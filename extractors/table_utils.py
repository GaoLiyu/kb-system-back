"""
表格处理工具（增强版）
======================
动态定位、合并单元格处理
"""

import re
from typing import List, Dict, Optional, Tuple, Any
from docx.table import Table
from docx.oxml.ns import qn

from .text_utils import normalize_text, normalize_label, FIELD_SYNONYMS


# ============================================================================
# 合并单元格处理
# ============================================================================

def get_cell_span(cell) -> Tuple[int, int]:
    """
    获取单元格的跨度（横向和纵向）

    Returns:
        (col_span, row_span)
    """
    tc = cell._tc

    # 横向跨度
    grid_span_elem = tc.find(qn('w:tcPr'))
    col_span = 1
    if grid_span_elem is not None:
        gs = grid_span_elem.find(qn('w:gridSpan'))
        if gs is not None:
            val = gs.get(qn('w:val'))
            if val:
                col_span = int(val)

    # 纵向跨度（vMerge）
    row_span = 1
    if grid_span_elem is not None:
        v_merge = grid_span_elem.find(qn('w:vMerge'))
        if v_merge is not None:
            val = v_merge.get(qn('w:val'))
            if val != 'restart':
                row_span = 0  # 这是被合并的单元格

    return (col_span, row_span)


def get_effective_row_cells(row) -> List[Tuple[int, str, int]]:
    """
    获取行的有效单元格（处理横向合并）

    Returns:
        [(logical_col_index, cell_text, col_span), ...]
        logical_col_index 是逻辑列号（考虑跨度后的）
    """
    cells = []
    seen_tcs = set()
    logical_col = 0

    for cell in row.cells:
        tc = cell._tc
        if tc in seen_tcs:
            continue
        seen_tcs.add(tc)

        col_span, _ = get_cell_span(cell)
        text = cell.text.strip() if cell.text else ''

        cells.append((logical_col, text, col_span))
        logical_col += col_span

    return cells


def row_to_text_list(row, expected_cols: int = None) -> List[str]:
    """
    将行转换为文本列表（处理合并单元格）

    Args:
        row: 表格行
        expected_cols: 期望的列数，超出部分截断，不足部分补空

    Returns:
        文本列表
    """
    effective_cells = get_effective_row_cells(row)

    # 构建结果列表
    result = []
    for logical_col, text, col_span in effective_cells:
        result.append(text)
        # 如果有跨度，后续列填充空字符串
        for _ in range(col_span - 1):
            result.append('')

    # 调整到期望长度
    if expected_cols:
        if len(result) < expected_cols:
            result.extend([''] * (expected_cols - len(result)))
        elif len(result) > expected_cols:
            result = result[:expected_cols]

    return result


def get_row_cells_simple(row) -> List[str]:
    """
    简单获取行的单元格文本（不处理合并，用于快速扫描）
    """
    return [c.text.strip() for c in row.cells]


# ============================================================================
# 动态表头定位
# ============================================================================

def find_header_row(table: Table,
                    required_keywords: List[str],
                    optional_keywords: List[str] = None,
                    max_rows: int = 5) -> int:
    """
    查找表头行

    Args:
        table: Word表格
        required_keywords: 必须包含的关键词
        optional_keywords: 可选关键词（用于打分）
        max_rows: 最多搜索前几行

    Returns:
        表头行索引，未找到返回 -1
    """
    best_row = -1
    best_score = -1

    for row_idx in range(min(len(table.rows), max_rows)):
        row_text = ' '.join(c.text for c in table.rows[row_idx].cells)
        normalized = normalize_text(row_text)

        # 检查必需关键词
        if required_keywords and not all(kw in normalized for kw in required_keywords):
            continue

        # 计算得分
        score = len(required_keywords) if required_keywords else 0
        if optional_keywords:
            score += sum(1 for kw in optional_keywords if kw in normalized)

        if score > best_score:
            best_score = score
            best_row = row_idx

    return best_row


def find_column_indices(table: Table,
                        column_fields: List[str],
                        header_row: int = 0) -> Dict[str, int]:
    """
    动态查找列索引

    Args:
        table: Word表格
        column_fields: 要查找的字段名列表（FIELD_SYNONYMS的key）
        header_row: 表头所在行

    Returns:
        {field_name: col_index, ...}
    """
    if header_row < 0 or header_row >= len(table.rows):
        return {}

    cells = get_effective_row_cells(table.rows[header_row])
    result = {}

    for logical_col, text, _ in cells:
        normalized = normalize_label(text)

        for field in column_fields:
            if field in result:
                continue  # 已找到

            synonyms = FIELD_SYNONYMS.get(field, [field])
            if any(syn in normalized for syn in synonyms):
                result[field] = logical_col
                break

    return result


