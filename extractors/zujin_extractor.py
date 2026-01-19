"""
租金报告精确提取器
==================
针对租金报告的表格结构精确提取
表格索引（基于分析结果）：
- 表格0/2/9: 结果汇总表（坐落、评估面积、评估单价、评估总价）
- 表格1: 权属表
- 表格4: 基础信息表
- 表格5: 因素描述表
- 表格6: 因素等级表
- 表格7: 因素指数表（注意：表头是"案例A/B/C"而不是"可比实例"）
- 表格8: 修正计算表
"""

import os
import re
from typing import Dict, List
from docx import Document
from dataclasses import dataclass, field


@dataclass
class Position:
    """位置信息"""
    table_index: int = -1
    row_index: int = -1
    col_index: int = -1


@dataclass
class LocatedValue:
    """带位置的值"""
    value: any = None
    position: Position = field(default_factory=Position)
    raw_text: str = ""


@dataclass
class Factor:
    """因素数据"""
    name: str = ""
    description: str = ""
    level: str = ""
    index: int = 100
    desc_pos: Position = field(default_factory=Position)
    level_pos: Position = field(default_factory=Position)
    index_pos: Position = field(default_factory=Position)


@dataclass
class Case:
    """可比实例"""
    case_id: str = ""
    address: LocatedValue = field(default_factory=LocatedValue)
    location: str = ""
    usage: str = ""
    data_source: str = ""
    rental_price: LocatedValue = field(default_factory=LocatedValue)  # 租赁价格
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_date: str = ""
    
    # 新增字段
    district: str = ""           # 区域
    street: str = ""             # 街道/镇
    build_year: int = 0          # 建成年份
    total_floor: int = 0         # 总楼层
    current_floor: int = 0       # 所在楼层
    structure: str = ""          # 结构
    orientation: str = ""        # 朝向
    decoration: str = ""         # 装修
    
    # 修正系数
    transaction_correction: LocatedValue = field(default_factory=LocatedValue)
    market_correction: LocatedValue = field(default_factory=LocatedValue)
    location_correction: LocatedValue = field(default_factory=LocatedValue)
    physical_correction: LocatedValue = field(default_factory=LocatedValue)
    rights_correction: LocatedValue = field(default_factory=LocatedValue)
    adjusted_price: LocatedValue = field(default_factory=LocatedValue)
    
    # 因素
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class Subject:
    """估价对象"""
    address: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    unit_price: LocatedValue = field(default_factory=LocatedValue)  # 元/㎡·年
    total_price: LocatedValue = field(default_factory=LocatedValue)  # 万元/年
    usage: str = ""
    
    # 新增字段
    district: str = ""           # 区域
    street: str = ""             # 街道/镇
    build_year: int = 0          # 建成年份
    total_floor: int = 0         # 总楼层
    current_floor: int = 0       # 所在楼层
    structure: str = ""          # 结构
    orientation: str = ""        # 朝向
    decoration: str = ""         # 装修
    value_date: str = ""         # 价值时点
    appraisal_purpose: str = ""  # 估价目的
    
    # 因素
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class ZujinExtractionResult:
    """租金报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)
    
    final_unit_price: LocatedValue = field(default_factory=LocatedValue)
    final_total_price: LocatedValue = field(default_factory=LocatedValue)
    price_unit: str = "元/㎡·年"


class ZujinExtractor:
    """租金报告提取器"""
    
    # 表格索引
    TABLE_RESULT_SUMMARY = 0
    TABLE_PROPERTY_RIGHTS = 1
    TABLE_BASIC_INFO = 4
    TABLE_FACTOR_DESC = 5
    TABLE_FACTOR_LEVEL = 6
    TABLE_FACTOR_INDEX = 7
    TABLE_CORRECTION = 8
    
    # 因素名称（租金报告特有的因素）
    LOCATION_FACTORS = ['繁华程度', '区域位置', '楼幢位置', '朝向', '交通条件', '配套设施', '环境质量', '景观',
                        '物业管理', '驻车条件']
    PHYSICAL_FACTORS = ['建筑面积', '套内建筑面积', '空间布局', '新旧程度', '装饰装修', '建筑结构', '建筑结构',
                        '物业类型', '设施设备', '楼宇等级', '地形地势', '地质土壤', '开发程度']
    RIGHTS_FACTORS = ['规划条件', '土地使用期限', '土地剩余使用年限', '担保物权设立', '租赁占用状况', '拖欠税费状况',
                      '登记状况', '他项权利', '限制权利', '其他因素']
    
    def __init__(self):
        self.doc = None
        self.tables = []
    
    def extract(self, doc_path: str) -> ZujinExtractionResult:
        """提取租金报告"""
        self.doc = Document(doc_path)
        self.tables = self.doc.tables
        
        result = ZujinExtractionResult(source_file=os.path.basename(doc_path))
        
        print(f"\n📊 提取租金报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")
        
        # 1. 提取结果汇总
        self._extract_result_summary(result)
        print(f"   ✓ 结果汇总: {result.subject.address.value}")

        # 1.1 提取权属信息（表1）
        self._extract_property_rights(result)
        
        # 2. 提取基础信息
        self._extract_basic_info(result)
        print(f"   ✓ 基础信息: {len(result.cases)}个可比实例")
        
        # 3. 提取因素描述
        self._extract_factor_descriptions(result)
        
        # 4. 提取因素等级
        self._extract_factor_levels(result)
        
        # 5. 提取因素指数
        self._extract_factor_indices(result)
        print(f"   ✓ 因素数据: 描述/等级/指数")
        
        # 6. 提取修正系数
        self._extract_corrections(result)
        print(f"   ✓ 修正系数")
        
        return result
    
    def _extract_result_summary(self, result: ZujinExtractionResult):
        """提取结果汇总表（支持有/无楼层列）"""
        table = self.tables[self.TABLE_RESULT_SUMMARY]

        if len(table.rows) >= 2:
            # 检查表头是否有楼层列
            header = [c.text.strip() for c in table.rows[0].cells]
            has_floor_col = any('楼层' in h for h in header)

            row = table.rows[1]
            cells = [c.text.strip() for c in row.cells]

            # 根据是否有楼层列调整索引
            # 有楼层列: 坐落=0, 楼层=1, 面积=2, 单价=3, 总价=4
            # 无楼层列: 坐落=0, 面积=1, 单价=2, 总价=3
            if has_floor_col:
                col_address = 0
                col_floor = 1
                col_area = 2
                col_unit_price = 3
                col_total_price = 4
            else:
                col_address = 0
                col_floor = -1  # 不存在
                col_area = 1
                col_unit_price = 2
                col_total_price = 3

            # 提取地址
            if len(cells) > col_address:
                result.subject.address = LocatedValue(
                    value=cells[col_address],
                    position=Position(self.TABLE_RESULT_SUMMARY, 1, col_address),
                    raw_text=cells[col_address]
                )

            # 提取楼层（如果存在）
            if has_floor_col and len(cells) > col_floor:
                floor_text = cells[col_floor]
                # 解析楼层 "1/2" 格式
                if '/' in floor_text:
                    parts = floor_text.split('/')
                    if len(parts) == 2:
                        try:
                            result.subject.current_floor = int(parts[0])
                            result.subject.total_floor = int(parts[1])
                        except:
                            pass

            # 提取面积
            if len(cells) > col_area:
                try:
                    result.subject.building_area = LocatedValue(
                        value=float(cells[col_area]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, col_area),
                        raw_text=cells[col_area]
                    )
                except:
                    pass

            # 提取单价
            if len(cells) > col_unit_price:
                try:
                    result.subject.unit_price = LocatedValue(
                        value=float(cells[col_unit_price]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, col_unit_price),
                        raw_text=cells[col_unit_price]
                    )
                    result.final_unit_price = result.subject.unit_price
                except:
                    pass

            # 提取总价
            if len(cells) > col_total_price:
                try:
                    result.subject.total_price = LocatedValue(
                        value=float(cells[col_total_price]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, col_total_price),
                        raw_text=cells[col_total_price]
                    )
                    result.final_total_price = result.subject.total_price
                except:
                    pass

    def _extract_property_rights(self, result: ZujinExtractionResult):
        """提取权属表（表1）

        说明：不改变输出结构，只补充 Subject 里已有字段：
        - address / building_area / structure / current_floor / total_floor / usage(如有)
        """
        if len(self.tables) <= self.TABLE_PROPERTY_RIGHTS:
            return
        table = self.tables[self.TABLE_PROPERTY_RIGHTS]
        if len(table.rows) < 3:
            return

        # 表1通常：第1行是表头，第2行是字段名，第3行是值
        row = table.rows[2]
        cells = [c.text.strip().replace('\\n', ' ') for c in row.cells]
        if len(cells) < 7:
            return

        # 0证号 1权利人 2坐落 3结构 4楼层 5面积 6用途
        addr = cells[2]
        if addr and not result.subject.address.value:
            result.subject.address = LocatedValue(
                value=addr,
                position=Position(self.TABLE_PROPERTY_RIGHTS, 2, 2),
                raw_text=addr,
            )

        # 结构
        struct = cells[3]
        if struct:
            result.subject.structure = struct

        # 楼层：可能出现多个“a-b/总”片段，取第一个可解析的
        floor_text = cells[4]
        if floor_text:
            m = re.search(r'(\d+)(?:-\d+)?\s*/\s*(\d+)', floor_text)
            if m:
                try:
                    result.subject.current_floor = int(m.group(1))
                    result.subject.total_floor = int(m.group(2))
                except:
                    pass

        # 面积：可能多段数字（多个分部），尝试求和
        area_text = cells[5]
        if area_text:
            nums = re.findall(r'\d+(?:\.\d+)?', area_text)
            if nums:
                try:
                    area_sum = sum(float(n) for n in nums)
                    # 仅在结果汇总未给出面积时写入；否则保留汇总表为准
                    if not result.subject.building_area.value:
                        result.subject.building_area = LocatedValue(
                            value=area_sum,
                            position=Position(self.TABLE_PROPERTY_RIGHTS, 2, 5),
                            raw_text=area_text,
                        )
                except:
                    pass

        # 用途（有些报告是“——”）
        usage = cells[6].strip()
        if usage and usage not in {'—', '——', '-'} and not result.subject.usage:
            result.subject.usage = usage

    def _extract_basic_info(self, result: ZujinExtractionResult):
        """提取基础信息表"""
        table = self.tables[self.TABLE_BASIC_INFO]
        
        result.cases = [Case(case_id='A'), Case(case_id='B'), Case(case_id='C')]
        
        # 列映射（基于分析：前两列合并，估价对象=2, A=3, B=4, C=5）
        COL_SUBJECT = 2
        COL_A = 3
        COL_B = 4
        COL_C = 5
        
        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            
            if len(cells) < 6:
                continue
            
            label = cells[0] + cells[1]
            label = label.replace(' ', '').replace('\u3000', '')
            
            if '地址' in label or '坐落' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.address = LocatedValue(
                            value=cells[col],
                            position=Position(self.TABLE_BASIC_INFO, row_idx, col),
                            raw_text=cells[col]
                        )
            
            elif '位置' in label and '楼' not in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.location = cells[col]
            
            elif '来源' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.data_source = cells[col]
            
            elif '用途' in label:
                if COL_SUBJECT < len(cells):
                    result.subject.usage = cells[COL_SUBJECT]
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.usage = cells[col]
            
            elif '租赁价格' in label or '交易价格' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            price = float(re.sub(r'[^\d.]', '', cells[col]))
                            case.rental_price = LocatedValue(
                                value=price,
                                position=Position(self.TABLE_BASIC_INFO, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif '评估面积' in label or '建筑面积' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            area = float(re.sub(r'[^\d.]', '', cells[col]))
                            case.building_area = LocatedValue(
                                value=area,
                                position=Position(self.TABLE_BASIC_INFO, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif '交易日期' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.transaction_date = cells[col]

    def _extract_factor_descriptions(self, result: ZujinExtractionResult):
        """提取因素描述表（表5）

        表5固定为6列：
        0=分类, 1=因素名称, 2=估价对象, 3/4/5=可比实例A/B/C。
        旧版本为了去重会导致列错位，这里按固定列读取。
        同时把估价对象因素写入 result.subject 的 factors（不改变输出结构）。
        """
        table = self.tables[self.TABLE_FACTOR_DESC]

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

        current_category = ''
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = [c.text.strip().replace('\\n', ' ') for c in row.cells]
            if len(cells) < 6:
                continue

            raw_category = (cells[COL_CATEGORY] or '').replace(' ', '').replace('　', '')
            factor_name = (cells[COL_FACTOR] or '').replace(' ', '').replace('　', '')

            # 跳过交易类
            if raw_category in ('交易情况', '交易日期') or factor_name in ('交易情况', '交易日期'):
                continue

            # 分类更新
            if raw_category in category_alias:
                current_category = category_alias[raw_category]

            if not factor_name:
                continue

            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue

            factor_key = self._normalize_factor_name(factor_name)

            # 估价对象
            subject_val = cells[COL_SUBJECT]
            if subject_val:
                subject_dict = getattr(result.subject, f'{factor_type}_factors')
                f = subject_dict.get(factor_key) or Factor(name=factor_key)
                f.description = subject_val
                f.desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, COL_SUBJECT)
                subject_dict[factor_key] = f
                self._sync_subject_fields_from_factor(result.subject, factor_key, factor_type)

            # 可比实例A/B/C
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                value = cells[col]
                if value == '':
                    continue
                factor_dict = getattr(case, f'{factor_type}_factors')
                f = factor_dict.get(factor_key) or Factor(name=factor_key)
                f.description = value
                f.desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, col)
                factor_dict[factor_key] = f

                self._sync_case_fields_from_factor(case, factor_key, factor_type)

    def _extract_factor_levels(self, result: ZujinExtractionResult):
        """提取因素等级表（表6）

        该报告中表6与表5结构一致，仍按固定列读取。
        """
        table = self.tables[self.TABLE_FACTOR_LEVEL]

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

        current_category = ''
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = [c.text.strip().replace('\\n', ' ') for c in row.cells]
            if len(cells) < 6:
                continue

            raw_category = (cells[COL_CATEGORY] or '').replace(' ', '').replace('　', '')
            factor_name = (cells[COL_FACTOR] or '').replace(' ', '').replace('　', '')

            if raw_category in ('交易情况', '交易日期') or factor_name in ('交易情况', '交易日期'):
                continue

            if raw_category in category_alias:
                current_category = category_alias[raw_category]

            if not factor_name:
                continue

            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue

            factor_key = self._normalize_factor_name(factor_name)

            # 估价对象
            subject_val = cells[COL_SUBJECT]
            if subject_val:
                subject_dict = getattr(result.subject, f'{factor_type}_factors')
                f = subject_dict.get(factor_key) or Factor(name=factor_key)
                f.level = subject_val
                f.level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, COL_SUBJECT)
                subject_dict[factor_key] = f

            # 可比实例
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                value = cells[col]
                if value == '':
                    continue
                factor_dict = getattr(case, f'{factor_type}_factors')
                f = factor_dict.get(factor_key) or Factor(name=factor_key)
                f.level = value
                f.level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, col)
                factor_dict[factor_key] = f

    def _extract_factor_indices(self, result: ZujinExtractionResult):
        """提取因素指数表（表7）"""
        table = self.tables[self.TABLE_FACTOR_INDEX]

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

        current_category = ''
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells = [c.text.strip().replace('\\n', ' ') for c in row.cells]
            if len(cells) < 6:
                continue

            raw_category = (cells[COL_CATEGORY] or '').replace(' ', '').replace('　', '')
            factor_name = (cells[COL_FACTOR] or '').replace(' ', '').replace('　', '')

            if raw_category in ('交易情况', '交易日期') or factor_name in ('交易情况', '交易日期'):
                continue

            if raw_category in category_alias:
                current_category = category_alias[raw_category]

            if not factor_name:
                continue

            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue

            factor_key = self._normalize_factor_name(factor_name)

            def to_int(v: str) -> int:
                try:
                    return int(re.sub(r'[^0-9]', '', v))
                except Exception:
                    return 100

            # 估价对象
            subject_val = cells[COL_SUBJECT]
            if subject_val:
                subject_dict = getattr(result.subject, f'{factor_type}_factors')
                f = subject_dict.get(factor_key) or Factor(name=factor_key)
                f.index = to_int(subject_val)
                f.index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, COL_SUBJECT)
                subject_dict[factor_key] = f

            # 可比实例
            for i, case in enumerate(result.cases):
                col = [COL_A, COL_B, COL_C][i]
                value = cells[col]
                if value == '':
                    continue
                factor_dict = getattr(case, f'{factor_type}_factors')
                f = factor_dict.get(factor_key) or Factor(name=factor_key)
                f.index = to_int(value)
                f.index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, col)
                factor_dict[factor_key] = f

    def _extract_corrections(self, result: ZujinExtractionResult):
        """提取修正系数"""
        table = self.tables[self.TABLE_CORRECTION]

        COL_A = 1

        ROW_MAPPING = {
            '交易价格': 'rental_price',
            '交易情况修正': 'transaction_correction',
            '市场状况': 'market_correction',
            '区位状况': 'location_correction',
            '实物状况': 'physical_correction',
            '权益状况': 'rights_correction',
            '调整后单价': 'adjusted_price',
        }

        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]

            if len(cells) < 2:
                continue

            label = cells[0].replace(' ', '').replace('\u3000', '')

            field_name = None
            for key, field in ROW_MAPPING.items():
                if key in label:
                    field_name = field
                    break

            if not field_name:
                continue

            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    try:
                        value = float(cells[col])
                        loc_val = LocatedValue(
                            value=value,
                            position=Position(self.TABLE_CORRECTION, row_idx, col),
                            raw_text=cells[col]
                        )
                        setattr(case, field_name, loc_val)
                    except:
                        pass

    def _get_factor_type(self, factor_name: str, current_category: str) -> str:
        """获取因素类型"""
        if factor_name in self.LOCATION_FACTORS or current_category == '区位状况':
            return 'location'
        elif factor_name in self.PHYSICAL_FACTORS or current_category in ('实物状况', '实物因素'):
            return 'physical'
        elif factor_name in self.RIGHTS_FACTORS or current_category in ('权益状况', '权益因素'):
            return 'rights'
        return ''

    def _sync_subject_fields_from_factor(self, subject: Subject, factor_key: str, val: str):
        v = (val or "").strip()
        if not v:
            return
        if factor_key == "orientation" and not subject.orientation:
            subject.orientation = v
        elif factor_key == "decoration" and not subject.decoration:
            subject.decoration = v
        elif factor_key == "structure" and not subject.structure:
            subject.structure = v

    def _sync_case_fields_from_factor(self, case: Case, factor_key: str, val: str):
        v = (val or "").strip()
        if not v:
            return
        if factor_key == "orientation" and not case.orientation:
            case.orientation = v
        elif factor_key == "decoration" and not case.decoration:
            case.decoration = v
        elif factor_key == "structure" and not case.structure:
            case.structure = v

    def _normalize_factor_name(self, name: str) -> str:
        """标准化因素名称"""
        name = name.replace(' ', '').replace('\u3000', '')

        mapping = {
            '繁华程度': 'prosperity',
            '楼幢位置': 'location_building',
            '朝向': 'orientation',
            '交通条件': 'traffic',
            '配套设施': 'facilities',
            '环境质量': 'environment',
            '景观': 'landscape',
            '建筑面积': 'area',
            '空间布局': 'layout',
            '新旧程度': 'age',
            '装饰装修': 'decoration',
            '建筑结构': 'structure',
            '物业类型': 'property_type',
            '设施设备': 'equipment',
            '规划条件': 'planning',
            '土地使用期限': 'land_term',
            '担保物权设立': 'mortgage',
            '租赁占用状况': 'lease',
            '拖欠税费状况': 'tax',
            # 兼容该报告模板的因素名称
            '区域位置': 'region_location',
            '物业管理': 'property_management',
            '驻车条件': 'parking',
            '地形地势': 'terrain',
            '地质土壤': 'soil',
            '开发程度': 'development',
            '套内建筑面积': 'inner_area',
            '楼宇等级': 'building_grade',
            '登记状况': 'registration',
            '他项权利': 'other_rights',
            '限制权利': 'restricted_rights',
            '土地剩余使用年限': 'land_remaining_term',
            '其他因素': 'other_factors',
        }

        return mapping.get(name, name)


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    extractor = ZujinExtractor()
    result = extractor.extract("./data/docs/租金报告-比较法.docx")

    print(result)