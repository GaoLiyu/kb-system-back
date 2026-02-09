"""
标准房报告提取器（重构版）
==========================
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
from .text_utils import parse_number, normalize_label, extract_year


@dataclass
class Case:
    """可比实例"""
    case_id: str = ""
    address: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_price: LocatedValue = field(default_factory=LocatedValue)
    avg_listing_price: LocatedValue = field(default_factory=LocatedValue)

    # 基本信息
    data_source: str = ""
    structure: str = ""
    current_floor: str = ""
    total_floor: str = ""
    orientation: str = ""
    build_year: str = ""
    transaction_date: str = ""

    # 修正系数（百分比形式，如108表示1.08）
    structure_factor: LocatedValue = field(default_factory=LocatedValue)
    floor_factor: LocatedValue = field(default_factory=LocatedValue)
    orientation_factor: LocatedValue = field(default_factory=LocatedValue)
    age_factor: LocatedValue = field(default_factory=LocatedValue)
    east_west_factor: LocatedValue = field(default_factory=LocatedValue)
    physical_composite: LocatedValue = field(default_factory=LocatedValue)

    # P系数（字符串，因为可能是"不修正"或"108/103"）
    p1_transaction: str = ""
    p2_date: str = ""
    p3_physical: str = ""
    p4_location: str = ""

    # 计算结果
    composite_result: LocatedValue = field(default_factory=LocatedValue)
    vs_result: LocatedValue = field(default_factory=LocatedValue)
    decoration_price: LocatedValue = field(default_factory=LocatedValue)
    attachment_price: LocatedValue = field(default_factory=LocatedValue)
    final_price: LocatedValue = field(default_factory=LocatedValue)


@dataclass
class Subject:
    """估价对象"""
    address: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    unit_price: LocatedValue = field(default_factory=LocatedValue)
    total_price: LocatedValue = field(default_factory=LocatedValue)

    # 基本信息
    district: str = ""
    street: str = ""
    structure: str = ""
    current_floor: str = ""
    total_floor: str = ""
    orientation: str = ""
    build_year: str = ""
    usage: str = ""
    cert_no: str = ""
    owner: str = ""
    property_type: str = ""
    transaction_date: str = ""
    location_code: str = ""
    east_to_west: str = ""
    appendages: str = ""
    avg_listing_price: LocatedValue = field(default_factory=LocatedValue)

    # 修正系数
    structure_factor: LocatedValue = field(default_factory=LocatedValue)
    floor_factor: LocatedValue = field(default_factory=LocatedValue)
    orientation_factor: LocatedValue = field(default_factory=LocatedValue)
    age_factor: LocatedValue = field(default_factory=LocatedValue)
    east_west_factor: LocatedValue = field(default_factory=LocatedValue)
    physical_composite: LocatedValue = field(default_factory=LocatedValue)

    appraisal_purpose: str = ""


@dataclass
class BiaozhunfangExtractionResult:
    """标准房报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)
    final_price: LocatedValue = field(default_factory=LocatedValue)
    type: str = "biaozhunfang"
    stats: ExtractionStats = field(default_factory=ExtractionStats)


