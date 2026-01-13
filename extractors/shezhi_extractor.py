"""
涉执报告精确提取器
==================
针对涉执报告的表格结构精确提取
表格索引（基于分析结果）：
- 表格0/3/11: 结果汇总表
- 表格2: 权属表
- 表格5: 基础信息表
- 表格6: 因素描述表
- 表格7: 因素等级表
- 表格8: 因素指数表
- 表格9: 因素比率表
- 表格10: 修正计算表
"""

import os
import re
from typing import Dict, List, Optional
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
    case_id: str = ""  # A/B/C
    address: LocatedValue = field(default_factory=LocatedValue)
    location: str = ""
    usage: str = ""
    data_source: str = ""
    transaction_price: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_date: str = ""
    
    # 新增字段
    district: str = ""           # 区域
    street: str = ""             # 街道/镇
    build_year: int = 0          # 建成年份
    total_floor: int = 0         # 总楼层
    current_floor: int = 0       # 所在楼层
    orientation: str = ""        # 朝向
    decoration: str = ""         # 装修
    structure: str = ""          # 结构
    
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
    unit_price: LocatedValue = field(default_factory=LocatedValue)
    total_price: LocatedValue = field(default_factory=LocatedValue)
    
    # 权属
    cert_no: str = ""
    owner: str = ""
    structure: str = ""
    floor: str = ""
    usage: str = ""
    land_type: str = ""
    
    # 新增字段
    district: str = ""           # 区域（区/县）
    street: str = ""             # 街道/镇
    build_year: int = 0          # 建成年份
    total_floor: int = 0         # 总楼层
    current_floor: int = 0       # 所在楼层
    orientation: str = ""        # 朝向
    decoration: str = ""         # 装修状况
    land_end_date: str = ""      # 土地终止日期
    value_date: str = ""         # 价值时点
    appraisal_purpose: str = ""  # 估价目的
    
    # 因素
    location_factors: Dict[str, Factor] = field(default_factory=dict)
    physical_factors: Dict[str, Factor] = field(default_factory=dict)
    rights_factors: Dict[str, Factor] = field(default_factory=dict)


