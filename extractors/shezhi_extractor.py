"""
涉执报告提取器（重构版）
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
from .text_utils import parse_number, normalize_label, extract_year


@dataclass
class Case:
    """可比实例"""
    case_id: str = ""
    address: LocatedValue = field(default_factory=LocatedValue)
    location: str = ""
    usage: str = ""
    data_source: str = ""
    transaction_price: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_date: str = ""

    # 扩展字段
    district: str = ""
    street: str = ""
    build_year: int = 0
    total_floor: int = 0
    current_floor: int = 0
    orientation: str = ""
    decoration: str = ""
    structure: str = ""

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
    unit_price: LocatedValue = field(default_factory=LocatedValue)
    total_price: LocatedValue = field(default_factory=LocatedValue)

    # 扩展字段
    district: str = ""
    street: str = ""
    usage: str = ""
    structure: str = ""
    cert_no: str = ""
    owner: str = ""
    land_end_date: str = ""
    total_floor: int = 0
    current_floor: int = 0
    orientation: str = ""
    decoration: str = ""
    build_year: int = 0
    value_date: str = ""
    appraisal_purpose: str = ""

    # 因素数据
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class ShezhiExtractionResult:
    """涉执报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)

    final_unit_price: LocatedValue = field(default_factory=LocatedValue)
    final_total_price: LocatedValue = field(default_factory=LocatedValue)
    floor_factor: float = 1.0

    type: str = "shezhi"
    stats: ExtractionStats = field(default_factory=ExtractionStats)