class BiaozhunfangExtractor(BaseExtractor):
    """标准房报告提取器"""

    # 需要检测的表格类型
    TABLE_TYPES = ['result_summary', 'biaozhunfang_main', 'biaozhunfang_detail', 'biaozhunfang_correction']

    # 主信息表行标签
    MAIN_ROW_LABELS = {
        'address': ['地址', '坐落'],
        'data_source': ['案例来源', '来源'],
        'building_area': ['建筑面积', '面积'],
        'structure': ['结构', '建筑结构'],
        'floor': ['层次', '楼层', '所在层'],
        'orientation': ['朝向', '房屋朝向'],
        'build_year': ['建成时间', '建成年份', '建成年代'],
        'transaction_date': ['交易时间', '交易日期', '成交日期', '价值时点'],
        'transaction_price': ['交易单价', '交易价格', '成交价格', '成交单价'],
        'avg_listing_price': ['二手房挂牌均价', '挂牌均价'],
    }

    # 详细因素表行标签
    DETAIL_ROW_LABELS = {
        'structure_factor': ['结构修正系数', '结构系数', '结构修正'],
        'floor_factor': ['层次修正系数', '层次系数', '楼层修正'],
        'orientation_factor': ['朝向修正系数', '朝向系数', '朝向修正'],
        'age_factor': ['成新修正系数', '成新系数', '成新修正'],
        'east_west_factor': ['东西至修正系数', '东西至修正', '东西至'],
        'physical_composite': ['实体状况系数综合', '实体状况综合', '实体综合'],
    }

    # 修正计算表行标签
    CORRECTION_ROW_LABELS = {
        'p1': ['P1', 'P1交易', '交易情况修正'],
        'p2': ['P2', 'P2交易日期', '交易日期修正'],
        'p3': ['P3', 'P3实体', '实体状况修正'],
        'p4': ['P4', 'P4区位', '区位状况修正'],
        'composite': ['P1×P2×P3×P4', '综合修正', '修正系数综合'],
        'vs_result': ['Vs×', 'Vs结果', 'Vs×结果'],
        'decoration': ['装修', '装修价格', '装修重置价', '装修档次', '装饰装修', 'Vb', '装修单价'],
        'attachment': ['附属物', '附属物价格', '附属物单价', 'Va', '附属设施', '附属物单价修正'],
        'final': ['比准价格', '最终价格', '评估单价'],
    }

    def __init__(self, auto_detect: bool = True):
        super().__init__(auto_detect)

        # 备用硬编码索引（当自动检测失败时使用）
        self.TABLE_RESULT_SUMMARY = 2
        self.TABLE_MAIN_INFO = 6
        self.TABLE_DETAIL = 19
        self.TABLE_CORRECTION = 20

    def extract(self, doc_path: str) -> BiaozhunfangExtractionResult:
        """提取标准房报告"""
        # 1. 加载文档
        self.load_document(doc_path)

        result = BiaozhunfangExtractionResult(
            source_file=os.path.basename(doc_path)
        )

        print(f"\n📊 提取标准房报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")

        # 2. 更新表格索引（优先使用自动检测结果）
        self._update_table_indices()
        print(f"   表格索引: 汇总={self.TABLE_RESULT_SUMMARY}, 主表={self.TABLE_MAIN_INFO}, "
              f"详细={self.TABLE_DETAIL}, 修正={self.TABLE_CORRECTION}")

        # 3. 初始化4个可比实例
        result.cases = [Case(case_id=c) for c in ['A', 'B', 'C', 'D']]

        # 4. 提取各表格数据
        self._extract_result_summary(result)
        print(f"   ✓ 结果汇总表")

        self._extract_main_table(result)
        print(f"   ✓ 主要信息表")

        self._extract_detail_table(result)
        print(f"   ✓ 详细因素表")

        self._extract_correction_table(result)
        print(f"   ✓ 修正计算表")

        self._extract_extended_info(result)
        print(f"   ✓ 扩展信息")

        self._parse_district_info(result)
        print(f"   ✓ 区域信息: {result.subject.district}")

        # 5. 记录统计
        result.stats = self.stats

        return result

    def _update_table_indices(self):
        """更新表格索引（优先使用自动检测结果）"""
        if 'result_summary' in self.table_indices:
            self.TABLE_RESULT_SUMMARY = self.table_indices['result_summary']
        if 'biaozhunfang_main' in self.table_indices:
            self.TABLE_MAIN_INFO = self.table_indices['biaozhunfang_main']
        if 'biaozhunfang_detail' in self.table_indices:
            self.TABLE_DETAIL = self.table_indices['biaozhunfang_detail']
        if 'biaozhunfang_correction' in self.table_indices:
            self.TABLE_CORRECTION = self.table_indices['biaozhunfang_correction']

    def _extract_result_summary(self, result: BiaozhunfangExtractionResult):
        """提取结果汇总表"""
        if self.TABLE_RESULT_SUMMARY >= len(self.tables):
            return

        table = self.tables[self.TABLE_RESULT_SUMMARY]
        table_idx = self.TABLE_RESULT_SUMMARY

        # 查找包含单价/总价的行
        for row_idx, row in enumerate(table.rows):
            cells = get_row_cells_simple(row)
            row_text = ' '.join(cells)
            row_text_normalized = normalize_label(row_text)

            for col_idx, cell_text in enumerate(cells):
                cell_normalized = normalize_label(cell_text)

                # 单价
                if '单价' in cell_normalized and col_idx + 1 < len(cells):
                    value = self.safe_extract_number(
                        cells[col_idx + 1], 'unit_price',
                        Position(table_idx, row_idx, col_idx + 1)
                    )
                    if value:
                        result.subject.unit_price = self.create_located_value(
                            value, table_idx, row_idx, col_idx + 1, cells[col_idx + 1]
                        )

                # 总价
                if '总价' in cell_normalized and col_idx + 1 < len(cells):
                    value = self.safe_extract_number(
                        cells[col_idx + 1], 'total_price',
                        Position(table_idx, row_idx, col_idx + 1)
                    )
                    if value:
                        result.subject.total_price = self.create_located_value(
                            value, table_idx, row_idx, col_idx + 1, cells[col_idx + 1]
                        )

    def _extract_main_table(self, result: BiaozhunfangExtractionResult):
        """提取主要信息表（动态定位）"""
        if self.TABLE_MAIN_INFO >= len(self.tables):
            return

        table = self.tables[self.TABLE_MAIN_INFO]
        table_idx = self.TABLE_MAIN_INFO

        # 1. 动态查找列索引
        col_fields = ['subject', 'case_a', 'case_b', 'case_c', 'case_d']
        col_indices = find_column_indices(table, col_fields, header_row=0)

        # 如果自动检测失败，使用默认值
        if not col_indices or len(col_indices) < 3:
            col_indices = {
                'subject': 3,
                'case_a': 4,
                'case_b': 5,
                'case_c': 6,
                'case_d': 7,
            }

        # 2. 动态查找行
        row_indices = find_rows_by_labels(table, self.MAIN_ROW_LABELS, start_row=1, label_col=0)

        # 3. 提取估价对象数据
        subject_col = col_indices.get('subject', 3)
        self._extract_subject_from_main(result, table, table_idx, row_indices, subject_col)

        # 4. 提取可比实例数据
        case_cols = {
            'A': col_indices.get('case_a', 4),
            'B': col_indices.get('case_b', 5),
            'C': col_indices.get('case_c', 6),
            'D': col_indices.get('case_d', 7),
        }

        for case in result.cases:
            col_idx = case_cols.get(case.case_id)
            if col_idx is not None:
                self._extract_case_from_main(case, table, table_idx, row_indices, col_idx)

    def _extract_subject_from_main(self, result, table, table_idx, row_indices, col_idx):
        """从主信息表提取估价对象数据"""
        subject = result.subject

        for field_name, row_idx in row_indices.items():
            if row_idx < 0 or row_idx >= len(table.rows):
                continue

            cells = row_to_text_list(table.rows[row_idx])
            if col_idx >= len(cells):
                continue

            raw_text = cells[col_idx]

            if field_name == 'address':
                subject.address = self.create_located_value(raw_text, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'building_area':
                value = self.safe_extract_number(raw_text, 'subject_building_area', Position(table_idx, row_idx, col_idx))
                if value:
                    subject.building_area = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'structure':
                subject.structure = raw_text
            elif field_name == 'floor':
                self._parse_floor_text(subject, raw_text)
            elif field_name == 'orientation':
                subject.orientation = raw_text
            elif field_name == 'build_year':
                subject.build_year = raw_text
            elif field_name == 'transaction_date':
                subject.transaction_date = raw_text
            elif field_name == 'transaction_price':
                value = self.safe_extract_number(raw_text, 'subject_transaction_price', Position(table_idx, row_idx, col_idx))
                if value:
                    subject.unit_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'avg_listing_price':
                value = self.safe_extract_number(raw_text, 'subject_avg_listing_price', Position(table_idx, row_idx, col_idx))
                if value:
                    subject.avg_listing_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)

    def _extract_case_from_main(self, case, table, table_idx, row_indices, col_idx):
        """从主信息表提取可比实例数据"""
        for field_name, row_idx in row_indices.items():
            if row_idx < 0 or row_idx >= len(table.rows):
                continue

            cells = row_to_text_list(table.rows[row_idx])
            if col_idx >= len(cells):
                continue

            raw_text = cells[col_idx]

            if field_name == 'address':
                case.address = self.create_located_value(raw_text, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'data_source':
                case.data_source = raw_text
            elif field_name == 'building_area':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_building_area', Position(table_idx, row_idx, col_idx))
                if value:
                    case.building_area = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'structure':
                case.structure = raw_text
            elif field_name == 'floor':
                self._parse_floor_text_case(case, raw_text)
            elif field_name == 'orientation':
                case.orientation = raw_text
            elif field_name == 'build_year':
                case.build_year = raw_text
            elif field_name == 'transaction_date':
                case.transaction_date = raw_text
            elif field_name == 'transaction_price':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_transaction_price', Position(table_idx, row_idx, col_idx))
                if value:
                    case.transaction_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'avg_listing_price':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_avg_listing_price', Position(table_idx, row_idx, col_idx))
                if value:
                    case.avg_listing_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)

    def _extract_detail_table(self, result: BiaozhunfangExtractionResult):
        """提取详细因素表"""
        if self.TABLE_DETAIL >= len(self.tables):
            return

        table = self.tables[self.TABLE_DETAIL]
        table_idx = self.TABLE_DETAIL

        # 动态查找行
        row_indices = find_rows_by_labels(table, self.DETAIL_ROW_LABELS, start_row=1, label_col=0)

        # 列索引（估价对象在第1列，A/B/C/D在2/3/4/5列）
        subject_col = 1
        case_cols = {'A': 2, 'B': 3, 'C': 4, 'D': 5}

        # 提取估价对象的修正系数
        for field_name, row_idx in row_indices.items():
            if row_idx < 0 or row_idx >= len(table.rows):
                continue

            cells = row_to_text_list(table.rows[row_idx])

            # 估价对象
            if subject_col < len(cells):
                raw_text = cells[subject_col]
                # 修正系数是百分比形式
                value = self.safe_extract_number(
                    raw_text, f'subject_{field_name}',
                    Position(table_idx, row_idx, subject_col),
                    is_percentage=True
                )
                if value:
                    setattr(result.subject, field_name,
                            self.create_located_value(value, table_idx, row_idx, subject_col, raw_text))

            # 可比实例
            for case in result.cases:
                col_idx = case_cols.get(case.case_id)
                if col_idx is None or col_idx >= len(cells):
                    continue

                raw_text = cells[col_idx]
                # 可比实例的系数保持原值（如108），不转换为小数
                value = self.safe_extract_number(
                    raw_text, f'{case.case_id}_{field_name}',
                    Position(table_idx, row_idx, col_idx)
                )
                if value:
                    setattr(case, field_name,
                            self.create_located_value(value, table_idx, row_idx, col_idx, raw_text))

    def _extract_correction_table(self, result: BiaozhunfangExtractionResult):
        """提取修正计算表（动态定位）"""
        if self.TABLE_CORRECTION >= len(self.tables):
            return

        table = self.tables[self.TABLE_CORRECTION]
        table_idx = self.TABLE_CORRECTION

        # 动态查找行
        row_indices = find_rows_by_labels(table, self.CORRECTION_ROW_LABELS, start_row=0, label_col=0)

        # 列索引（A=1, B=2, C=3, D=4）
        case_cols = {}
        if len(table.rows) > 0:
            header_cells = row_to_text_list(table.rows[0])
            for col_idx, cell_text in enumerate(header_cells):
                text = normalize_label(cell_text)
                if '可比实例A' in text or text == 'A' or '实例A' in text:
                    case_cols['A'] = col_idx
                elif '可比实例B' in text or text == 'B' or '实例B' in text:
                    case_cols['B'] = col_idx
                elif '可比实例C' in text or text == 'C' or '实例C' in text:
                    case_cols['C'] = col_idx
                elif '可比实例D' in text or text == 'D' or '实例D' in text:
                    case_cols['D'] = col_idx

        # 如果没检测到，尝试用数据行第一行推断
        if len(case_cols) < 4:
            # 回退：假设标签列后面依次是 A B C D
            # 先找到标签列宽度（第一个有数据的非标签列）
            case_cols = {'A': 1, 'B': 2, 'C': 3, 'D': 4}

        print(f"   修正计算表列索引: {case_cols}")

        for case in result.cases:
            col_idx = case_cols.get(case.case_id)
            if col_idx is None:
                continue

            # P1-P4（保存为字符串）
            for p_field, attr_name in [('p1', 'p1_transaction'), ('p2', 'p2_date'),
                                        ('p3', 'p3_physical'), ('p4', 'p4_location')]:
                row_idx = row_indices.get(p_field, -1)
                if row_idx >= 0 and row_idx < len(table.rows):
                    cells = row_to_text_list(table.rows[row_idx])
                    if col_idx < len(cells):
                        setattr(case, attr_name, cells[col_idx])

            # 数值字段
            numeric_mappings = [
                ('composite', 'composite_result'),
                ('vs_result', 'vs_result'),
                ('decoration', 'decoration_price'),
                ('attachment', 'attachment_price'),
                ('final', 'final_price'),
            ]

            for field_key, attr_name in numeric_mappings:
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
                    setattr(case, attr_name,
                            self.create_located_value(value, table_idx, row_idx, col_idx, raw_text))

        for case in result.cases:
            p1 = getattr(case, 'p1_transaction', None)
            p2 = getattr(case, 'p2_date', None)
            p3 = getattr(case, 'p3_physical', None)
            p4 = getattr(case, 'p4_location', None)
            va = getattr(case, 'attachment_price', None)
            vb = getattr(case, 'decoration_price', None)
            fp = getattr(case, 'final_price', None)
            va_val = va.value if hasattr(va, 'value') and va else va
            vb_val = vb.value if hasattr(vb, 'value') and vb else vb
            fp_val = fp.value if hasattr(fp, 'value') and fp else fp
            print(f"   Case {case.case_id}: P1={p1}, P2={p2}, P3={p3}, P4={p4}, "
                  f"Va={va_val}, Vb={vb_val}, Final={fp_val}")

    def _extract_extended_info(self, result: BiaozhunfangExtractionResult):
        """从全文提取扩展信息"""
        patterns = {
            'appraisal_purpose': [
                r'估价目的[：:是为]*(.{5,80}?)(?:。|$)',
                r'本次估价目的是(.{5,80}?)(?:。|$)',
            ],
            'value_date': [
                r'价值时点[：:为]*(\d{4}年\d{1,2}月\d{1,2}日)',
                r'价值时点[：:为]*(\d{4}-\d{1,2}-\d{1,2})',
            ],
        }

        if not (result.subject.total_price and
                hasattr(result.subject.total_price, 'value') and
                result.subject.total_price.value):
            total_price_patterns = [
                r'评估总价[为：:]\s*([\d,.]+)\s*万?\s*元',
                r'估价结果[为：:]\s*([\d,.]+)\s*万?\s*元',
                r'市场价值[为：:]\s*(?:人民币)?\s*([\d,.]+)\s*万?\s*元',
                r'总价[为：:]\s*([\d,.]+)\s*万?\s*元',
            ]
            for pattern in total_price_patterns:
                match = re.search(pattern, self.full_text)
                if match:
                    price_str = match.group(1).replace(',', '')
                    try:
                        value = float(price_str)
                        # 判断是否万元
                        matched_text = match.group(0)
                        if '万' in matched_text:
                            value = value * 10000
                        result.subject.total_price = self.create_located_value(
                            value, -1, -1, -1, match.group(0)
                        )
                        print(f"   从全文提取总价: {match.group(0)} → {value}")
                    except ValueError:
                        pass
                    break

        extracted = self.extract_from_text(patterns)

        if 'appraisal_purpose' in extracted:
            result.subject.appraisal_purpose = extracted['appraisal_purpose']
        if 'value_date' in extracted:
            result.subject.transaction_date = extracted['value_date']

    def _parse_district_info(self, result: BiaozhunfangExtractionResult):
        """解析区域信息"""
        address = result.subject.address.value if result.subject.address.value else ''
        district_info = self.parse_district(address)
        result.subject.district = district_info['district']
        result.subject.street = district_info['street']

    def _parse_floor_text(self, subject, text):
        """解析楼层文本（估价对象）"""
        if not text or text == '/':
            subject.current_floor = '0'
            subject.total_floor = '0'
            return

        if '/' in text:
            parts = text.split('/')
            subject.current_floor = parts[0].strip()
            subject.total_floor = parts[1].strip() if len(parts) > 1 else ''
        else:
            subject.current_floor = text.strip()
            subject.total_floor = ''

    def _parse_floor_text_case(self, case, text):
        """解析楼层文本（可比实例）"""
        if not text or text == '/':
            case.current_floor = '0'
            case.total_floor = '0'
            return

        if '/' in text:
            parts = text.split('/')
            case.current_floor = parts[0].strip()
            case.total_floor = parts[1].strip() if len(parts) > 1 else ''
        else:
            case.current_floor = text.strip()
            case.total_floor = ''