# ============================================================================
# 动态行定位
# ============================================================================

def find_row_by_label(table: Table,
                      label_keywords: List[str],
                      start_row: int = 0,
                      label_col: int = 0,
                      end_row: int = None) -> int:
    """
    通过行标签查找行

    Args:
        table: Word表格
        label_keywords: 行标签关键词列表
        start_row: 开始搜索的行号
        label_col: 标签所在列
        end_row: 结束行号（不含）

    Returns:
        行索引，未找到返回 -1
    """
    if end_row is None:
        end_row = len(table.rows)

    for row_idx in range(start_row, min(end_row, len(table.rows))):
        try:
            cells = row_to_text_list(table.rows[row_idx])
            if label_col < len(cells):
                label = normalize_label(cells[label_col])
                if any(kw in label for kw in label_keywords):
                    return row_idx
        except Exception:
            continue

    return -1


def find_rows_by_labels(table: Table,
                        label_mapping: Dict[str, List[str]],
                        start_row: int = 0,
                        label_col: int = 0,
                        end_row: int = None) -> Dict[str, int]:
    """
    批量查找多个行

    Args:
        table: Word表格
        label_mapping: {field_name: [keyword1, keyword2, ...], ...}
        start_row: 开始搜索的行号
        label_col: 标签所在列
        end_row: 结束行号（不含）

    Returns:
        {field_name: row_index, ...}
    """
    result = {}
    remaining = dict(label_mapping)

    if end_row is None:
        end_row = len(table.rows)

    for row_idx in range(start_row, min(end_row, len(table.rows))):
        if not remaining:
            break

        try:
            cells = row_to_text_list(table.rows[row_idx])
            if label_col >= len(cells):
                continue

            # 合并前两列作为标签（有些表格第一列是分类，第二列是具体项）
            label = normalize_label(cells[label_col])
            if label_col + 1 < len(cells):
                label += normalize_label(cells[label_col + 1])

            for field_name, keywords in list(remaining.items()):
                if any(kw in label for kw in keywords):
                    result[field_name] = row_idx
                    del remaining[field_name]
                    break
        except Exception:
            continue

    return result


# ============================================================================
# 表格类型识别（打分制）
# ============================================================================

def get_table_text_block(table: Table, max_rows: int = 8, max_cols: int = 12) -> str:
    """获取表格文本块（用于类型识别）"""
    parts = []
    for row_idx in range(min(len(table.rows), max_rows)):
        try:
            cells = row_to_text_list(table.rows[row_idx], max_cols)
            parts.extend(cells)
        except Exception:
            continue
    return ' '.join(p for p in parts if p)


def score_table_type(table: Table, type_rules: Dict[str, Any]) -> int:
    """
    对表格进行类型打分

    Args:
        table: Word表格
        type_rules: {
            'required': ['关键词1', '关键词2'],  # 必须包含，否则返回-1
            'strong': ['关键词3', '关键词4'],    # 强特征，+3分
            'weak': ['关键词5', '关键词6'],      # 弱特征，+1分
            'min_rows': 5,                       # 最小行数
            'max_rows': 20,                      # 最大行数
        }

    Returns:
        得分，不满足required返回-1
    """
    text = normalize_text(get_table_text_block(table))
    rows = len(table.rows)

    score = 0

    # 检查必需关键词
    required = type_rules.get('required', [])
    if required and not all(kw in text for kw in required):
        return -1  # 不满足必需条件

    score += len(required) * 2

    # 强特征
    for kw in type_rules.get('strong', []):
        if kw in text:
            score += 3

    # 弱特征
    for kw in type_rules.get('weak', []):
        if kw in text:
            score += 1

    # 行数限制
    min_rows = type_rules.get('min_rows', 0)
    max_rows_limit = type_rules.get('max_rows', 999)
    if rows < min_rows or rows > max_rows_limit:
        score -= 5

    return score


# ============================================================================
# 表格类型规则定义
# ============================================================================