class ShezhiExtractor(BaseExtractor):
    """涉执报告提取器"""

    # 需要检测的表格类型
    TABLE_TYPES = ['result_summary', 'property_rights', 'basic_info', 'factor_desc',
                   'factor_level', 'factor_index', 'correction']

    # 基础信息表行标签
    BASIC_ROW_LABELS = {
        'address': ['地址', '坐落'],
        'usage': ['用途', '房屋用途', '规划用途'],
        'data_source': ['来源', '数据来源', '案例来源'],
        'transaction_price': ['交易价格', '成交价格', '交易单价', '成交单价'],
        'building_area': ['建筑面积', '面积'],
        'transaction_date': ['交易时间', '交易日期', '成交日期'],
        'structure': ['结构', '建筑结构'],
        'floor': ['层次', '楼层', '所在层'],
        'orientation': ['朝向', '房屋朝向'],
        'build_year': ['建成年代', '建成时间', '建成年份'],
        'decoration': ['装修', '装修情况'],
    }

    # 修正系数表行标签
    CORRECTION_ROW_LABELS = {
        'transaction_price': ['交易价格', '成交价格'],
        'transaction_correction': ['交易情况修正', '交易情况'],
        'market_correction': ['市场状况修正', '市场状况', '市场状况调整'],
        'location_correction': ['区位状况修正', '区位状况', '区位状况调整'],
        'physical_correction': ['实物状况修正', '实物状况', '实物状况调整'],
        'rights_correction': ['权益状况修正', '权益状况', '权益状况调整'],
        'adjusted_price': ['修正后单价', '调整后单价', '比准价格'],
    }

    def __init__(self, auto_detect: bool = True):
        super().__init__(auto_detect)

        # 备用硬编码索引
        self.TABLE_RESULT_SUMMARY = 0
        self.TABLE_PROPERTY_RIGHTS = 2
        self.TABLE_BASIC_INFO = 5
        self.TABLE_FACTOR_DESC = 6
        self.TABLE_FACTOR_LEVEL = 7
        self.TABLE_FACTOR_INDEX = 8
        self.TABLE_FACTOR_RATIO = 9
        self.TABLE_CORRECTION = 10

    def extract(self, doc_path: str) -> ShezhiExtractionResult:
        """提取涉执报告"""
        # 1. 加载文档
        self.load_document(doc_path)

        result = ShezhiExtractionResult(
            source_file=os.path.basename(doc_path)
        )

        print(f"\n📊 提取涉执报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")

        # 2. 更新表格索引
        self._update_table_indices()
        print(f"   表格索引: 汇总={self.TABLE_RESULT_SUMMARY}, 权属={self.TABLE_PROPERTY_RIGHTS}, "
              f"基础={self.TABLE_BASIC_INFO}, 修正={self.TABLE_CORRECTION}")

        # 3. 初始化3个可比实例
        result.cases = [Case(case_id=c) for c in ['A', 'B', 'C']]

        # 4. 提取各表格数据
        self._extract_result_summary(result)
        print(f"   ✓ 结果汇总: {result.subject.address.value}")

        self._extract_property_rights(result)
        print(f"   ✓ 权属信息: {result.subject.cert_no}")

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

        # 兜底：基于基础信息表推算其他表格位置
        if self.TABLE_BASIC_INFO > 0:
            base = self.TABLE_BASIC_INFO
            if 'factor_desc' not in self.table_indices:
                self.TABLE_FACTOR_DESC = min(base + 1, len(self.tables) - 1)
            if 'factor_level' not in self.table_indices:
                self.TABLE_FACTOR_LEVEL = min(base + 2, len(self.tables) - 1)
            if 'factor_index' not in self.table_indices:
                self.TABLE_FACTOR_INDEX = min(base + 3, len(self.tables) - 1)
            if 'correction' not in self.table_indices:
                self.TABLE_CORRECTION = min(base + 5, len(self.tables) - 1)

    def _extract_result_summary(self, result: ShezhiExtractionResult):
        """提取结果汇总表"""
        if self.TABLE_RESULT_SUMMARY >= len(self.tables):
            return

        table = self.tables[self.TABLE_RESULT_SUMMARY]
        table_idx = self.TABLE_RESULT_SUMMARY

        # 通常第二行是数据行
        if len(table.rows) >= 2:
            cells = get_row_cells_simple(table.rows[1])

            # 地址
            if len(cells) >= 1 and cells[0]:
                result.subject.address = self.create_located_value(
                    cells[0], table_idx, 1, 0, cells[0]
                )

            # 建筑面积
            if len(cells) >= 2:
                value = self.safe_extract_number(cells[1], 'building_area', Position(table_idx, 1, 1))
                if value:
                    result.subject.building_area = self.create_located_value(value, table_idx, 1, 1, cells[1])

            # 单价
            if len(cells) >= 3:
                value = self.safe_extract_number(cells[2], 'unit_price', Position(table_idx, 1, 2))
                if value:
                    result.subject.unit_price = self.create_located_value(value, table_idx, 1, 2, cells[2])
                    result.final_unit_price = result.subject.unit_price

            # 总价
            if len(cells) >= 4:
                total_text = cells[3]
                value = self.safe_extract_number(total_text, 'total_price', Position(table_idx, 1, 3))
                if value:
                    result.subject.total_price = self.create_located_value(value, table_idx, 1, 3, total_text)
                    result.final_total_price = result.subject.total_price

    def _extract_property_rights(self, result: ShezhiExtractionResult):
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

    def _extract_basic_info(self, result: ShezhiExtractionResult):
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

        # 3. 提取可比实例数据
        case_cols = {
            'A': col_indices.get('case_a', 3),
            'B': col_indices.get('case_b', 4),
            'C': col_indices.get('case_c', 5),
        }

        for case in result.cases:
            col_idx = case_cols.get(case.case_id)
            if col_idx is not None:
                self._extract_case_from_basic(case, table, table_idx, row_indices, col_idx)

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
            elif field_name == 'transaction_price':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_transaction_price', Position(table_idx, row_idx, col_idx))
                if value:
                    case.transaction_price = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'building_area':
                value = self.safe_extract_number(raw_text, f'{case.case_id}_building_area', Position(table_idx, row_idx, col_idx))
                if value:
                    case.building_area = self.create_located_value(value, table_idx, row_idx, col_idx, raw_text)
            elif field_name == 'transaction_date':
                case.transaction_date = raw_text
            elif field_name == 'structure':
                case.structure = raw_text
            elif field_name == 'floor':
                self._parse_floor_int(case, raw_text)
            elif field_name == 'orientation':
                case.orientation = raw_text
            elif field_name == 'build_year':
                year = extract_year(raw_text)
                if year:
                    case.build_year = year
            elif field_name == 'decoration':
                case.decoration = raw_text

    def _extract_factor_descriptions(self, result: ShezhiExtractionResult):
        """提取因素描述表"""
        if self.TABLE_FACTOR_DESC >= len(self.tables):
            return

        table = self.tables[self.TABLE_FACTOR_DESC]
        table_idx = self.TABLE_FACTOR_DESC

        # 列索引
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

            # 跳过交易类
            if raw_category in ('交易情况', '交易日期') or factor_name in ('交易情况', '交易日期'):
                continue

            # 更新分类
            if raw_category in category_alias:
                current_category = category_alias[raw_category]

            if not factor_name:
                continue

            # 确定因素类型
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

    def _extract_factor_levels(self, result: ShezhiExtractionResult):
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

    def _extract_factor_indices(self, result: ShezhiExtractionResult):
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

    def _extract_corrections(self, result: ShezhiExtractionResult):
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

            for field_key, attr_name in self.CORRECTION_ROW_LABELS.items():
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
                    # 将行标签映射到属性名
                    setattr(case, field_key,
                            self.create_located_value(value, table_idx, row_idx, col_idx, raw_text))

    def _extract_floor_factor(self, result: ShezhiExtractionResult):
        """从全文提取楼层修正系数"""
        match = re.search(r'×\s*(\d+)%\s*[＝=]', self.full_text)
        if match:
            result.floor_factor = int(match.group(1)) / 100

    def _extract_extended_info(self, result: ShezhiExtractionResult):
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

    def _parse_district_info(self, result: ShezhiExtractionResult):
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

    def _parse_floor_int(self, case, text):
        """解析楼层为整数"""
        if not text:
            return

        try:
            # 尝试提取数字
            match = re.search(r'(\d+)', text)
            if match:
                case.current_floor = int(match.group(1))
        except:
            pass