@dataclass
class ShezhiExtractionResult:
    """涉执报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)
    
    # 最终结果
    final_unit_price: LocatedValue = field(default_factory=LocatedValue)
    final_total_price: LocatedValue = field(default_factory=LocatedValue)
    floor_factor: float = 1.0


class ShezhiExtractor:
    """涉执报告提取器"""
    
    # 表格索引映射
    TABLE_RESULT_SUMMARY = 0      # 结果汇总
    TABLE_PROPERTY_RIGHTS = 2     # 权属表
    TABLE_BASIC_INFO = 5          # 基础信息
    TABLE_FACTOR_DESC = 6         # 因素描述
    TABLE_FACTOR_LEVEL = 7        # 因素等级
    TABLE_FACTOR_INDEX = 8        # 因素指数
    TABLE_FACTOR_RATIO = 9        # 因素比率
    TABLE_CORRECTION = 10         # 修正计算
    
    # 因素名称映射
    LOCATION_FACTORS = ['区域位置', '楼幢位置', '朝向', '交通条件', '配套设施', '环境质量', '景观', '物业管理']
    PHYSICAL_FACTORS = ['地形地势', '地质土壤', '开发程度', '建筑面积', '空间布局', '新旧程度', '装饰装修', '建筑结构', '物业类型', '设施设备']
    RIGHTS_FACTORS = ['规划条件', '土地使用期限', '担保物权设立', '租赁占用状况', '拖欠税费状况', '其他权益状况']
    
    def __init__(self):
        self.doc = None
        self.tables = []
        self.full_text = ""
    
    def extract(self, doc_path: str) -> ShezhiExtractionResult:
        """提取涉执报告"""
        self.doc = Document(doc_path)
        self.tables = self.doc.tables
        self.full_text = "\n".join([p.text for p in self.doc.paragraphs])
        
        result = ShezhiExtractionResult(source_file=os.path.basename(doc_path))
        
        print(f"\n📊 提取涉执报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")
        
        # 1. 提取结果汇总
        self._extract_result_summary(result)
        print(f"   ✓ 结果汇总: {result.subject.address.value}")
        
        # 2. 提取权属信息
        self._extract_property_rights(result)
        print(f"   ✓ 权属信息: {result.subject.cert_no}")
        
        # 3. 提取基础信息
        self._extract_basic_info(result)
        print(f"   ✓ 基础信息: {len(result.cases)}个可比实例")
        
        # 4. 提取因素描述
        self._extract_factor_descriptions(result)
        
        # 5. 提取因素等级
        self._extract_factor_levels(result)
        
        # 6. 提取因素指数
        self._extract_factor_indices(result)
        print(f"   ✓ 因素数据: 描述/等级/指数")
        
        # 7. 提取修正系数
        self._extract_corrections(result)
        print(f"   ✓ 修正系数")
        
        # 8. 提取楼层修正系数
        self._extract_floor_factor(result)
        if result.floor_factor != 1.0:
            print(f"   ✓ 楼层修正: {result.floor_factor}")
        
        # 9. 提取扩展信息（建成年代、价值时点、估价目的等）
        self._extract_extended_info(result)
        
        # 10. 解析区域信息
        self._parse_district(result)
        
        return result
    
    def _get_cell_value(self, table_idx: int, row_idx: int, col_idx: int) -> LocatedValue:
        """获取单元格值（带位置）"""
        try:
            table = self.tables[table_idx]
            cell = table.rows[row_idx].cells[col_idx]
            return LocatedValue(
                value=cell.text.strip(),
                position=Position(table_idx, row_idx, col_idx),
                raw_text=cell.text.strip()
            )
        except:
            return LocatedValue()
    
    def _extract_result_summary(self, result: ShezhiExtractionResult):
        """提取结果汇总表"""
        table = self.tables[self.TABLE_RESULT_SUMMARY]
        
        # 第二行是数据行
        if len(table.rows) >= 2:
            row = table.rows[1]
            cells = [c.text.strip() for c in row.cells]
            
            result.subject.address = LocatedValue(
                value=cells[0] if cells else "",
                position=Position(self.TABLE_RESULT_SUMMARY, 1, 0),
                raw_text=cells[0] if cells else ""
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
                # 提取总价数字
                total_text = cells[3]
                match = re.search(r'([\d.]+)', total_text)
                if match:
                    result.subject.total_price = LocatedValue(
                        value=float(match.group(1)),
                        position=Position(self.TABLE_RESULT_SUMMARY, 1, 3),
                        raw_text=total_text
                    )
                    result.final_total_price = result.subject.total_price
    
    def _extract_property_rights(self, result: ShezhiExtractionResult):
        """提取权属表"""
        table = self.tables[self.TABLE_PROPERTY_RIGHTS]
        
        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            row_text = ' '.join(cells)
            
            if '不动产权第' in row_text or '不动产权证' in row_text:
                for cell in cells:
                    if '不动产权' in cell and '号' in cell:
                        result.subject.cert_no = cell
                    elif cell in ['钢混', '砖混', '框架', '砖木']:
                        result.subject.structure = cell
                    elif '/' in cell and any(c.isdigit() for c in cell) and len(cell) < 10:
                        result.subject.floor = cell
            
            if '权利人' in row_text:
                for i, cell in enumerate(cells):
                    if cell and cell not in ['权利人', '不动产权利人', '坐落', '结构']:
                        if '不动产权' not in cell and '/' not in cell:
                            result.subject.owner = cell
                            break
    
    def _extract_basic_info(self, result: ShezhiExtractionResult):
        """提取基础信息表"""
        table = self.tables[self.TABLE_BASIC_INFO]
        
        # 初始化三个可比实例
        result.cases = [Case(case_id='A'), Case(case_id='B'), Case(case_id='C')]
        
        # 列映射: 估价对象=2, A=3, B=4, C=5
        COL_SUBJECT = 2
        COL_A = 3
        COL_B = 4
        COL_C = 5
        
        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            
            if len(cells) < 6:
                continue
            
            # 获取行标签（前两列可能合并）
            label = cells[0] + cells[1] if len(cells) > 1 else cells[0]
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
                # 估价对象用途
                if COL_SUBJECT < len(cells):
                    result.subject.usage = cells[COL_SUBJECT]
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.usage = cells[col]
            
            elif '成交基价' in label or '交易价格' in label:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            price = float(re.sub(r'[^\d.]', '', cells[col]))
                            case.transaction_price = LocatedValue(
                                value=price,
                                position=Position(self.TABLE_BASIC_INFO, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif '建筑面积' in label:
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
    
    def _extract_factor_descriptions(self, result: ShezhiExtractionResult):
        """提取因素描述表"""
        table = self.tables[self.TABLE_FACTOR_DESC]
        
        # 列映射
        COL_SUBJECT = 1  # 估价对象列（去重后）
        COL_A = 2
        COL_B = 3
        COL_C = 4
        
        current_category = ""
        
        for row_idx, row in enumerate(table.rows[1:], 1):  # 跳过表头
            # 获取去重后的单元格
            cells_raw = [c.text.strip().replace('\n', ' ') for c in row.cells]
            cells = []
            for c in cells_raw:
                if c not in cells:
                    cells.append(c)
            
            if len(cells) < 2:
                continue
            
            first = cells[0]
            
            # 判断类别
            if first in ['区位状况', '实物状况', '权益状况']:
                current_category = first
                factor_name = cells[1] if len(cells) > 1 else ""
            elif first in ['交易情况', '交易日期']:
                continue  # 跳过交易相关行
            else:
                factor_name = first
            
            if not factor_name:
                continue
            
            # 确定因素类别
            if factor_name in self.LOCATION_FACTORS or current_category == '区位状况':
                factor_type = 'location'
            elif factor_name in self.PHYSICAL_FACTORS or current_category == '实物状况':
                factor_type = 'physical'
            elif factor_name in self.RIGHTS_FACTORS or current_category == '权益状况':
                factor_type = 'rights'
            else:
                continue
            
            # 标准化因素名
            factor_key = self._normalize_factor_name(factor_name)
            
            # 提取估价对象的值
            if len(cells) > COL_SUBJECT:
                subject_value = cells[COL_SUBJECT]
                factor = Factor(name=factor_key, description=subject_value)
                factor.desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, COL_SUBJECT)
                
                if factor_type == 'location':
                    result.subject.location_factors[factor_key] = factor
                elif factor_type == 'physical':
                    result.subject.physical_factors[factor_key] = factor
                elif factor_type == 'rights':
                    result.subject.rights_factors[factor_key] = factor
            
            # 提取可比实例的值
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    value = cells[col]
                    
                    # 初始化因素
                    if factor_type == 'location':
                        if factor_key not in case.location_factors:
                            case.location_factors[factor_key] = Factor(name=factor_key)
                        case.location_factors[factor_key].description = value
                        case.location_factors[factor_key].desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, col)
                    elif factor_type == 'physical':
                        if factor_key not in case.physical_factors:
                            case.physical_factors[factor_key] = Factor(name=factor_key)
                        case.physical_factors[factor_key].description = value
                        case.physical_factors[factor_key].desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, col)
                    elif factor_type == 'rights':
                        if factor_key not in case.rights_factors:
                            case.rights_factors[factor_key] = Factor(name=factor_key)
                        case.rights_factors[factor_key].description = value
                        case.rights_factors[factor_key].desc_pos = Position(self.TABLE_FACTOR_DESC, row_idx, col)
    
    def _extract_factor_levels(self, result: ShezhiExtractionResult):
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
            
            if factor_name in self.LOCATION_FACTORS or current_category == '区位状况':
                factor_type = 'location'
            elif factor_name in self.PHYSICAL_FACTORS or current_category == '实物状况':
                factor_type = 'physical'
            elif factor_name in self.RIGHTS_FACTORS or current_category == '权益状况':
                factor_type = 'rights'
            else:
                continue
            
            factor_key = self._normalize_factor_name(factor_name)
            
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    value = cells[col]
                    
                    if factor_type == 'location':
                        if factor_key not in case.location_factors:
                            case.location_factors[factor_key] = Factor(name=factor_key)
                        case.location_factors[factor_key].level = value
                        case.location_factors[factor_key].level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, col)
                    elif factor_type == 'physical':
                        if factor_key not in case.physical_factors:
                            case.physical_factors[factor_key] = Factor(name=factor_key)
                        case.physical_factors[factor_key].level = value
                        case.physical_factors[factor_key].level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, col)
                    elif factor_type == 'rights':
                        if factor_key not in case.rights_factors:
                            case.rights_factors[factor_key] = Factor(name=factor_key)
                        case.rights_factors[factor_key].level = value
                        case.rights_factors[factor_key].level_pos = Position(self.TABLE_FACTOR_LEVEL, row_idx, col)
    
    def _extract_factor_indices(self, result: ShezhiExtractionResult):
        """提取因素指数表"""
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
            
            if factor_name in self.LOCATION_FACTORS or current_category == '区位状况':
                factor_type = 'location'
            elif factor_name in self.PHYSICAL_FACTORS or current_category == '实物状况':
                factor_type = 'physical'
            elif factor_name in self.RIGHTS_FACTORS or current_category == '权益状况':
                factor_type = 'rights'
            else:
                continue
            
            factor_key = self._normalize_factor_name(factor_name)
            
            for i, case in enumerate(result.cases):
                col = COL_A + i
                if col < len(cells):
                    try:
                        value = int(cells[col])
                    except:
                        value = 100
                    
                    if factor_type == 'location':
                        if factor_key not in case.location_factors:
                            case.location_factors[factor_key] = Factor(name=factor_key)
                        case.location_factors[factor_key].index = value
                        case.location_factors[factor_key].index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, col)
                    elif factor_type == 'physical':
                        if factor_key not in case.physical_factors:
                            case.physical_factors[factor_key] = Factor(name=factor_key)
                        case.physical_factors[factor_key].index = value
                        case.physical_factors[factor_key].index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, col)
                    elif factor_type == 'rights':
                        if factor_key not in case.rights_factors:
                            case.rights_factors[factor_key] = Factor(name=factor_key)
                        case.rights_factors[factor_key].index = value
                        case.rights_factors[factor_key].index_pos = Position(self.TABLE_FACTOR_INDEX, row_idx, col)
    
    def _extract_corrections(self, result: ShezhiExtractionResult):
        """提取修正系数"""
        table = self.tables[self.TABLE_CORRECTION]
        
        # 修正计算表列: A=1, B=2, C=3
        COL_A = 1
        
        ROW_MAPPING = {
            '交易价格': 'transaction_price',
            '交易情况修正': 'transaction_correction',
            '市场状况': 'market_correction',
            '区位状况': 'location_correction',
            '实物状况': 'physical_correction',
            '权益状况': 'rights_correction',
            '修正后单价': 'adjusted_price',
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
    
    def _extract_floor_factor(self, result: ShezhiExtractionResult):
        """提取楼层修正系数"""
        match = re.search(r'×\s*(\d+)%\s*[＝=]', self.full_text)
        if match:
            result.floor_factor = int(match.group(1)) / 100
    
    def _extract_extended_info(self, result: ShezhiExtractionResult):
        """提取扩展信息（建成年代、价值时点、估价目的等）"""
        
        # 1. 建成年代 - 从段落文本中提取
        # 匹配模式: "建成于XXXX年" 或 "约建成于本世纪初" 或 "建成年代：XXXX"
        build_patterns = [
            r'建成于(\d{4})年',
            r'约(\d{4})年建成',
            r'建成年代[：:]\s*(\d{4})',
            r'(\d{4})年建成',
            r'约建成于本世纪初',  # 特殊处理
            r'建成于上世纪(\d{2})年代',
        ]
        
        for pattern in build_patterns:
            match = re.search(pattern, self.full_text)
            if match:
                if '本世纪初' in pattern:
                    result.subject.build_year = 2000
                elif len(match.groups()) > 0:
                    year_str = match.group(1)
                    if len(year_str) == 2:
                        # 处理"90年代"这种格式
                        result.subject.build_year = 1900 + int(year_str)
                    else:
                        result.subject.build_year = int(year_str)
                break
        
        # 2. 价值时点 - 从段落文本中提取
        value_date_patterns = [
            r'价值时点[：:]\s*(\d{4})[年\.](\d{1,2})[月\.](\d{1,2})',
            r'价值时点(\d{4})\.(\d{1,2})\.(\d{1,2})',
            r'价值时点为(\d{4})年(\d{1,2})月(\d{1,2})日',
        ]
        
        for pattern in value_date_patterns:
            match = re.search(pattern, self.full_text)
            if match:
                result.subject.value_date = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                break
        
        # 3. 估价目的 - 从段落文本中提取
        purpose_patterns = [
            r'估价目的[：:是为]*(.{5,50}?)(?:。|$)',
            r'本次估价目的是(.{5,50}?)(?:。|$)',
        ]
        
        for pattern in purpose_patterns:
            match = re.search(pattern, self.full_text)
            if match:
                result.subject.appraisal_purpose = match.group(1).strip()
                break
        
        # 4. 土地终止日期 - 从权属表中提取
        if len(self.tables) > self.TABLE_PROPERTY_RIGHTS:
            table = self.tables[self.TABLE_PROPERTY_RIGHTS]
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                for i, cell in enumerate(cells):
                    if '终止' in cell and i + 1 < len(cells):
                        # 找下一行同一列
                        pass
                    # 匹配日期格式 YYYY/MM/DD
                    date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', cell)
                    if date_match:
                        result.subject.land_end_date = date_match.group(1)
        
        # 5. 解析楼层信息（从字符串"8/10"解析为数字）
        if result.subject.floor and '/' in result.subject.floor:
            parts = result.subject.floor.split('/')
            if len(parts) == 2:
                try:
                    result.subject.current_floor = int(parts[0])
                    result.subject.total_floor = int(parts[1])
                except:
                    pass
    
    def _parse_district(self, result: ShezhiExtractionResult):
        """从地址解析区域信息"""
        address = result.subject.address.value or ""
        
        # 常见区域关键词
        district_patterns = [
            r'([\u4e00-\u9fa5]{2,4}区)',   # XX区
            r'([\u4e00-\u9fa5]{2,4}县)',   # XX县
            r'([\u4e00-\u9fa5]{2,4}市)',   # XX市（县级市）
        ]
        
        for pattern in district_patterns:
            match = re.search(pattern, address)
            if match:
                result.subject.district = match.group(1)
                break
        
        # 街道/镇
        street_patterns = [
            r'([\u4e00-\u9fa5]{2,6}街道)',
            r'([\u4e00-\u9fa5]{2,4}镇)',
            r'([\u4e00-\u9fa5]{2,4}乡)',
        ]
        
        for pattern in street_patterns:
            match = re.search(pattern, address)
            if match:
                result.subject.street = match.group(1)
                break
        
        # 同样处理可比实例
        for case in result.cases:
            case_addr = case.address.value or ""
            
            for pattern in district_patterns:
                match = re.search(pattern, case_addr)
                if match:
                    case.district = match.group(1)
                    break
            
            for pattern in street_patterns:
                match = re.search(pattern, case_addr)
                if match:
                    case.street = match.group(1)
                    break
    
    def _normalize_factor_name(self, name: str) -> str:
        """标准化因素名称"""
        name = name.replace(' ', '').replace('\u3000', '').replace('　', '')
        
        mapping = {
            '区域位置': 'location_region',
            '楼幢位置': 'location_building',
            '朝向': 'orientation',
            '交通条件': 'traffic',
            '配套设施': 'facilities',
            '环境质量': 'environment',
            '景观': 'landscape',
            '物业管理': 'property_management',
            '地形地势': 'terrain',
            '地质土壤': 'geology',
            '开发程度': 'development',
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
            '其他权益状况': 'other_rights',
        }
        
        return mapping.get(name, name)


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    extractor = ShezhiExtractor()
    result = extractor.extract("./data/docs/涉执报告-比较法.docx")
    
    print(f"\n{'='*70}")
    print("【提取结果】")
    print('='*70)
    
    print(f"\n估价对象:")
    print(f"  地址: {result.subject.address.value}")
    print(f"  面积: {result.subject.building_area.value}㎡")
    print(f"  单价: {result.subject.unit_price.value}元/㎡")
    print(f"  总价: {result.subject.total_price.value}万元")
    print(f"  结构: {result.subject.structure}")
    print(f"  楼层: {result.subject.floor}")
    
    print(f"\n可比实例:")
    for case in result.cases:
        print(f"\n  实例{case.case_id}:")
        print(f"    地址: {case.address.value}")
        print(f"    成交价: {case.transaction_price.value}元/㎡")
        print(f"    面积: {case.building_area.value}㎡")
        print(f"    交易日期: {case.transaction_date}")
        
        print(f"    修正系数:")
        print(f"      交易情况: {case.transaction_correction.value}")
        print(f"      市场状况: {case.market_correction.value}")
        print(f"      区位状况: {case.location_correction.value}")
        print(f"      实物状况: {case.physical_correction.value}")
        print(f"      权益状况: {case.rights_correction.value}")
        print(f"    修正后单价: {case.adjusted_price.value}元/㎡")
        
        # 显示部分因素
        if case.location_factors.get('traffic'):
            print(f"    交通条件: {case.location_factors['traffic'].description}")
        if case.physical_factors.get('layout'):
            print(f"    空间布局: {case.physical_factors['layout'].description}")
        if case.physical_factors.get('equipment'):
            print(f"    设施设备: {case.physical_factors['equipment'].description}")
    
    print(f"\n楼层修正系数: {result.floor_factor}")
