# table_utils.py
# -*- coding: utf-8 -*-
"""
Word(docx) 表格提取通用工具集（偏“抗模板变化”）
================================================

设计目标：
1) 不依赖固定行/列号：通过“表头定位 + 列映射 + 行定位”来取值
2) 兼容合并单元格、空行、表头分两行、字段名/值分离等常见情况
3) 可支持“打分制”表格识别（你已经做了自动检测，这里也保留通用能力）

使用建议（最小可用）：
- 先确定 table（你自动检测得到的 index）
- 在该 table 内：
  1) header_row = find_best_header_row(...)
  2) col_map = build_col_map_by_keywords(header_cells, rules)
  3) data_row = find_data_row_after_header(...)
  4) value = pick_cell(table, data_row, col_map["xxx"])

可选增强：
- find_kv_value_in_table：直接在“字段-值”结构里找（不需要表头）
- fuzzy label 行定位：find_row_by_label / extract_rows_kv
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# =========================
# 文本归一化/解析
# =========================

_SPACE_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

def norm_text(s: Any) -> str:
    """归一化文本：去掉全角空格/多空白/首尾空白"""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\u3000", " ")
    s = s.replace("\t", " ").replace("\n", " ")
    s = _SPACE_RE.sub(" ", s).strip()
    return s

def compact_text(s: Any) -> str:
    """更激进的归一化：去掉所有空格，适合匹配“P1 交易 情况 修正”这类被拆开的文本"""
    return norm_text(s).replace(" ", "")

def looks_like_number(s: str) -> bool:
    s = norm_text(s)
    if not s:
        return False
    # 允许带单位（㎡、万元等），但要求能提取出数字
    return bool(_NUM_RE.search(s))

def parse_first_number(s: str) -> Optional[float]:
    """从字符串中提取第一个数字（失败返回 None）"""
    s = norm_text(s)
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def count_hits(text: str, keys: Sequence[str]) -> int:
    """统计命中关键词数量（text 要求是 compact 后的更稳）"""
    return sum(1 for k in keys if k in text)

def has_all(text: str, keys: Sequence[str]) -> bool:
    return all(k in text for k in keys)

def has_any(text: str, keys: Sequence[str]) -> bool:
    return any(k in text for k in keys)


# =========================
# docx Table/Row/Cell 访问
# =========================

def table_size(table) -> Tuple[int, int]:
    """返回 (rows, cols)"""
    rows = len(getattr(table, "rows", []) or [])
    cols = 0
    try:
        cols = len(table.columns) if getattr(table, "columns", None) else 0
    except Exception:
        cols = 0
    return rows, cols

def row_cells_text(row) -> List[str]:
    """读取一行所有 cell 的文本（norm）"""
    return [norm_text(c.text) for c in row.cells]

def get_cell_text(table, r: int, c: int) -> str:
    """安全获取 cell 文本"""
    try:
        return norm_text(table.rows[r].cells[c].text)
    except Exception:
        return ""

def join_row_prefix_as_label(table, r: int, k: int = 2) -> str:
    """
    把一行的前 k 列拼成 label（处理合并单元格/第一列空但第二列有字等）
    """
    try:
        cells = row_cells_text(table.rows[r])
    except Exception:
        return ""
    label = " ".join(cells[: max(1, k)])
    return norm_text(label)

def table_text_block(table, max_rows: int = 10, max_cols: int = 12) -> str:
    """
    把表格前 max_rows 行、前 max_cols 列拼成一个大文本块
    用于：表格打分识别、粗略判断表类型等
    """
    parts: List[str] = []
    rows, _ = table_size(table)
    for r in range(min(rows, max_rows)):
        try:
            row = table.rows[r]
        except Exception:
            continue
        cells = row.cells[: max_cols]
        for cell in cells:
            t = norm_text(cell.text)
            if t:
                parts.append(t)
    return " ".join(parts)

def table_text_block_compact(table, max_rows: int = 10, max_cols: int = 12) -> str:
    return compact_text(table_text_block(table, max_rows=max_rows, max_cols=max_cols))


# =========================
# 表头行定位 / 数据行定位
# =========================

def find_best_header_row(
    table,
    header_keys: Sequence[str],
    *,
    start: int = 0,
    end: Optional[int] = None,
    max_cols: int = 12,
    min_score: int = 1,
) -> int:
    """
    在 [start, end) 行内，找“最像表头”的行：命中 header_keys 最多的那一行
    返回 row_index，找不到返回 -1
    """
    rows, _ = table_size(table)
    if end is None or end > rows:
        end = rows

    best_score = -1
    best_idx = -1

    for r in range(start, end):
        # 只看前 max_cols 列，避免正文大列影响
        row_text = " ".join(get_cell_text(table, r, c) for c in range(max_cols))
        t = compact_text(row_text)
        score = count_hits(t, header_keys)
        if score > best_score:
            best_score = score
            best_idx = r

    if best_score < min_score:
        return -1
    return best_idx

def find_data_row_after_header(
    table,
    header_row: int,
    *,
    min_filled_cells: int = 3,
    max_scan_rows: int = 8,
) -> int:
    """
    从 header_row 后开始找第一行“像数据”的行：
    - 非空 cell 数 >= min_filled_cells
    - 默认最多往下扫 max_scan_rows 行
    返回 row_index，找不到返回 -1
    """
    rows, _ = table_size(table)
    start = header_row + 1
    end = min(rows, start + max_scan_rows)

    for r in range(start, end):
        try:
            cells = row_cells_text(table.rows[r])
        except Exception:
            continue
        filled = sum(1 for x in cells if x)
        if filled >= min_filled_cells:
            return r
    return -1

def find_row_by_label(
    table,
    label_keys: Sequence[str],
    *,
    start: int = 0,
    end: Optional[int] = None,
    label_cols: int = 2,
    mode: str = "any",  # "any" or "all"
) -> int:
    """
    用“行 label”定位行（通常用于主表、修正表、因素表等按行名取值的场景）
    - label = 前 label_cols 列拼接
    - mode="any": 命中任意关键词算匹配
    - mode="all": 必须命中全部关键词
    """
    rows, _ = table_size(table)
    if end is None or end > rows:
        end = rows

    for r in range(start, end):
        label = compact_text(join_row_prefix_as_label(table, r, k=label_cols))
        if mode == "all":
            if has_all(label, [compact_text(k) for k in label_keys]):
                return r
        else:
            if has_any(label, [compact_text(k) for k in label_keys]):
                return r
    return -1


# =========================
# 列映射（关键字 -> 列号）
# =========================

@dataclass
class ColRule:
    """
    一个列映射规则：匹配到 header cell 文本则认为该列属于某个 key
    - include: 必须包含的关键词（任意一个/全部由 match_mode 控制）
    - exclude: 不能包含的关键词（命中则排除）
    - match_mode: "any" or "all"
    """
    key: str
    include: Sequence[str]
    exclude: Sequence[str] = ()
    match_mode: str = "any"

def build_col_map_by_keywords(
    header_cells: Sequence[str],
    rules: Sequence[ColRule],
    *,
    compact: bool = True,
) -> Dict[str, int]:
    """
    根据 header_cells 和规则生成 col_map：{key: col_index}
    - 如果多个列同时命中同一 key，取第一个命中的列
    """
    col_map: Dict[str, int] = {}

    for ci, h in enumerate(header_cells):
        ht = compact_text(h) if compact else norm_text(h)

        for rule in rules:
            if rule.key in col_map:
                continue

            inc = [compact_text(x) if compact else norm_text(x) for x in rule.include]
            exc = [compact_text(x) if compact else norm_text(x) for x in rule.exclude]

            if exc and has_any(ht, exc):
                continue

            ok = has_any(ht, inc) if rule.match_mode == "any" else has_all(ht, inc)
            if ok:
                col_map[rule.key] = ci

    return col_map

def get_header_cells(
    table,
    header_row: int,
    *,
    max_cols: Optional[int] = None,
) -> List[str]:
    """读取 header_row 的所有 cell 文本（可限制 max_cols）"""
    try:
        cells = row_cells_text(table.rows[header_row])
    except Exception:
        return []
    if max_cols is not None:
        return cells[:max_cols]
    return cells


# =========================
# 取值工具：按 col_map 或按相邻 KV
# =========================

def pick_cell_by_col_map(
    table,
    row: int,
    col_map: Dict[str, int],
    key: str,
    *,
    default: str = "",
) -> str:
    """从 (row, col_map[key]) 取值"""
    ci = col_map.get(key)
    if ci is None:
        return default
    return get_cell_text(table, row, ci) or default

def pick_number_by_col_map(
    table,
    row: int,
    col_map: Dict[str, int],
    key: str,
) -> Optional[float]:
    """从 col_map 定位列后解析数字"""
    s = pick_cell_by_col_map(table, row, col_map, key, default="")
    return parse_first_number(s)

def find_kv_value_in_row(
    row_cells: Sequence[str],
    field_keys: Sequence[str],
    *,
    search_from: int = 0,
) -> Optional[str]:
    """
    处理常见“字段-值”结构：某个 cell 包含字段名，值在右侧相邻 cell
    返回找到的值字符串；找不到返回 None
    """
    keys = [compact_text(k) for k in field_keys]
    for i in range(search_from, len(row_cells)):
        cell = compact_text(row_cells[i])
        if has_any(cell, keys):
            # 值通常在右侧相邻 cell
            if i + 1 < len(row_cells):
                v = norm_text(row_cells[i + 1])
                if v:
                    return v
    return None

def find_kv_value_in_table(
    table,
    field_keys: Sequence[str],
    *,
    start: int = 0,
    end: Optional[int] = None,
    prefer_right_cell: bool = True,
) -> Optional[str]:
    """
    在整个表里找“字段-值”：
    - field_keys 命中某 cell，则取右侧 cell 作为 value（最常见）
    - 如果 prefer_right_cell=False，可扩展为同行拼接/下一行等（你后续可加）
    """
    rows, _ = table_size(table)
    if end is None or end > rows:
        end = rows

    for r in range(start, end):
        try:
            cells = row_cells_text(table.rows[r])
        except Exception:
            continue
        v = find_kv_value_in_row(cells, field_keys, search_from=0)
        if v:
            return v
    return None


# =========================
# 表格打分识别（可选）
# =========================

@dataclass
class TableScoreRule:
    """
    表格打分规则：强特征/弱特征/形态特征
    - strong: 命中一次给 strong_w 分
    - weak: 命中一次给 weak_w 分
    - shape: (rows_min, cols_min) 满足则加 shape_w 分
    """
    name: str
    strong: Sequence[str] = ()
    weak: Sequence[str] = ()
    strong_w: int = 3
    weak_w: int = 1
    rows_min: int = 0
    cols_min: int = 0
    shape_w: int = 0
    require_all_strong: bool = False  # True: 必须命中全部 strong 才计分

def score_table(
    table,
    rule: TableScoreRule,
    *,
    max_rows: int = 10,
    max_cols: int = 12,
) -> int:
    """
    对单个 table 根据 rule 打分
    """
    t = table_text_block_compact(table, max_rows=max_rows, max_cols=max_cols)
    rows, cols = table_size(table)

    if rule.require_all_strong and rule.strong:
        if not has_all(t, [compact_text(k) for k in rule.strong]):
            return 0

    score = 0
    score += rule.strong_w * count_hits(t, [compact_text(k) for k in rule.strong])
    score += rule.weak_w * count_hits(t, [compact_text(k) for k in rule.weak])

    if rows >= rule.rows_min and cols >= rule.cols_min:
        score += rule.shape_w

    return score

def best_table_index_by_rules(
    tables: Sequence[Any],
    rules: Sequence[TableScoreRule],
    *,
    max_rows: int = 10,
    max_cols: int = 12,
    threshold: Optional[Dict[str, int]] = None,
) -> Dict[str, int]:
    """
    多规则：为每个 rule.name 找最佳 table index
    返回：{rule.name: index}；如果达不到阈值则不返回该 name
    """
    best: Dict[str, Tuple[int, int]] = {r.name: (-1, -1) for r in rules}

    for i, table in enumerate(tables):
        for r in rules:
            s = score_table(table, r, max_rows=max_rows, max_cols=max_cols)
            if s > best[r.name][0]:
                best[r.name] = (s, i)

    out: Dict[str, int] = {}
    for r in rules:
        s, idx = best[r.name]
        if idx < 0:
            continue
        if threshold and r.name in threshold:
            if s < threshold[r.name]:
                continue
        out[r.name] = idx
    return out


# =========================
# 常用列规则模板（你可以按项目继续扩展）
# =========================

def common_property_rights_rules(kind: str = "house") -> List[ColRule]:
    """
    权属表常用列映射规则（房屋/土地）
    kind="house" or "land"
    """
    if kind == "house":
        return [
            ColRule("cert_no", include=["证号", "产权证"], exclude=["土地"]),
            ColRule("owner", include=["权利人", "所有权人", "产权人"]),
            ColRule("address", include=["坐落", "地址"]),
            ColRule("structure", include=["结构"]),
            ColRule("floor", include=["楼层", "所在层", "总层", "层数"], match_mode="any"),
            ColRule("building_area", include=["建筑面积", "面积"], exclude=["土地"]),
            ColRule("plan_usage", include=["用途", "规划用途"]),
        ]
    else:
        return [
            ColRule("land_no", include=["土地", "证号", "使用证"], match_mode="any"),
            ColRule("land_owner", include=["土地", "权利人", "使用权人"], match_mode="any"),
            ColRule("land_address", include=["坐落", "地址"]),
            ColRule("land_use_type", include=["使用权类型", "权利类型"]),
            ColRule("land_type", include=["地类", "用途"]),
            ColRule("land_area", include=["土地", "面积"], match_mode="any"),
            ColRule("end_date", include=["终止日期", "到期日期", "终止"], match_mode="any"),
        ]


# =========================
# 示例：用该 utils 改造“权属表”
# =========================

def extract_property_rights_generic(
    table,
    *,
    subject_setter: Callable[[str, Any], None],
    detect_land: bool = True,
) -> None:
    """
    一个“通用版权属表”提取示例（你可以直接在 extractor 里调用）
    - subject_setter：回写字段的回调，例如：
        subject_setter("cert_no", "xxxx")
        subject_setter("building_area", 123.4)
    """
    # ---- A) 房屋块 ----
    header_keys = ["证号", "权利人", "坐落", "结构", "楼层", "面积", "用途"]
    h = find_best_header_row(table, header_keys, min_score=2)
    if h >= 0:
        header_cells = get_header_cells(table, h)
        col_map = build_col_map_by_keywords(header_cells, common_property_rights_rules("house"))
        data_row = find_data_row_after_header(table, h, min_filled_cells=3)
        if data_row >= 0:
            cert_no = pick_cell_by_col_map(table, data_row, col_map, "cert_no")
            owner = pick_cell_by_col_map(table, data_row, col_map, "owner")
            address = pick_cell_by_col_map(table, data_row, col_map, "address")
            structure = pick_cell_by_col_map(table, data_row, col_map, "structure")
            floor = pick_cell_by_col_map(table, data_row, col_map, "floor")
            plan_usage = pick_cell_by_col_map(table, data_row, col_map, "plan_usage")
            area = pick_number_by_col_map(table, data_row, col_map, "building_area")

            if cert_no: subject_setter("cert_no", cert_no)
            if owner: subject_setter("owner", owner)
            if address: subject_setter("address", address)
            if structure: subject_setter("structure", structure)
            if floor: subject_setter("floor", floor)
            if plan_usage: subject_setter("plan_usage", plan_usage)
            if area is not None: subject_setter("building_area", area)

    # ---- B) 土地块（可选）----
    if not detect_land:
        return

    land_hint_keys = ["土地", "使用证", "使用权", "地类", "终止日期", "土地面积"]
    lh = find_best_header_row(table, land_hint_keys, min_score=2)
    if lh >= 0:
        header_cells = get_header_cells(table, lh)
        land_map = build_col_map_by_keywords(header_cells, common_property_rights_rules("land"))
        data_row = find_data_row_after_header(table, lh, min_filled_cells=3)
        if data_row >= 0:
            land_no = pick_cell_by_col_map(table, data_row, land_map, "land_no")
            land_owner = pick_cell_by_col_map(table, data_row, land_map, "land_owner")
            land_address = pick_cell_by_col_map(table, data_row, land_map, "land_address")
            land_use_type = pick_cell_by_col_map(table, data_row, land_map, "land_use_type")
            land_type = pick_cell_by_col_map(table, data_row, land_map, "land_type")
            land_area = pick_number_by_col_map(table, data_row, land_map, "land_area")
            end_date = pick_cell_by_col_map(table, data_row, land_map, "end_date")

            if land_no: subject_setter("land_no", land_no)
            if land_owner: subject_setter("land_owner", land_owner)
            if land_address: subject_setter("land_address", land_address)
            if land_use_type: subject_setter("land_use_type", land_use_type)
            if land_type: subject_setter("land_type", land_type)
            if land_area is not None: subject_setter("land_area", land_area)
            if end_date: subject_setter("end_date", end_date)
