"""
报告校验器
==========
校验单个报告的数据质量：完整性、合理性、反算
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Any
from dataclasses import dataclass, field
from config import VALIDATION_CONFIG


@dataclass
class Issue:
    """问题项"""
    level: str          # error / warning / info
    category: str       # completeness / reasonability / formula / consistency
    description: str
    position: Dict = field(default_factory=dict)  # 位置信息
    suggestion: str = ""
    related_data: Dict = field(default_factory=dict)


@dataclass
class FormulaCheck:
    """公式校验结果"""
    case_id: str
    formula_name: str
    expected: float
    actual: float
    difference: float
    is_valid: bool
    position: Dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    risk_level: str     # low / medium / high
    issues: List[Issue] = field(default_factory=list)
    formula_checks: List[FormulaCheck] = field(default_factory=list)
    summary: str = ""


class ReportValidator:
    """报告校验器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or VALIDATION_CONFIG
    
    def validate(self, result) -> ValidationResult:
        """
        校验提取结果
        
        Args:
            result: 提取结果对象
        
        Returns:
            ValidationResult
        """
        issues = []
        formula_checks = []
        
        # 1. 完整性校验
        issues.extend(self._check_completeness(result))
        
        # 2. 合理性校验
        issues.extend(self._check_reasonability(result))
        
        # 3. 反算校验
        checks = self._check_formulas(result)
        formula_checks.extend(checks)
        
        # 将公式问题也加入issues
        for fc in formula_checks:
            if not fc.is_valid:
                issues.append(Issue(
                    level='warning',
                    category='formula',
                    description=f'实例{fc.case_id}{fc.formula_name}验算不符：理论值{fc.expected:.0f}，实际值{fc.actual:.0f}',
                    position=fc.position,
                ))
        
        # 4. 一致性校验
        issues.extend(self._check_consistency(result))
        
        # 计算风险等级
        error_count = len([i for i in issues if i.level == 'error'])
        warning_count = len([i for i in issues if i.level == 'warning'])
        
        if error_count > 0:
            risk_level = 'high'
        elif warning_count > 3:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        return ValidationResult(
            is_valid=(error_count == 0),
            risk_level=risk_level,
            issues=issues,
            formula_checks=formula_checks,
            summary=f"发现{error_count}个错误，{warning_count}个警告"
        )
    
    def _check_completeness(self, result) -> List[Issue]:
        """完整性校验"""
        issues = []
        
        # 估价对象地址
        if not result.subject.address.value:
            issues.append(Issue(
                level='error',
                category='completeness',
                description='估价对象地址缺失',
                suggestion='请检查结果汇总表',
            ))
        
        # 估价对象面积
        if not result.subject.building_area.value:
            issues.append(Issue(
                level='error',
                category='completeness',
                description='估价对象建筑面积缺失',
                suggestion='请检查结果汇总表',
            ))
        
        # 可比实例数量
        min_count = self.config.get('min_case_count', 3)
        if len(result.cases) < min_count:
            issues.append(Issue(
                level='warning',
                category='completeness',
                description=f'可比实例仅{len(result.cases)}个，建议至少{min_count}个',
            ))
        
        # 每个实例的关键字段
        for case in result.cases:
            if not case.address.value:
                issues.append(Issue(
                    level='warning',
                    category='completeness',
                    description=f'实例{case.case_id}地址缺失',
                ))
        
        return issues
    
    def _check_reasonability(self, result) -> List[Issue]:
        """合理性校验"""
        issues = []
        
        min_val, max_val = self.config.get('correction_range', (0.7, 1.3))
        
        for case in result.cases:
            # 检查修正系数范围（涉执和租金报告）
            corrections = [
                ('交易情况', 'transaction_correction'),
                ('市场状况', 'market_correction'),
                ('区位状况', 'location_correction'),
                ('实物状况', 'physical_correction'),
                ('权益状况', 'rights_correction'),
            ]
            
            for name, field in corrections:
                if hasattr(case, field):
                    val = getattr(case, field)
                    if val.value and (val.value < min_val or val.value > max_val):
                        issues.append(Issue(
                            level='warning',
                            category='reasonability',
                            description=f'实例{case.case_id}的{name}修正系数({val.value})超出常规范围({min_val}-{max_val})',
                            position={
                                'table': val.position.table_index,
                                'row': val.position.row_index,
                                'col': val.position.col_index,
                            },
                            suggestion='请核实修正系数计算',
                        ))
        
        return issues
    
    def _check_formulas(self, result) -> List[FormulaCheck]:
        """反算校验"""
        checks = []
        tolerance = self.config.get('formula_tolerance', 10)
        
        for case in result.cases:
            # 获取交易价格
            trans = 0
            if hasattr(case, 'transaction_price') and case.transaction_price.value:
                trans = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price.value:
                trans = case.rental_price.value
            
            # 获取修正后价格
            adj = 0
            adj_position = {}
            if hasattr(case, 'adjusted_price') and case.adjusted_price.value:
                adj = case.adjusted_price.value
                adj_position = {
                    'table': case.adjusted_price.position.table_index,
                    'row': case.adjusted_price.position.row_index,
                }
            
            # 计算修正后单价
            if trans > 0 and adj > 0 and hasattr(case, 'transaction_correction'):
                tc = getattr(case, 'transaction_correction').value or 1
                mc = getattr(case, 'market_correction').value or 1
                lc = getattr(case, 'location_correction').value or 1
                pc = getattr(case, 'physical_correction').value or 1
                rc = getattr(case, 'rights_correction').value or 1
                
                expected = trans * tc * mc * lc * pc * rc
                diff = abs(expected - adj)
                
                checks.append(FormulaCheck(
                    case_id=case.case_id,
                    formula_name='修正后单价',
                    expected=round(expected, 2),
                    actual=adj,
                    difference=round(diff, 2),
                    is_valid=(diff < tolerance),
                    position=adj_position,
                ))
        
        return checks
    
    def _check_consistency(self, result) -> List[Issue]:
        """一致性校验"""
        issues = []
        
        # 检查因素等级与指数是否一致
        for case in result.cases:
            for factor_type in ['location_factors', 'physical_factors', 'rights_factors']:
                if not hasattr(case, factor_type):
                    continue
                
                factors = getattr(case, factor_type)
                if not factors:
                    continue
                
                for key, factor in factors.items():
                    level = factor.level
                    index = factor.index
                    
                    if level in ['优', '较优'] and index < 100:
                        issues.append(Issue(
                            level='warning',
                            category='consistency',
                            description=f'实例{case.case_id}的{key}等级"{level}"与指数{index}不一致',
                            suggestion='"优"或"较优"的指数通常应>=100',
                        ))
                    elif level in ['差', '较差'] and index > 100:
                        issues.append(Issue(
                            level='warning',
                            category='consistency',
                            description=f'实例{case.case_id}的{key}等级"{level}"与指数{index}不一致',
                            suggestion='"差"或"较差"的指数通常应<=100',
                        ))
        
        return issues


# ============================================================================
# 便捷函数
# ============================================================================

def validate_report(result, config: Dict = None) -> ValidationResult:
    """校验报告的便捷函数"""
    validator = ReportValidator(config)
    return validator.validate(result)
