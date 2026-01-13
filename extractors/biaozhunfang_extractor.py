"""
标准房报告精确提取器
====================
针对标准房报告的表格结构精确提取
表格索引（基于分析结果）：
- 表格6: 主要信息表（地址、面积、各类修正系数等，4个可比实例）
- 表格19: 详细因素比较表
- 表格20: 修正计算表
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
class Case:
    """可比实例"""
    case_id: str = ""  # A/B/C/D
    address: LocatedValue = field(default_factory=LocatedValue)
    data_source: str = ""
    building_area: LocatedValue = field(default_factory=LocatedValue)
    transaction_price: LocatedValue = field(default_factory=LocatedValue)  # 交易单价
    
    # 标准房特有的修正系数
    structure_factor: LocatedValue = field(default_factory=LocatedValue)  # 结构修正
    floor_factor: LocatedValue = field(default_factory=LocatedValue)      # 层次修正
    orientation_factor: LocatedValue = field(default_factory=LocatedValue)  # 朝向修正
    age_factor: LocatedValue = field(default_factory=LocatedValue)        # 成新修正
    physical_composite: LocatedValue = field(default_factory=LocatedValue)  # 实体状况综合
    
    # 计算表中的修正
    p1_transaction: str = ""      # P1交易情况修正
    p2_date: str = ""             # P2交易日期修正
    p3_physical: str = ""         # P3实体因素修正
    p4_location: str = ""         # P4区位状况修正
    composite_result: LocatedValue = field(default_factory=LocatedValue)  # P1×P2×P3×P4结果
    vs_result: LocatedValue = field(default_factory=LocatedValue)         # Vs×结果
    decoration_price: LocatedValue = field(default_factory=LocatedValue)  # 装修重置价
    attachment_price: LocatedValue = field(default_factory=LocatedValue)  # 附属物单价
    final_price: LocatedValue = field(default_factory=LocatedValue)       # 比准价格


@dataclass
class Subject:
    """估价对象（标准房）"""
    address: LocatedValue = field(default_factory=LocatedValue)
    building_area: LocatedValue = field(default_factory=LocatedValue)
    
    # 修正系数
    structure_factor: LocatedValue = field(default_factory=LocatedValue)
    floor_factor: LocatedValue = field(default_factory=LocatedValue)
    orientation_factor: LocatedValue = field(default_factory=LocatedValue)
    age_factor: LocatedValue = field(default_factory=LocatedValue)
    physical_composite: LocatedValue = field(default_factory=LocatedValue)
    
    # 区位
    location_code: str = ""


@dataclass
class BiaozhunfangExtractionResult:
    """标准房报告提取结果"""
    source_file: str = ""
    subject: Subject = field(default_factory=Subject)
    cases: List[Case] = field(default_factory=list)
    
    # 最终结果（比准价格的平均值或加权值）
    final_price: LocatedValue = field(default_factory=LocatedValue)


class BiaozhunfangExtractor:
    """标准房报告提取器"""
    
    # 表格索引
    TABLE_MAIN_INFO = 6        # 主要信息表（34行）
    TABLE_DETAIL = 19          # 详细因素表（30行）
    TABLE_CORRECTION = 20      # 修正计算表（11行）
    
    def __init__(self):
        self.doc = None
        self.tables = []
    
    def extract(self, doc_path: str) -> BiaozhunfangExtractionResult:
        """提取标准房报告"""
        self.doc = Document(doc_path)
        self.tables = self.doc.tables
        
        result = BiaozhunfangExtractionResult(source_file=os.path.basename(doc_path))
        
        print(f"\n📊 提取标准房报告: {os.path.basename(doc_path)}")
        print(f"   表格数量: {len(self.tables)}")
        
        # 初始化4个可比实例
        result.cases = [Case(case_id='A'), Case(case_id='B'), 
                        Case(case_id='C'), Case(case_id='D')]
        
        # 1. 从表格19提取基本信息和修正系数
        self._extract_detail_table(result)
        print(f"   ✓ 详细信息表: 地址、面积、修正系数")
        
        # 2. 从表格20提取修正计算
        self._extract_correction_table(result)
        print(f"   ✓ 修正计算表: 比准价格")
        
        return result
    
    def _extract_detail_table(self, result: BiaozhunfangExtractionResult):
        """提取详细因素表（表格19）"""
        table = self.tables[self.TABLE_DETAIL]
        
        # 列映射：估价对象=1, A=2, B=3, C=4, D=5
        COL_SUBJECT = 1
        COL_A = 2
        COL_B = 3
        COL_C = 4
        COL_D = 5
        
        # 行映射（基于分析结果）
        ROW_DATA_SOURCE = 2      # 案例来源
        ROW_ADDRESS = 3          # 地址
        ROW_AREA = 4             # 建筑面积
        ROW_STRUCTURE = 5        # 结构修正系数
        ROW_FLOOR = 6            # 层次修正系数
        ROW_ORIENTATION = 7      # 朝向修正系数
        ROW_AGE = 8              # 成新修正系数
        ROW_PHYSICAL_COMPOSITE = 10  # 实体状况系数综合
        ROW_LOCATION_CODE = 14   # 区位代码
        
        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            
            if len(cells) < 5:
                continue
            
            if row_idx == ROW_ADDRESS:
                # 估价对象地址
                if len(cells) > COL_SUBJECT:
                    result.subject.address = LocatedValue(
                        value=cells[COL_SUBJECT],
                        position=Position(self.TABLE_DETAIL, row_idx, COL_SUBJECT),
                        raw_text=cells[COL_SUBJECT]
                    )
                # 可比实例地址
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.address = LocatedValue(
                            value=cells[col],
                            position=Position(self.TABLE_DETAIL, row_idx, col),
                            raw_text=cells[col]
                        )
            
            elif row_idx == ROW_DATA_SOURCE:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.data_source = cells[col]
            
            elif row_idx == ROW_AREA:
                # 估价对象面积
                if len(cells) > COL_SUBJECT:
                    try:
                        result.subject.building_area = LocatedValue(
                            value=float(cells[COL_SUBJECT]),
                            position=Position(self.TABLE_DETAIL, row_idx, COL_SUBJECT),
                            raw_text=cells[COL_SUBJECT]
                        )
                    except:
                        pass
                # 可比实例面积
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.building_area = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_DETAIL, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_STRUCTURE:
                self._extract_factor_row(result, cells, row_idx, 'structure_factor', 
                                         COL_SUBJECT, COL_A)
            
            elif row_idx == ROW_FLOOR:
                self._extract_factor_row(result, cells, row_idx, 'floor_factor',
                                         COL_SUBJECT, COL_A)
            
            elif row_idx == ROW_ORIENTATION:
                self._extract_factor_row(result, cells, row_idx, 'orientation_factor',
                                         COL_SUBJECT, COL_A)
            
            elif row_idx == ROW_AGE:
                self._extract_factor_row(result, cells, row_idx, 'age_factor',
                                         COL_SUBJECT, COL_A)
            
            elif row_idx == ROW_PHYSICAL_COMPOSITE:
                self._extract_factor_row(result, cells, row_idx, 'physical_composite',
                                         COL_SUBJECT, COL_A)
            
            elif row_idx == ROW_LOCATION_CODE:
                if len(cells) > COL_SUBJECT:
                    result.subject.location_code = cells[COL_SUBJECT]
    
    def _extract_factor_row(self, result, cells, row_idx, factor_name, col_subject, col_a):
        """提取修正系数行"""
        # 估价对象
        if len(cells) > col_subject:
            try:
                value = float(cells[col_subject])
                setattr(result.subject, factor_name, LocatedValue(
                    value=value,
                    position=Position(self.TABLE_DETAIL, row_idx, col_subject),
                    raw_text=cells[col_subject]
                ))
            except:
                pass
        
        # 可比实例
        for i, case in enumerate(result.cases):
            col = col_a + i
            if col < len(cells):
                try:
                    value = float(cells[col])
                    setattr(case, factor_name, LocatedValue(
                        value=value,
                        position=Position(self.TABLE_DETAIL, row_idx, col),
                        raw_text=cells[col]
                    ))
                except:
                    pass
    
    def _extract_correction_table(self, result: BiaozhunfangExtractionResult):
        """提取修正计算表（表格20）"""
        table = self.tables[self.TABLE_CORRECTION]
        
        # 列映射: A=1, B=2, C=3, D=4
        COL_A = 1
        
        # 行映射
        ROW_PRICE = 1           # 交易单价
        ROW_P1 = 2              # P1交易情况修正
        ROW_P2 = 3              # P2交易日期修正
        ROW_P3 = 4              # P3实体因素修正
        ROW_P4 = 5              # P4区位状况修正
        ROW_COMPOSITE = 6       # P1×P2×P3×P4结果
        ROW_VS = 7              # Vs×P1×P2×P3×P4结果
        ROW_DECORATION = 8      # 单位面积装修重置价
        ROW_ATTACHMENT = 9      # 单位面积附属物单价
        ROW_FINAL = 10          # 比准价格
        
        for row_idx, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            
            if len(cells) < 4:
                continue
            
            if row_idx == ROW_PRICE:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.transaction_price = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_P1:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.p1_transaction = cells[col]
            
            elif row_idx == ROW_P2:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.p2_date = cells[col]
            
            elif row_idx == ROW_P3:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.p3_physical = cells[col]
            
            elif row_idx == ROW_P4:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        case.p4_location = cells[col]
            
            elif row_idx == ROW_COMPOSITE:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.composite_result = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_VS:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.vs_result = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_DECORATION:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.decoration_price = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_ATTACHMENT:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.attachment_price = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass
            
            elif row_idx == ROW_FINAL:
                for i, case in enumerate(result.cases):
                    col = COL_A + i
                    if col < len(cells):
                        try:
                            case.final_price = LocatedValue(
                                value=float(cells[col]),
                                position=Position(self.TABLE_CORRECTION, row_idx, col),
                                raw_text=cells[col]
                            )
                        except:
                            pass


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    extractor = BiaozhunfangExtractor()
    result = extractor.extract("./data/docs/标准房报告-比较法.docx")
    
    print(f"\n{'='*70}")
    print("【提取结果】")
    print('='*70)
    
    print(f"\n估价对象（标准房）:")
    print(f"  地址: {result.subject.address.value}")
    print(f"  面积: {result.subject.building_area.value}㎡")
    print(f"  结构修正: {result.subject.structure_factor.value}%")
    print(f"  层次修正: {result.subject.floor_factor.value}%")
    print(f"  朝向修正: {result.subject.orientation_factor.value}%")
    print(f"  成新修正: {result.subject.age_factor.value}%")
    print(f"  实体综合: {result.subject.physical_composite.value}%")
    print(f"  区位代码: {result.subject.location_code}")
    
    print(f"\n可比实例:")
    for case in result.cases:
        print(f"\n  实例{case.case_id}:")
        print(f"    地址: {case.address.value}")
        print(f"    来源: {case.data_source}")
        print(f"    面积: {case.building_area.value}㎡")
        print(f"    交易单价: {case.transaction_price.value}元/㎡")
        print(f"    P1交易情况: {case.p1_transaction}")
        print(f"    P2交易日期: {case.p2_date}")
        print(f"    P3实体因素: {case.p3_physical}")
        print(f"    P4区位状况: {case.p4_location}")
        print(f"    综合系数: {case.composite_result.value}")
        print(f"    Vs结果: {case.vs_result.value}")
        print(f"    装修重置价: {case.decoration_price.value}")
        print(f"    比准价格: {case.final_price.value}元/㎡")
