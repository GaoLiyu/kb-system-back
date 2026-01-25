"""
报告校验器
==========
校验单个报告的数据质量：完整性、合理性、反算
"""

import sys
import os

from utils import normalize_factor, parse_ratio_to_float

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
    inputs: Dict[str, Any] = field(default_factory=dict)
    formula_detail: str = ""


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
            case_id = getattr(case, 'case_id', '?')

            # 地址检查
            if not case.address.value:
                issues.append(Issue(
                    level='warning',
                    category='completeness',
                    description=f'实例{case.case_id}地址缺失',
                ))

            # 价格检查
            price = None
            if hasattr(case, 'transaction_price') and case.transaction_price and case.transaction_price.value:
                price = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price and case.rental_price.value:
                price = case.rental_price.value
            elif hasattr(case, 'final_price') and case.final_price and case.final_price.value:
                price = case.final_price.value

            if not price:
                issues.append(Issue(
                    level='error',
                    category='completeness',
                    description=f'实例{case_id}价格缺失',
                    suggestion='请检查可比实例的交易价格/租金/比准价格',
                ))

            # 修正系数检查（涉执和租金报告）
            if hasattr(case, 'location_correction'):
                if not case.location_correction or not case.location_correction.value:
                    issues.append(Issue(
                        level='warning',
                        category='completeness',
                        description=f'实例{case_id}修正系数缺失',
                    ))

            # 标准房的P3/P4检查
            if hasattr(case, 'physical_composite'):
                if not case.physical_composite or not case.physical_composite.value:
                    issues.append(Issue(
                        level='warning',
                        category='completeness',
                        description=f'实例{case_id}P3综合系数缺失',
                    ))
        
        return issues
    
    def _check_reasonability(self, result) -> List[Issue]:
        """合理性校验"""
        issues = []
        
        min_val, max_val = self.config.get('correction_range', (0.7, 1.3))

        # 检测报告类型
        report_type = getattr(result, 'type', None)
        if not report_type:
            # 通过字段特征判断
            if hasattr(result.cases[0], 'physical_composite') if result.cases else False:
                report_type = 'biaozhunfang'
            else:
                report_type = 'shezhi'

        for case in result.cases:
            case_id = getattr(case, 'case_id', '?')
            if report_type == 'biaozhunfang':
                p_factors = [
                    ('P1(交易情况)', 'p1', 0.95, 1.05),  # P1通常为1
                    ('P2(交易日期)', 'p2', 0.85, 1.15),
                    ('P3(实体修正)', 'physical_composite', 0.60, 1.40),
                    ('P4(区位修正)', 'p4', 0.70, 1.30),
                ]

                for name, field, p_min, p_max in p_factors:
                    if hasattr(case, field):
                        val_obj = getattr(case, field)
                        val = val_obj.value if hasattr(val_obj, 'value') else val_obj

                        normalize_val = normalize_factor(val)

                        if normalize_val and (normalize_val < p_min or normalize_val > p_max):
                            issues.append(Issue(
                                level='warning',
                                category='reasonability',
                                description=f'实例{case_id}的{name}修正系数({val:.3f})超出常规范围({p_min}-{p_max})',
                                suggestion='请核实修正系数计算',
                            ))

                # 检查子系数
                sub_factors = [
                    ('结构系数', 'structure_factor', 0.85, 1.15),
                    ('楼层系数', 'floor_factor', 0.85, 1.15),
                    ('朝向系数', 'orientation_factor', 0.90, 1.10),
                    ('年代系数', 'age_factor', 0.80, 1.20),
                ]

                for name, field, p_min, p_max in sub_factors:
                    if hasattr(case, field):
                        val_obj = getattr(case, field)
                        val = val_obj.value if hasattr(val_obj, 'value') else val_obj

                        normalize_val = normalize_factor(val)
                        if normalize_val and (normalize_val < p_min or normalize_val > p_max):
                            issues.append(Issue(
                                level='info',
                                category='reasonability',
                                description=f'实例{case_id}的{name}={val:.3f}，可能需要核实',
                            ))
            else:
                corrections = [
                    ('交易情况', 'transaction_correction'),
                    ('市场状况', 'market_correction'),
                    ('区位状况', 'location_correction'),
                    ('实物状况', 'physical_correction'),
                    ('权益状况', 'rights_correction'),
                ]
            
                for name, field in corrections:
                    if hasattr(case, field):
                        val_obj = getattr(case, field)
                        if val_obj and hasattr(val_obj, 'value') and val_obj.value:
                            val = val_obj.value

                            normalize_val = normalize_factor(val)
                            if normalize_val < min_val or normalize_val > max_val:
                                issues.append(Issue(
                                    level='warning',
                                    category='reasonability',
                                    description=f'实例{case_id}的{name}修正系数({val:.3f})超出常规范围({min_val}-{max_val})',
                                    position={
                                        'table': val_obj.position.table_index if val_obj.position else 0,
                                        'row': val_obj.position.row_index if val_obj.position else 0,
                                        'col': val_obj.position.col_index if val_obj.position else 0,
                                    } if hasattr(val_obj, 'position') and val_obj.position else {},
                                    suggestion='请检查修正系数计算',
                                ))

        # 价格合理性检查
        for case in result.cases:
            case_id = getattr(case, 'case_id', '?')
            price = None

            if hasattr(case, 'transaction_price') and case.transaction_price and case.transaction_price.value:
                price = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price and case.rental_price.value:
                price = case.rental_price.value
            elif hasattr(case, 'final_price') and case.final_price and case.final_price.value:
                price = case.final_price.value

            if price:
                # 住宅价格范围检查（根据报告类型）
                if report_type == 'zujin':
                    if price < 50 or price > 2000:
                        issues.append(Issue(
                            level='warning',
                            category='reasonability',
                            description=f'实例{case_id}的成交价格({price:.0f}元/㎡·年)可能异常',
                            suggestion='租金通常在50-2000元/㎡·年范围内',
                        ))
                else:
                    if price < 1000 or price > 200000:
                        issues.append(Issue(
                            level='warning',
                            category='reasonability',
                            description=f'实例{case_id}的成交价格({price:.0f}元/㎡·年)可能异常',
                            suggestion='价格通常在1000-200000元/㎡·年范围内',
                        ))

        return issues
    
    def _check_formulas(self, result) -> List[FormulaCheck]:
        """反算校验"""
        checks = []
        tolerance = self.config.get('formula_tolerance', 10)

        def get_p_value(case, field_name, default=1.0):
            """获取 P 系数值和原始文本"""
            if not hasattr(case, field_name):
                return default, None

            val = getattr(case, field_name)
            if val is None:
                return default, None

            # 如果是 LocatedValue
            if hasattr(val, 'value'):
                raw = getattr(val, 'raw_text', str(val.value))
                return parse_ratio_to_float(val.value) or default, raw

            # 字符串或数字
            raw = str(val)
            parsed = parse_ratio_to_float(val)
            return parsed or default, raw

        report_type = getattr(result, 'type', None)
        if not report_type:
            if hasattr(result.cases[0], 'physical_composite') if result.cases else False:
                report_type = 'biaozhunfang'
            else:
                report_type = 'shezhi'

        for case in result.cases:
            case_id = getattr(case, 'case_id', '?')

            if report_type == 'biaozhunfang':
                # === 标准房公式验证 ===
                # 比准价格 = Vs X P1 X P2 X P3 X P4 -Va - Vbf

                # 获取可比实例成交价格 Vs
                vs = 0
                vs_raw = None
                if hasattr(case, 'transaction_price') and case.transaction_price and case.transaction_price.value:
                    vs = case.transaction_price.value
                    vs_raw = getattr(case.transaction_price, 'raw_text', str(vs))

                # 获取 P1, P2, P3(physical_composite), P4
                p1, p1_raw = get_p_value(case, 'p1_transaction', 1.0)
                p2, p2_raw = get_p_value(case, 'p2_date', 1.0)

                p3, p3_raw = 1.0, None
                if hasattr(case, 'p3_physical') and getattr(case, 'p3_physical'):
                    p3, p3_raw = get_p_value(case, 'p3_physical', 1.0)
                elif hasattr(case, 'physical_composite') and case.physical_composite:
                    if hasattr(case.physical_composite, 'value') and case.physical_composite.value:
                        p3 = case.physical_composite.value
                        p3_raw = getattr(case.physical_composite, 'raw_text', str(p3))


                p4, p4_raw = get_p_value(case, 'p4_location', 1.0)

                va = 0
                va_raw = None
                if hasattr(case, 'attachment_price') and case.attachment_price:
                    if hasattr(case.attachment_price, 'value'):
                        va = case.attachment_price.value or 0
                        va_raw = getattr(case.attachment_price, 'raw_text', str(va))
                    else:
                        va = parse_ratio_to_float(case.attachment_price) or 0
                        va_raw = str(case.attachment_price)

                vb = 0
                vb_raw = None
                if hasattr(case, 'decoration_price') and case.decoration_price:
                    if hasattr(case.decoration_price, 'value'):
                        vb = case.decoration_price.value or 0
                        vb_raw = getattr(case.decoration_price, 'raw_text', str(vb))
                    else:
                        vb = parse_ratio_to_float(case.decoration_price) or 0
                        vb_raw = str(case.decoration_price)

                # 获取实际比准价格
                final_price = 0
                final_price_position = {}
                if hasattr(case, 'final_price') and case.final_price and case.final_price.value:
                    final_price = case.final_price.value
                    if hasattr(case.final_price, 'position') and case.final_price.position:
                        final_price_position = {
                            'table': case.final_price.position.table_index,
                            'row': case.final_price.position.row_index,
                        }

                if vs > 0 and final_price > 0:
                    expected = vs * p1 * p2 * p3 * p4 - va - vb
                    diff = abs(expected - final_price)
                    # 使用百分比容差(1%)
                    tolerance_pct = max(expected * 0.01, tolerance)

                    # 构建输入参数
                    inputs = {
                        'vs': {'raw': vs_raw, 'value': vs},
                        'p1': {'raw': p1_raw, 'value': p1},
                        'p2': {'raw': p2_raw, 'value': p2},
                        'p3': {'raw': p3_raw, 'value': p3},
                        'p4': {'raw': p4_raw, 'value': p4},
                        'va': {'raw': va_raw, 'value': va},
                        'vb': {'raw': vb_raw, 'value': vb},
                    }

                    # 构建公式详情
                    formula_parts = [f"{vs:.2f}"]
                    if p1 != 1.0 or p1_raw:
                        formula_parts.append(f"×{p1:.4f}")
                    if p2 != 1.0 or p2_raw:
                        formula_parts.append(f"×{p2:.4f}")
                    formula_parts.append(f"×{p3:.4f}")
                    formula_parts.append(f"×{p4:.4f}")
                    if va > 0:
                        formula_parts.append(f"-{va:.2f}")
                    if vb > 0:
                        formula_parts.append(f"-{vb:.2f}")
                    formula_parts.append(f"={expected:.2f}")
                    formula_detail = "".join(formula_parts)

                    checks.append(FormulaCheck(
                        case_id=case_id,
                        formula_name='比准价格(VsxP1xP2xP3xP4-Va-Vb)',
                        expected=round(expected, 2),
                        actual=final_price,
                        difference=round(diff, 2),
                        is_valid=(diff < tolerance_pct),
                        position=final_price_position,
                        inputs=inputs,
                        formula_detail=formula_detail,
                    ))

                # 验证 P3 = 结构系数 x 楼层系数 x 朝向系数 x 成新系数 x 东西至修正
                def get_factor_value(case, field_name, default=1.0):
                    if not hasattr(case, field_name):
                        return default, None
                    val = getattr(case, field_name)
                    if val is None:
                        return default, None
                    if hasattr(val, 'value') and val.value:
                        # 判断是百分比还是小数
                        v = val.value
                        if v > 10:  # 百分比形式
                            v = v / 100
                        return v, getattr(val, 'raw_text', str(val.value))
                    return default, None

                sf, sf_raw = get_factor_value(case, 'structure_factor')
                ff, ff_raw = get_factor_value(case, 'floor_factor')
                of, of_raw = get_factor_value(case, 'orientation_factor')
                af, af_raw = get_factor_value(case, 'age_factor')
                ew, ew_raw = get_factor_value(case, 'east_to_west_factor')

                p3_composite, p3_composite_row = get_factor_value(case, 'physical_composite')

                # 如果至少有两个子系数有效，则验证 P3
                valid_factors = sum([
                    sf != 1.0 or sf_raw is not None,
                    ff != 1.0 or ff_raw is not None,
                    of != 1.0 or of_raw is not None,
                    af != 1.0 or af_raw is not None,
                    ew != 1.0 or ew_raw is not None,
                ])

                if valid_factors >= 2 and p3_composite != 1.0:
                    expected_p3 = sf * ff * of * af * ew
                    diff_p3 = abs(expected_p3 - p3_composite)

                    inputs_p3 = {
                        'sf': {'raw': sf_raw, 'value': sf},
                        'ff': {'raw': ff_raw, 'value': ff},
                        'of': {'raw': of_raw, 'value': of},
                        'af': {'raw': af_raw, 'value': af},
                        'ew': {'raw': ew_raw, 'value': ew},
                    }

                    formula_detail_p3 = f"{sf:.4f}×{ff:.4f}×{of:.4f}×{af:.4f}×{ew:.4f}={expected_p3:.4f}"

                    checks.append(FormulaCheck(
                        case_id=case_id,
                        formula_name='P3实体修正',
                        expected=round(expected_p3, 4),
                        actual=p3_composite,
                        difference=round(diff_p3, 4),
                        is_valid=(diff_p3 < 0.01),  # 允许1%误差
                        position={},
                        inputs=inputs_p3,
                        formula_detail=formula_detail_p3,
                    ))
            else:
                # === 涉执/租金 ===
                # 修正后单价 = 交易价格 × 交易修正 × 市场修正 × 区位修正 × 实物修正 × 权益修正

                trans = 0
                trans_raw = None
                if hasattr(case, 'transaction_price') and case.transaction_price and case.transaction_price.value:
                    trans = case.transaction_price.value
                    trans_raw = getattr(case.transaction_price, 'raw_text', str(trans))
                elif hasattr(case, 'rental_price') and case.rental_price and case.rental_price.value:
                    trans = case.rental_price.value
                    trans_raw = getattr(case.rental_price, 'raw_text', str(trans))

                adj = 0
                adj_position = {}
                if hasattr(case, 'adjusted_price') and case.adjusted_price and case.adjusted_price.value:
                    adj = case.adjusted_price.value
                    if hasattr(case.adjusted_price, 'position') and case.adjusted_price.position:
                        adj_position = {
                            'table': case.adjusted_price.position.table_index,
                            'row': case.adjusted_price.position.row_index,
                        }

                if trans > 0 and adj > 0:
                    def get_correction(case, field_name):
                        if not hasattr(case, field_name):
                            return 1.0, None
                        val = getattr(case, field_name)
                        if val is None:
                            return 1.0, None
                        if hasattr(val, 'value') and val.value:
                            return val.value, getattr(val, 'raw_text', str(val.value))
                        return 1.0, None

                    tc, tc_raw = get_correction(case, 'transaction_correction')
                    mc, mc_raw = get_correction(case, 'market_correction')
                    lc, lc_raw = get_correction(case, 'location_correction')
                    pc, pc_raw = get_correction(case, 'physical_correction')
                    rc, rc_raw = get_correction(case, 'rights_correction')

                    expected = trans * tc * mc * lc * pc * rc
                    diff = abs(expected - adj)
                    # 使用百分比容差(1%)
                    tolerance_pct = max(expected * 0.01, tolerance)

                    inputs = {
                        'trans': {'raw': trans_raw, 'value': trans},
                        'tc': {'raw': tc_raw, 'value': tc},
                        'mc': {'raw': mc_raw, 'value': mc},
                        'lc': {'raw': lc_raw, 'value': lc},
                        'pc': {'raw': pc_raw, 'value': pc},
                        'rc': {'raw': rc_raw, 'value': rc},
                    }

                    formula_detail = f"{trans:.2f}×{tc:.4f}×{mc:.4f}×{lc:.4f}×{pc:.4f}×{rc:.4f}={expected:.2f}"

                    checks.append(FormulaCheck(
                        case_id=case_id,
                        formula_name='修正后单价',
                        expected=round(expected, 2),
                        actual=adj,
                        difference=round(diff, 2),
                        is_valid=(diff < tolerance_pct),
                        position=adj_position,
                        inputs=inputs,
                        formula_detail=formula_detail,
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
