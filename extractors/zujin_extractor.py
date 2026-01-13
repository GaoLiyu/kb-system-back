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
    LOCATION_FACTORS = ['繁华程度', '楼幢位置', '朝向', '交通条件', '配套设施', '环境质量', '景观']
    PHYSICAL_FACTORS = ['建筑面积', '空间布局', '新旧程度', '装饰装修', '建筑结构', '物业类型', '设施设备']
    RIGHTS_FACTORS = ['规划条件', '土地使用期限', '担保物权设立', '租赁占用状况', '拖欠税费状况']
    
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
        """提取结果汇总表"""
        table = self.tables[self.TABLE_RESULT_SUMMARY]
        
        if len(table.rows) >= 2:
            row = table.rows[1]
            cells = [c.text.strip() for c in row.cells]
            
            if len(cells) >= 1:
                result.subject.address = LocatedValue(
                    value=cells[0],
                    position=Position(self.TABLE_RESULT_SUMMARY, 1, 0),
                    raw_text=cells[0]
                )
            
            if len(cells) >= 2:
                try:
                    result.subject.building_area = LocatedValue(
                        value=float(cells[1]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, 1),
                        raw_text=cells[1]
                    )
                except:
                    pass
            
            if len(cells) >= 3:
                try:
                    result.subject.unit_price = LocatedValue(
                        value=float(cells[2]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, 2),
                        raw_text=cells[2]
                    )
                    result.final_unit_price = result.subject.unit_price
                except:
                    pass
            
            if len(cells) >= 4:
                try:
                    result.subject.total_price = LocatedValue(
                        value=float(cells[3]),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, 3),
                        raw_text=cells[3]
                    )
                    result.final_total_price = result.subject.total_price
                except:
                    pass
    
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
        """提取因素描述表"""
        table = self.tables[self.TABLE_FACTOR_DESC]
        
        COL_SUBJECT = 1
        COL_A = 2
        COL_B = 3
        COL_C = 4
        
        current_category = ""
        
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells_raw = [c.text.strip().replace('\n', ' ') for c in row.cells]
            cells = []
            for c in cells_raw:
                if c not in cells:
                    cells.append(c)
            
            if len(cells) < 2:
                continue
            
            first = cells[0]
            
            if first in ['区位状况', '实物状况', '权益状况']:
                current_category = first
                factor_name = cells[1] if len(cells) > 1 else ""
            elif first in ['交易情况', '交易日期']:
                continue
            else:
                factor_name = first
            
            if not factor_name:
                continue
            
            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue
            
            factor_key = self._normalize_factor_name(factor_name)
            
            # 提取可比实例
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    value = cells[col]
                    
                    factor_dict = getattr(case, f'{factor_type}_factors')
                    if factor_key not in factor_dict:
                        factor_dict[factor_key] = Factor(name=factor_key)
                    factor_dict[factor_key].description = value
                    factor_dict[factor_key].desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, col)
    
    def _extract_factor_levels(self, result: ZujinExtractionResult):
        """提取因素等级表"""
        table = self.tables[self.TABLE_FACTOR_LEVEL]
        
        COL_A = 2
        current_category = ""
        
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells_raw = [c.text.strip() for c in row.cells]
            cells = []
            for c in cells_raw:
                if c not in cells:
                    cells.append(c)
            
            if len(cells) < 2:
                continue
            
            first = cells[0]
            
            if first in ['区位状况', '实物状况', '权益状况']:
                current_category = first
                factor_name = cells[1] if len(cells) > 1 else ""
            elif first in ['交易情况', '交易日期']:
                continue
            else:
                factor_name = first
            
            if not factor_name:
                continue
            
            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue
            
            factor_key = self._normalize_factor_name(factor_name)
            
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    value = cells[col]
                    factor_dict = getattr(case, f'{factor_type}_factors')
                    if factor_key not in factor_dict:
                        factor_dict[factor_key] = Factor(name=factor_key)
                    factor_dict[factor_key].level = value
                    factor_dict[factor_key].level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, col)
    
    def _extract_factor_indices(self, result: ZujinExtractionResult):
        """提取因素指数表（注意：表头是"案例A/B/C"）"""
        table = self.tables[self.TABLE_FACTOR_INDEX]
        
        COL_A = 2
        current_category = ""
        
        for row_idx, row in enumerate(table.rows[1:], 1):
            cells_raw = [c.text.strip() for c in row.cells]
            cells = []
            for c in cells_raw:
                if c not in cells:
                    cells.append(c)
            
            if len(cells) < 2:
                continue
            
            first = cells[0]
            
            if first in ['区位状况', '实物状况', '权益状况']:
                current_category = first
                factor_name = cells[1] if len(cells) > 1 else ""
            elif first in ['交易情况', '交易日期']:
                continue
            else:
                factor_name = first
            
            if not factor_name:
                continue
            
            factor_type = self._get_factor_type(factor_name, current_category)
            if not factor_type:
                continue
            
            factor_key = self._normalize_factor_name(factor_name)
            
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    try:
                        value = int(cells[col])
                    except:
                        value = 100
                    
                    factor_dict = getattr(case, f'{factor_type}_factors')
                    if factor_key not in factor_dict:
                        factor_dict[factor_key] = Factor(name=factor_key)
                    factor_dict[factor_key].index = value
                    factor_dict[factor_key].index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, col)
    
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
        elif factor_name in self.PHYSICAL_FACTORS or current_category == '实物状况':
            return 'physical'
        elif factor_name in self.RIGHTS_FACTORS or current_category == '权益状况':
            return 'rights'
        return ''
    
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
        }
        
        return mapping.get(name, name)


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    extractor = ZujinExtractor()
    result = extractor.extract("./data/docs/租金报告-比较法.docx")
    
    print(f"\n{'='*70}")
    print("【提取结果】")
    print('='*70)
    
    print(f"\n估价对象:")
    print(f"  地址: {result.subject.address.value}")
    print(f"  面积: {result.subject.building_area.value}㎡")
    print(f"  单价: {result.subject.unit_price.value}元/㎡·年")
    print(f"  总价: {result.subject.total_price.value}万元/年")
    print(f"  用途: {result.subject.usage}")
    
    print(f"\n可比实例:")
    for case in result.cases:
        print(f"\n  实例{case.case_id}:")
        print(f"    地址: {case.address.value}")
        print(f"    租赁价格: {case.rental_price.value}元/㎡·年")
        print(f"    面积: {case.building_area.value}㎡")
        print(f"    交易日期: {case.transaction_date}")
        
        print(f"    修正系数:")
        print(f"      交易情况: {case.transaction_correction.value}")
        print(f"      市场状况: {case.market_correction.value}")
        print(f"      区位状况: {case.location_correction.value}")
        print(f"      实物状况: {case.physical_correction.value}")
        print(f"      权益状况: {case.rights_correction.value}")
        print(f"    调整后单价: {case.adjusted_price.value}元/㎡·年")
        
        if case.location_factors.get('traffic'):
            print(f"    交通条件: {case.location_factors['traffic'].description}")