TABLE_TYPE_RULES = {
    # ===== 通用表格 =====

    # 结果汇总表
    'result_summary': {
        'required': [],
        'strong': ['单价', '总价', '评估结果'],
        'weak': ['建筑面积', '元/平方米', '万元', '大写', '坐落'],
        'max_rows': 10,
    },

    # 权属信息表
    'property_rights': {
        'required': [],
        'strong': ['不动产权证', '不动产权利人', '权属登记', '产权证'],
        'weak': ['坐落', '规划用途', '使用权类型', '土地面积', '终止日期'],
        'min_rows': 3,
    },

    # ===== 涉执/租金报告表格 =====

    # 基础信息表
    'basic_info': {
        'required': ['估价对象'],
        'strong': ['可比实例A', '可比实例B', '可比实例C', '项目'],
        'weak': ['地址', '坐落', '用途', '建筑面积', '交易价格', '来源'],
        'min_rows': 8,
    },

    # 因素描述表
    'factor_desc': {
        'required': ['估价对象'],
        'strong': ['区位状况', '实物状况', '权益状况'],
        'weak': ['可比实例', '因素', '描述'],
        'min_rows': 10,
    },

    # 因素等级表
    'factor_level': {
        'required': ['估价对象'],
        'strong': ['等级', '级别'],
        'weak': ['区位', '实物', '权益', '可比实例'],
        'min_rows': 8,
    },

    # 因素指数表
    'factor_index': {
        'required': [],
        'strong': ['指数', '100'],
        'weak': ['区位', '实物', '权益', '估价对象', '可比实例'],
        'min_rows': 8,
    },

    # 修正系数表（涉执/租金）
    'correction': {
        'required': [],
        'strong': ['交易情况修正', '市场状况', '修正后单价', '调整后单价'],
        'weak': ['区位状况', '实物状况', '权益状况', '交易价格'],
        'min_rows': 5,
    },

    # ===== 标准房报告表格 =====

    # 标准房主要信息表
    'biaozhunfang_main': {
        'required': [],
        'strong': ['估价对象', '可比实例A', '可比实例B', '可比实例C', '可比实例D'],
        'weak': ['地址', '建筑面积', '交易单价', '案例来源'],
        'min_rows': 20,
    },

    # 标准房详细因素表
    'biaozhunfang_detail': {
        'required': [],
        'strong': ['结构修正系数', '层次修正系数', '朝向修正系数', '成新修正系数'],
        'weak': ['东西至', '实体状况', '估价对象'],
        'min_rows': 15,
    },

    # 标准房修正计算表
    'biaozhunfang_correction': {
        'required': [],
        'strong': ['P1', 'P2', 'P3', 'P4', '比准价格'],
        'weak': ['交易情况修正', '交易日期修正', '实体状况', '区位状况', '综合'],
        'min_rows': 8,
    },
}


def auto_detect_tables(tables: List[Table],
                       table_types: List[str],
                       min_score: int = 3) -> Dict[str, int]:
    """
    自动检测表格索引

    Args:
        tables: 表格列表
        table_types: 要检测的表格类型列表
        min_score: 最低得分阈值

    Returns:
        {table_type: table_index, ...}
    """
    result = {}
    best_scores = {t: -1 for t in table_types}

    for idx, table in enumerate(tables):
        if len(table.rows) == 0:
            continue

        for table_type in table_types:
            rules = TABLE_TYPE_RULES.get(table_type)
            if not rules:
                continue

            score = score_table_type(table, rules)
            if score > best_scores[table_type]:
                best_scores[table_type] = score
                result[table_type] = idx

    # 过滤掉得分太低的
    return {k: v for k, v in result.items() if best_scores[k] >= min_score}


# ============================================================================
# 权属表提取（通用）
# ============================================================================

def extract_property_rights_generic(table: Table) -> Dict[str, str]:
    """
    从权属表中提取通用字段

    Returns:
        {field_name: value, ...}
    """
    result = {}

    # 权属表通常是两列或三列的键值对形式
    for row in table.rows:
        cells = get_row_cells_simple(row)

        if len(cells) >= 2:
            # 两列形式：键 | 值
            key = normalize_label(cells[0])
            value = cells[1].strip() if len(cells) > 1 else ''

            # 映射常见字段
            if '不动产权证' in key or '证号' in key:
                result['cert_no'] = value
            elif '权利人' in key:
                result['owner'] = value
            elif '坐落' in key:
                result['address'] = value
            elif '用途' in key:
                result['usage'] = value
            elif '面积' in key and '土地' not in key:
                result['building_area'] = value
            elif '结构' in key:
                result['structure'] = value
            elif '终止日期' in key or '使用期限' in key:
                result['land_end_date'] = value

        if len(cells) >= 4:
            # 四列形式：键1 | 值1 | 键2 | 值2
            key2 = normalize_label(cells[2])
            value2 = cells[3].strip() if len(cells) > 3 else ''

            if '不动产权证' in key2 or '证号' in key2:
                result['cert_no'] = value2
            elif '权利人' in key2:
                result['owner'] = value2
            elif '用途' in key2:
                result['usage'] = value2
            elif '面积' in key2 and '土地' not in key2:
                result['building_area'] = value2
            elif '结构' in key2:
                result['structure'] = value2

    return result