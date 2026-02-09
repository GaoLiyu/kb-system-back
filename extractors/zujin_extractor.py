"""
租金报告提取器（重构版）
========================
使用动态定位替代硬编码索引
"""

import os
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from .base_extractor import BaseExtractor, LocatedValue, Position, Factor, ExtractionStats
from .table_utils import (
    find_column_indices, find_rows_by_labels, find_row_by_label,
    row_to_text_list, get_row_cells_simple, extract_property_rights_generic
)
from .text_utils import parse_number, normalize_label, extract_year, parse_floor, parse_area, infer_floors_from_rooms


@dataclass
class Case:
    """可比实例"""
    case_id: str = ""
    address: LocatedValue = field(default_factory=LocatedValue)
    location: str = ""
    usage: str = ""
    data_source: str = ""
    rental_price: LocatedValue = field(default_factory=LocatedValue)  # 租金价格
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_date: str = ""

    # 扩展字段
    district: str = ""
    street: str = ""
    build_year: int = 0
    total_floor: int = 0
    current_floor: str = ""
    structure: str = ""
    orientation: str = ""
    decoration: str = ""
    floor: str = ""  # 原始楼层文本

    # 修正系数
    transaction_correction: LocatedValue = field(default_factory=LocatedValue)
    market_correction: LocatedValue = field(default_factory=LocatedValue)
    location_correction: LocatedValue = field(default_factory=LocatedValue)
    physical_correction: LocatedValue = field(default_factory=LocatedValue)
    rights_correction: LocatedValue = field(default_factory=LocatedValue)
    adjusted_price: LocatedValue = field(default_factory=LocatedValue)

    # 因素数据
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class Subject:
    """估价对象"""
    address: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    unit_price: LocatedValue = field(default_factory=LocatedValue)  # 租金单价
    total_price: LocatedValue = field(default_factory=LocatedValue)  # 租金总价

    # 扩展字段
    district: str = ""
    street: str = ""
    usage: str = ""
    structure: str = ""
    cert_no: str = ""
    owner: str = ""
    land_end_date: str = ""
    total_floor: int = 0
    current_floor: str = ""
    orientation: str = ""
    decoration: str = ""
    build_year: int = 0
    floor: str = ""
    value_date: str = ""
    appraisal_purpose: str = ""
    transaction_date: str = ""

    # 因素数据
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class ZujinExtractionResult:
    """租金报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)

    final_unit_price: LocatedValue = field(default_factory=LocatedValue)  # 租金单价
    final_total_price: LocatedValue = field(default_factory=LocatedValue)  # 租金总价
    floor_factor: float = 1.0

    # 多对象明细
    subjects: List[Subject] = field(default_factory=list)
    rent_unit: str = 'year' # 'year' or 'month' or 'day'
    price_in_wan: bool = False # 是否为万

    type: str = "zujin"
    stats: ExtractionStats = field(default_factory=ExtractionStats)


class ZujinExtractor(BaseExtractor):
    """租金报告提取器"""

    # 需要检测的表格类型
    TABLE_TYPES = ['result_summary', 'property_rights', 'basic_info', 'factor_desc',
                   'factor_level', 'factor_index', 'correction']

    # 基础信息表行标签
    BASIC_ROW_LABELS = {
        'address': ['地址', '坐落'],
        'usage': ['用途', '房屋用途', '规划用途'],
        'data_source': ['来源', '数据来源', '案例来源'],
        'rental_price': ['交易价格', '租金价格', '租金', '租赁价格', '月租金'],
        'building_area': ['建筑面积', '面积'],
        'transaction_date': ['交易时间', '交易日期', '成交日期', '价值时点'],
        'structure': ['结构', '建筑结构'],
        'floor': ['层次', '楼层', '所在层'],
        'orientation': ['朝向', '房屋朝向'],
        'build_year': ['建成年代', '建成时间', '建成年份'],
        'decoration': ['装修', '装修情况'],
    }

    # 修正系数表行标签
    CORRECTION_ROW_LABELS = {
        'rental_price': ['交易价格', '租金价格', '租金'],
        'transaction_correction': ['交易情况修正', '交易情况'],
        'market_correction': ['市场状况修正', '市场状况', '市场状况调整'],
        'location_correction': ['区位状况修正', '区位状况', '区位状况调整'],
        'physical_correction': ['实物状况修正', '实物状况', '实物状况调整'],
        'rights_correction': ['权益状况修正', '权益状况', '权益状况调整'],
        'adjusted_price': ['调整后单价', '修正后单价', '比准价格'],
    }

    def __init__(self, auto_detect: bool = True):
        super().__init__(auto_detect)

        # 备用硬编码索引
        self.TABLE_RESULT_SUMMARY = 0
        self.TABLE_PROPERTY_RIGHTS = 1
        self.TABLE_BASIC_INFO = 4
        self.TABLE_FACTOR_DESC = 5
        self.TABLE_FACTOR_LEVEL = 6
        self.TABLE_FACTOR_INDEX = 7
        self.TABLE_CORRECTION = 8

    def extract(self, doc_path: str) -> ZujinExtractionResult:
        """提取租金报告"""
        # 1. 加载文档
        self.load_document(doc_path)

        result = ZujinExtractionResult(
            source_file=os.path.basename(doc_path)
        )

        print(f"\n📊 提取租金报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")

        # 2. 更新表格索引
        self._update_table_indices()
        print(f"   表格索引: 汇总={self.TABLE_RESULT_SUMMARY}, 权属={self.TABLE_PROPERTY_RIGHTS}, "
              f"基础={self.TABLE_BASIC_INFO}, 修正={self.TABLE_CORRECTION}")

        # 3. 初始化3个可比实例
        result.cases = [Case(case_id=c) for c in ['A', 'B', 'C']]

        # 4. 提取各表格数据
        self._extract_result_summary(result)
        addr_display = result.subject.address.value if result.subject.address and result.subject.address.value else '未提取'
        print(f"   ✓ 结果汇总: {addr_display} ({len(result.subjects)}个估价对象, 单位={result.rent_unit})")

        self._extract_property_rights(result)
        print(f"   ✓ 权属信息")

        self._extract_basic_info(result)
        print(f"   ✓ 基础信息: {len(result.cases)}个可比实例")

        self._extract_factor_descriptions(result)
        self._extract_factor_levels(result)
        self._extract_factor_indices(result)
        print(f"   ✓ 因素数据: 描述/等级/指数")

        self._extract_corrections(result)
        print(f"   ✓ 修正系数")

        self._extract_floor_factor(result)
        if result.floor_factor != 1.0:
            print(f"   ✓ 楼层修正: {result.floor_factor}")

        self._extract_extended_info(result)
        self._parse_district_info(result)
        self._parse_floor_info(result)
        print(f"   ✓ 区域信息: {result.subject.district}")

        # 5. 记录统计
        result.stats = self.stats

        return result

    def _update_table_indices(self):
        """更新表格索引"""
        if 'result_summary' in self.table_indices:
            self.TABLE_RESULT_SUMMARY = self.table_indices['result_summary']
        if 'property_rights' in self.table_indices:
            self.TABLE_PROPERTY_RIGHTS = self.table_indices['property_rights']
        if 'basic_info' in self.table_indices:
            self.TABLE_BASIC_INFO = self.table_indices['basic_info']
        if 'factor_desc' in self.table_indices:
            self.TABLE_FACTOR_DESC = self.table_indices['factor_desc']
        if 'factor_level' in self.table_indices:
            self.TABLE_FACTOR_LEVEL = self.table_indices['factor_level']
        if 'factor_index' in self.table_indices:
            self.TABLE_FACTOR_INDEX = self.table_indices['factor_index']
        if 'correction' in self.table_indices:
            self.TABLE_CORRECTION = self.table_indices['correction']

        # 兜底
        if self.TABLE_BASIC_INFO > 0:
            base = self.TABLE_BASIC_INFO
            if 'factor_desc' not in self.table_indices:
                self.TABLE_FACTOR_DESC = min(base + 1, len(self.tables) - 1)
            if 'factor_level' not in self.table_indices:
                self.TABLE_FACTOR_LEVEL = min(base + 2, len(self.tables) - 1)
            if 'factor_index' not in self.table_indices:
                self.TABLE_FACTOR_INDEX = min(base + 3, len(self.tables) - 1)
            if 'correction' not in self.table_indices:
                self.TABLE_CORRECTION = min(base + 4, len(self.tables) - 1)

    def _extract_result_summary(self, result: ZujinExtractionResult):
        """提取结果汇总表（支持多估价对象）"""
        if self.TABLE_RESULT_SUMMARY >= len(self.tables):
            return

        table = self.tables[self.TABLE_RESULT_SUMMARY]
        table_idx = self.TABLE_RESULT_SUMMARY

        if len(table.rows) < 2:
            return

        # ============================================================
        # 第一步：从表头动态定位各列
        # ============================================================
        header_cells = row_to_text_list(table.rows[0])
        col_map = {
            'address': -1,
            'floor': -1,
            'area': -1,
            'unit_price': -1,
            'total_price': -1,
        }

        for col_idx, cell_text in enumerate(header_cells):
            text = normalize_label(cell_text)
            if '坐落' in text or '地址' in text:
                col_map['address'] = col_idx
            elif '楼层' in text or '层次' in text:
                col_map['floor'] = col_idx
            elif '面积' in text:
                col_map['area'] = col_idx
            elif '单价' in text:
                col_map['unit_price'] = col_idx
                # 从表头识别租金单位: 元/㎡·日、元/㎡·月、元/㎡·年
                if '日' in cell_text:
                    result.rent_unit = 'day'
                elif '月' in cell_text:
                    result.rent_unit = 'month'
                else:
                    result.rent_unit = 'year'
            elif '总价' in text:
                col_map['total_price'] = col_idx
                # 从表头识别万元单位
                if '万元' in cell_text:
                    result.price_in_wan = True

        # 如果表头没有"楼层"列（老格式4列表），回退到硬编码
        if col_map['area'] < 0:
            # 没找到面积列，说明表头识别失败，用老逻辑兼容
            # 老格式: 坐落(0) | 面积(1) | 单价(2) | 总价(3)
            col_map = {'address': 0, 'floor': -1, 'area': 1,
                       'unit_price': 2, 'total_price': 3}

        print(f"   汇总表列映射: {col_map}, 租金单位={result.rent_unit}, 万元={result.price_in_wan}")

        # ============================================================
        # 第二步：遍历数据行，收集所有估价对象
        # ============================================================
        summary_row = None  # 合计行

        for row_idx in range(1, len(table.rows)):
            cells = row_to_text_list(table.rows[row_idx])

            # 判断是否合计行
            row_text_joined = ''.join(cells)
            if '合计' in row_text_joined or '小计' in row_text_joined:
                summary_row = (row_idx, cells)
                continue

            # 判断是否空行（地址列为空）
            addr_col = col_map['address']
            if addr_col >= 0 and addr_col < len(cells):
                addr_text = cells[addr_col].strip()
                if not addr_text:
                    continue
            else:
                continue

            # 创建一个估价对象
            sub = Subject()

            # 地址
            if addr_col >= 0 and addr_col < len(cells):
                sub.address = self.create_located_value(
                    cells[addr_col], table_idx, row_idx, addr_col, cells[addr_col]
                )

            # 楼层
            floor_col = col_map['floor']
            if floor_col >= 0 and floor_col < len(cells) and cells[floor_col].strip():
                sub.floor = cells[floor_col].strip()

            # 面积
            area_col = col_map['area']
            if area_col >= 0 and area_col < len(cells):
                raw_area_text = cells[area_col]
                area_value, area_unit = parse_area(raw_area_text)
                if area_value:
                    value = area_value  # 已经统一为平方米
                    if area_unit == 'mu':
                        print(f"     ⚠️ 面积使用亩单位: {raw_area_text} → {value:.2f}㎡")
                else:
                    value = self.safe_extract_number(
                        raw_area_text, f'subject_{row_idx}_area',
                        Position(table_idx, row_idx, area_col)
                    )
                if value:
                    sub.building_area = self.create_located_value(
                        value, table_idx, row_idx, area_col, cells[area_col]
                    )

            # 单价
            up_col = col_map['unit_price']
            if up_col >= 0 and up_col < len(cells):
                value = self.safe_extract_number(
                    cells[up_col], f'subject_{row_idx}_unit_price',
                    Position(table_idx, row_idx, up_col)
                )
                if value:
                    sub.unit_price = self.create_located_value(
                        value, table_idx, row_idx, up_col, cells[up_col]
                    )

            # 总价
            tp_col = col_map['total_price']
            if tp_col >= 0 and tp_col < len(cells):
                raw_text = cells[tp_col]
                value = self.safe_extract_number(
                    raw_text, f'subject_{row_idx}_total_price',
                    Position(table_idx, row_idx, tp_col)
                )
                if value:
                    # 万元转换
                    if result.price_in_wan:
                        value = value * 10000
                    sub.total_price = self.create_located_value(
                        value, table_idx, row_idx, tp_col, raw_text
                    )

            result.subjects.append(sub)

        # ============================================================
        # 第三步：填充 result.subject（主估价对象 / 合计）
        # ============================================================
        if len(result.subjects) == 1:
            # 只有一个估价对象，直接作为主估价对象
            only = result.subjects[0]
            result.subject.address = only.address
            result.subject.building_area = only.building_area
            result.subject.unit_price = only.unit_price
            result.subject.total_price = only.total_price
            result.subject.floor = only.floor
            # 设置 final_xxx
            result.final_unit_price = only.unit_price
            result.final_total_price = only.total_price

        elif len(result.subjects) > 1:
            # 多个估价对象：用合计行或手动累加
            # 地址拼接
            addresses = [s.address.value for s in result.subjects if s.address and s.address.value]
            combined_addr = '、'.join(addresses) if addresses else ''
            result.subject.address = self.create_located_value(
                combined_addr, table_idx, 1, col_map['address'], combined_addr
            )

            if summary_row:
                # 有合计行，从合计行取面积和总价
                sum_row_idx, sum_cells = summary_row

                area_col = col_map['area']
                if area_col >= 0 and area_col < len(sum_cells):
                    value = self.safe_extract_number(
                        sum_cells[area_col], 'summary_area',
                        Position(table_idx, sum_row_idx, area_col)
                    )
                    if value:
                        result.subject.building_area = self.create_located_value(
                            value, table_idx, sum_row_idx, area_col, sum_cells[area_col]
                        )

                tp_col = col_map['total_price']
                if tp_col >= 0 and tp_col < len(sum_cells):
                    raw_text = sum_cells[tp_col]
                    value = self.safe_extract_number(
                        raw_text, 'summary_total_price',
                        Position(table_idx, sum_row_idx, tp_col)
                    )
                    if value:
                        if result.price_in_wan:
                            value = value * 10000
                        result.subject.total_price = self.create_located_value(
                            value, table_idx, sum_row_idx, tp_col, raw_text
                        )
            else:
                # 没有合计行，手动累加
                total_area = sum(
                    s.building_area.value for s in result.subjects
                    if s.building_area and s.building_area.value
                )
                total_price = sum(
                    s.total_price.value for s in result.subjects
                    if s.total_price and s.total_price.value
                )
                if total_area > 0:
                    result.subject.building_area = self.create_located_value(
                        total_area, table_idx, 1, col_map['area'], f'{total_area:.2f}'
                    )
                if total_price > 0:
                    result.subject.total_price = self.create_located_value(
                        total_price, table_idx, 1, col_map['total_price'], f'{total_price:.2f}'
                    )

            # 单价：取第一个估价对象的单价（各对象通常相同）
            first_with_price = next(
                (s for s in result.subjects if s.unit_price and s.unit_price.value), None
            )
            if first_with_price:
                result.subject.unit_price = first_with_price.unit_price

            result.final_unit_price = result.subject.unit_price
            result.final_total_price = result.subject.total_price

        # 如果上面没有提取到任何 subject（表格结构异常），走老逻辑兜底
        if not result.subjects:
            self._extract_result_summary_fallback(result)

        print(f"   估价对象数量: {len(result.subjects)}")
        for i, s in enumerate(result.subjects):
            addr = s.address.value if s.address and s.address.value else '?'
            area = s.building_area.value if s.building_area and s.building_area.value else '?'
            tp = s.total_price.value if s.total_price and s.total_price.value else '?'
            print(f"     [{i + 1}] {addr} | 面积={area} | 总价={tp}")

    def _extract_result_summary_fallback(self, result: ZujinExtractionResult):
        """兜底：老格式汇总表（当动态表头识别失败时）"""
        table = self.tables[self.TABLE_RESULT_SUMMARY]
        table_idx = self.TABLE_RESULT_SUMMARY

        if len(table.rows) >= 2:
            cells = get_row_cells_simple(table.rows[1])

            if len(cells) >= 1 and cells[0]:
                result.subject.address = self.create_located_value(
                    cells[0], table_idx, 1, 0, cells[0]
                )
            if len(cells) >= 2:
                value = self.safe_extract_number(cells[1], 'building_area', Position(table_idx, 1, 1))
                if value:
                    result.subject.building_area = self.create_located_value(value, table_idx, 1, 1, cells[1])
            if len(cells) >= 3:
                value = self.safe_extract_number(cells[2], 'unit_price', Position(table_idx, 1, 2))
                if value:
                    result.subject.unit_price = self.create_located_value(value, table_idx, 1, 2, cells[2])
                    result.final_unit_price = result.subject.unit_price
            if len(cells) >= 4:
                total_text = cells[3]
                value = self.safe_extract_number(total_text, 'total_price', Position(table_idx, 1, 3))
                if value:
                    result.subject.total_price = self.create_located_value(value, table_idx, 1, 3, total_text)
                    result.final_total_price = result.subject.total_price

            # 创建单个 subject
            sub = Subject()
            sub.address = result.subject.address
            sub.building_area = result.subject.building_area
            sub.unit_price = result.subject.unit_price
            sub.total_price = result.subject.total_price
            result.subjects.append(sub)

    def _extract_property_rights(self, result: ZujinExtractionResult):
        """提取权属信息"""
        if self.TABLE_PROPERTY_RIGHTS >= len(self.tables):
            return

        table = self.tables[self.TABLE_PROPERTY_RIGHTS]

        rights_info = extract_property_rights_generic(table)

        if 'cert_no' in rights_info:
            result.subject.cert_no = rights_info['cert_no']
        if 'owner' in rights_info:
            result.subject.owner = rights_info['owner']
        if 'usage' in rights_info:
            result.subject.usage = rights_info['usage']
        if 'structure' in rights_info:
            result.subject.structure = rights_info['structure']
        if 'land_end_date' in rights_info:
            result.subject.land_end_date = rights_info['land_end_date']

    def _extract_basic_info(self, result: ZujinExtractionResult):
        """提取基础信息表（动态定位）"""
        if self.TABLE_BASIC_INFO >= len(self.tables):
            return

        table = self.tables[self.TABLE_BASIC_INFO]
        table_idx = self.TABLE_BASIC_INFO

        # 1. 动态查找列索引
        col_fields = ['subject', 'case_a', 'case_b', 'case_c']
        col_indices = find_column_indices(table, col_fields, header_row=0)

        # 如果自动检测失败，使用默认值
        if not col_indices or len(col_indices) < 3:
            col_indices = {
                'subject': 2,
                'case_a': 3,
                'case_b': 4,
                'case_c': 5,
            }

        # 2. 动态查找行
        row_indices = find_rows_by_labels(table, self.BASIC_ROW_LABELS, start_row=1, label_col=0)

        # 3. 提取估价对象数据
        subject_col = col_indices.get('subject', 2)
        self._extract_subject_from_basic(result, table, table_idx, row_indices, subject_col)

        # 4. 提取可比实例数据
        case_cols = {
            'A': col_indices.get('case_a', 3),
            'B': col_indices.get('case_b', 4),
            'C': col_indices.get('case_c', 5),
        }

        for case in result.cases:
            col_idx = case_cols.get(case.case_id)
            if col_idx is not None:
                self._extract_case_from_basic(case, table, table_idx, row_indices, col_idx)

    def _extract_subject_from_basic(self, result, table, table_idx, row_indices, col_idx):
        """从基础信息表提取估价对象数据"""
        subject = result.subject

        for field_name, row_idx in row_indices.items():
            if row_idx < 0 or row_idx >= len(table.rows):
                continue

            cells = row_to_text_list(table.rows[row_idx])
            if col_idx >= len(cells):
                continue

            raw_text = cells[col_idx]

            if field_name == 'transaction_date':
                subject.transaction_date = raw_text
            elif field_name == 'floor':
                subject.floor = raw_text

    def _extract_case_from_basic(self, case, table, table_idx, row_indices, col_idx):
        """从基础信息表提取可比实例数据"""
        for field_name, row_idx in row_indices.items():
            if row_idx < 0 or row_idx >= len(table.rows):
                continue

            cells = row_to_text_list(table.rows[row_idx])
            if col_idx >= len(cells):
                continue

            raw_text = cells[col_idx]

            if field_name == 'address':
                case.address = self.create_located_value(raw_text, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'usage':
                case.usage = raw_text
            elif field_name == 'data_source':
                case.data_source = raw_text
            elif field_name == 'rental_price':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_rental_price', Position(table_idx, row_idx, col_idx))
                if value:
                    case.rental_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'building_area':
                area_value, area_unit = parse_area(raw_text)
                if area_value:
                    value = area_value  # 已经统一为平方米
                    if area_unit == 'mu':
                        print(f"     ⚠️ 面积使用亩单位: {raw_text} → {value:.2f}㎡")
                else:
                    value = self.safe_extract_number(
                        raw_text, f'subject_{row_idx}_area',
                        Position(table_idx, row_idx, col_idx)
                    )
                # value = self.safe_extract_number(raw_text, f'{case.case_id}_building_area', Position(table_idx, row_idx, col_idx))
                if value:
                    case.building_area = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'transaction_date':
                case.transaction_date = raw_text
            elif field_name == 'structure':
                case.structure = raw_text
            elif field_name == 'floor':
                case.floor = raw_text
            elif field_name == 'orientation':
                case.orientation = raw_text
            elif field_name == 'build_year':
                year = extract_year(raw_text)
                if year:
                    case.build_year = year
            elif field_name == 'decoration':
                case.decoration = raw_text

    def _extract_factor_descriptions(self, result: ZujinExtractionResult):
        """提取因素描述表"""
        if self.TABLE_FACTOR_DESC >= len(self.tables):
            return

        table = self.tables[self.TABLE_FACTOR_DESC]
        table_idx = self.TABLE_FACTOR_DESC

        COL_CATEGORY = 0
        COL_FACTOR = 1
        COL_SUBJECT = 2
        COL_A = 3
        COL_B = 4
        COL_C = 5

        category_alias = {
            '区位状况': '区位状况',
            '实物状况': '实物状况',
            '实物因素': '实物状况',
            '权益状况': '权益状况',
            '权益因素': '权益状况',
        }

        known_factors = set(self.LOCATION_FACTORS + self.PHYSICAL_FACTORS + self.RIGHTS_FACTORS)
        detected_factor_col = None
        for scan_row_idx in range(1, min(len(table.rows), 10)):
            scan_cells = row_to_text_list(table.rows[scan_row_idx])
            for scan_col_idx, scan_text in enumerate(scan_cells):
                if normalize_label(scan_text) in known_factors:
                    detected_factor_col = scan_col_idx
                    break
            if detected_factor_col is not None:
                break

        if detected_factor_col is not None and detected_factor_col != COL_FACTOR:
            # 列有偏移，重新计算所有列索引
            offset = detected_factor_col - COL_FACTOR
            COL_CATEGORY = max(0, COL_CATEGORY + offset)
            COL_FACTOR = detected_factor_col
            COL_SUBJECT = COL_FACTOR + 1
            COL_A = COL_FACTOR + 2
            COL_B = COL_FACTOR + 3
            COL_C = COL_FACTOR + 4
            print(f"   因素表列偏移修正: factor_col={COL_FACTOR}, offset={offset}")

        current_category = ""

        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = row_to_text_list(row)
            if len(cells) < 3:
                continue

            raw_category = normalize_label(cells[COL_CATEGORY])
            factor_name = normalize_label(cells[COL_FACTOR])

            if raw_category in ('交易情况', '交易日期') or factor_name in ('交易情况', '交易日期'):
                continue

            if raw_category in category_alias:
                current_category = category_alias[raw_category]

            if not factor_name:
                continue

            factor_type = self.classify_factor(factor_name)
            if factor_type == 'unknown':
                if current_category == '区位状况':
                    factor_type = 'location'
                elif current_category == '实物状况':
                    factor_type = 'physical'
                elif current_category == '权益状况':
                    factor_type = 'rights'
                else:
                    continue

            factor_key = self.normalize_factor_name(factor_name)

            # 估价对象
            subject_value = cells[COL_SUBJECT]
            if subject_value:
                factor_dict = getattr(result.subject, f'{factor_type}_factors')
                f = factor_dict.get(factor_key) or Factor(name=factor_key)
                f.description = subject_value
                f.desc_pos = Position(table_idx, row_idx, COL_SUBJECT)
                factor_dict[factor_key] = f

            # 可比实例
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                if col < len(cells):
                    case_value = cells[col]
                    if case_value:
                        factor_dict = getattr(case, f'{factor_type}_factors')
                        f = factor_dict.get(factor_key) or Factor(name=factor_key)
                        f.description = case_value
                        f.desc_pos = Position(table_idx, row_idx, col)
                        factor_dict[factor_key] = f

    def _extract_factor_levels(self, result: ZujinExtractionResult):
        """提取因素等级表"""
        if self.TABLE_FACTOR_LEVEL >= len(self.tables):
            return

        table = self.tables[self.TABLE_FACTOR_LEVEL]
        table_idx = self.TABLE_FACTOR_LEVEL

        COL_CATEGORY = 0
        COL_FACTOR = 1
        COL_SUBJECT = 2
        COL_A = 3
        COL_B = 4
        COL_C = 5

        known_factors = set(self.LOCATION_FACTORS + self.PHYSICAL_FACTORS + self.RIGHTS_FACTORS)
        detected_factor_col = None
        for scan_row_idx in range(1, min(len(table.rows), 10)):
            scan_cells = row_to_text_list(table.rows[scan_row_idx])
            for scan_col_idx, scan_text in enumerate(scan_cells):
                if normalize_label(scan_text) in known_factors:
                    detected_factor_col = scan_col_idx
                    break
            if detected_factor_col is not None:
                break

        if detected_factor_col is not None and detected_factor_col != COL_FACTOR:
            # 列有偏移，重新计算所有列索引
            offset = detected_factor_col - COL_FACTOR
            COL_CATEGORY = max(0, COL_CATEGORY + offset)
            COL_FACTOR = detected_factor_col
            COL_SUBJECT = COL_FACTOR + 1
            COL_A = COL_FACTOR + 2
            COL_B = COL_FACTOR + 3
            COL_C = COL_FACTOR + 4
            print(f"   因素表列偏移修正: factor_col={COL_FACTOR}, offset={offset}")

        current_category = ""

        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = row_to_text_list(row)
            if len(cells) < 3:
                continue

            raw_category = normalize_label(cells[COL_CATEGORY])
            factor_name = normalize_label(cells[COL_FACTOR])

            if raw_category in ('区位状况', '实物状况', '权益状况'):
                current_category = raw_category

            if not factor_name:
                continue

            factor_type = self.classify_factor(factor_name)
            if factor_type == 'unknown':
                if current_category == '区位状况':
                    factor_type = 'location'
                elif current_category == '实物状况':
                    factor_type = 'physical'
                elif current_category == '权益状况':
                    factor_type = 'rights'
                else:
                    continue

            factor_key = self.normalize_factor_name(factor_name)

            # 估价对象
            if COL_SUBJECT < len(cells):
                level = cells[COL_SUBJECT]
                if level:
                    factor_dict = getattr(result.subject, f'{factor_type}_factors')
                    f = factor_dict.get(factor_key) or Factor(name=factor_key)
                    f.level = level
                    f.level_pos = Position(table_idx, row_idx, COL_SUBJECT)
                    factor_dict[factor_key] = f

            # 可比实例
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                if col < len(cells):
                    level = cells[col]
                    if level:
                        factor_dict = getattr(case, f'{factor_type}_factors')
                        f = factor_dict.get(factor_key) or Factor(name=factor_key)
                        f.level = level
                        f.level_pos = Position(table_idx, row_idx, col)
                        factor_dict[factor_key] = f

    def _extract_factor_indices(self, result: ZujinExtractionResult):
        """提取因素指数表"""
        if self.TABLE_FACTOR_INDEX >= len(self.tables):
            return

        table = self.tables[self.TABLE_FACTOR_INDEX]
        table_idx = self.TABLE_FACTOR_INDEX

        COL_CATEGORY = 0
        COL_FACTOR = 1
        COL_SUBJECT = 2
        COL_A = 3
        COL_B = 4
        COL_C = 5

        known_factors = set(self.LOCATION_FACTORS + self.PHYSICAL_FACTORS + self.RIGHTS_FACTORS)
        detected_factor_col = None
        for scan_row_idx in range(1, min(len(table.rows), 10)):
            scan_cells = row_to_text_list(table.rows[scan_row_idx])
            for scan_col_idx, scan_text in enumerate(scan_cells):
                if normalize_label(scan_text) in known_factors:
                    detected_factor_col = scan_col_idx
                    break
            if detected_factor_col is not None:
                break

        if detected_factor_col is not None and detected_factor_col != COL_FACTOR:
            # 列有偏移，重新计算所有列索引
            offset = detected_factor_col - COL_FACTOR
            COL_CATEGORY = max(0, COL_CATEGORY + offset)
            COL_FACTOR = detected_factor_col
            COL_SUBJECT = COL_FACTOR + 1
            COL_A = COL_FACTOR + 2
            COL_B = COL_FACTOR + 3
            COL_C = COL_FACTOR + 4
            print(f"   因素表列偏移修正: factor_col={COL_FACTOR}, offset={offset}")

        def to_int(val):
            try:
                return int(float(val))
            except:
                return 100

        current_category = ""

        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = row_to_text_list(row)
            if len(cells) < 3:
                continue

            raw_category = normalize_label(cells[COL_CATEGORY])
            factor_name = normalize_label(cells[COL_FACTOR])

            if raw_category in ('区位状况', '实物状况', '权益状况'):
                current_category = raw_category

            if not factor_name:
                continue

            factor_type = self.classify_factor(factor_name)
            if factor_type == 'unknown':
                if current_category == '区位状况':
                    factor_type = 'location'
                elif current_category == '实物状况':
                    factor_type = 'physical'
                elif current_category == '权益状况':
                    factor_type = 'rights'
                else:
                    continue

            factor_key = self.normalize_factor_name(factor_name)

            # 估价对象
            if COL_SUBJECT < len(cells):
                value = cells[COL_SUBJECT]
                if value:
                    factor_dict = getattr(result.subject, f'{factor_type}_factors')
                    f = factor_dict.get(factor_key) or Factor(name=factor_key)
                    f.index = to_int(value)
                    f.index_pos = Position(table_idx, row_idx, COL_SUBJECT)
                    factor_dict[factor_key] = f

            # 可比实例
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                if col < len(cells):
                    value = cells[col]
                    if value:
                        factor_dict = getattr(case, f'{factor_type}_factors')
                        f = factor_dict.get(factor_key) or Factor(name=factor_key)
                        f.index = to_int(value)
                        f.index_pos = Position(table_idx, row_idx, col)
                        factor_dict[factor_key] = f

    def _extract_corrections(self, result: ZujinExtractionResult):
        """提取修正系数"""
        if self.TABLE_CORRECTION >= len(self.tables):
            return

        table = self.tables[self.TABLE_CORRECTION]
        table_idx = self.TABLE_CORRECTION

        # 动态查找行
        row_indices = find_rows_by_labels(table, self.CORRECTION_ROW_LABELS, start_row=0, label_col=0)

        # 列索引（A=1, B=2, C=3）
        case_cols = {'A': 1, 'B': 2, 'C': 3}

        for case in result.cases:
            col_idx = case_cols.get(case.case_id)
            if col_idx is None:
                continue

            for field_key in self.CORRECTION_ROW_LABELS.keys():
                row_idx = row_indices.get(field_key, -1)
                if row_idx < 0 or row_idx >= len(table.rows):
                    continue

                cells = row_to_text_list(table.rows[row_idx])
                if col_idx >= len(cells):
                    continue

                raw_text = cells[col_idx]
                value = self.safe_extract_number(
                    raw_text, f'{case.case_id}_{field_key}',
                    Position(table_idx, row_idx, col_idx)
                )

                if value is not None:
                    setattr(case, field_key,
                            self.create_located_value(value, table_idx, row_idx, col_idx, raw_text))

    def _extract_floor_factor(self, result: ZujinExtractionResult):
        """从全文提取楼层修正系数"""
        match = re.search(r'×\s*(\d+)%\s*[＝=]', self.full_text)
        if match:
            result.floor_factor = int(match.group(1)) / 100

    def _extract_extended_info(self, result: ZujinExtractionResult):
        """提取扩展信息"""
        patterns = {
            'build_year': [
                r'建成年代[：:为]*(\d{4})',
                r'(\d{4})年建成',
                r'建于(\d{4})年',
            ],
            'value_date': [
                r'价值时点[：:为]*(\d{4}年\d{1,2}月\d{1,2}日)',
                r'价值时点[：:为]*(\d{4}-\d{1,2}-\d{1,2})',
            ],
            'appraisal_purpose': [
                r'估价目的[：:是为]*(.{5,80}?)(?:。|$)',
                r'本次估价目的是(.{5,80}?)(?:。|$)',
            ],
        }

        extracted = self.extract_from_text(patterns)

        if 'build_year' in extracted:
            year = extract_year(extracted['build_year'])
            if year:
                result.subject.build_year = year
        if 'value_date' in extracted:
            result.subject.value_date = extracted['value_date']
        if 'appraisal_purpose' in extracted:
            result.subject.appraisal_purpose = extracted['appraisal_purpose']

    def _parse_district_info(self, result: ZujinExtractionResult):
        """解析区域信息"""
        address = result.subject.address.value if result.subject.address.value else ''
        district_info = self.parse_district(address)
        result.subject.district = district_info['district']
        result.subject.street = district_info['street']

        # 同步到可比实例
        for case in result.cases:
            case_address = case.address.value if case.address.value else ''
            case_district = self.parse_district(case_address)
            case.district = case_district['district']
            case.street = case_district['street']

    def _parse_floor_info(self, result: ZujinExtractionResult):
        """解析楼层信息"""
        # 估价对象
        if result.subject.floor:
            current, total = parse_floor(result.subject.floor)
            if current:
                result.subject.current_floor = current
            if total:
                try:
                    result.subject.total_floor = int(total)
                except:
                    pass

        # 可比实例
        for case in result.cases:
            if case.floor:
                current, total = parse_floor(case.floor)
                if current:
                    case.current_floor = current
                if total:
                    try:
                        case.total_floor = int(total)
                    except:
                        pass

        if len(result.subjects) > 1:
            all_inferred_floors = []
            for sub in result.subjects:
                addr = sub.address.value if sub.address and sub.address.value else ''
                inferred = infer_floors_from_rooms(addr)
                if inferred:
                    all_inferred_floors.extend(inferred)
                    # 如果 sub.floor 还没赋值，用推断值
                    if not sub.floor:
                        if len(inferred) == 1:
                            sub.floor = str(inferred[0])

            if all_inferred_floors:
                min_f = min(all_inferred_floors)
                max_f = max(all_inferred_floors)
                print(f"   楼层推断: 从房号推断为第{min_f}-{max_f}层")