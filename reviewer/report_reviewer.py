"""
报告审查器
==========
对比知识库审查新文件，发现异常
"""

import os
import sys
from typing import List, Dict, Optional
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractors import extract_report
from validators import validate_report, ValidationResult
from knowledge_base import KnowledgeBaseManager, KnowledgeBaseQuery
from utils import convert_doc_to_docx, detect_report_type
from reviewer.llm_reviewer import LLMReviewer, LLMReviewResult, LLMIssue


@dataclass
class ComparisonResult:
    """对比结果"""
    item: str
    current_value: any
    kb_min: float
    kb_max: float
    kb_avg: float
    is_abnormal: bool
    description: str = ""


@dataclass
class ReviewResult:
    """审查结果"""
    # 基础校验
    validation: ValidationResult = None
    
    # 知识库对比
    comparisons: List[ComparisonResult] = field(default_factory=list)
    similar_cases: List[Dict] = field(default_factory=list)
    
    # LLM语义审查
    llm_issues: List[LLMIssue] = field(default_factory=list)
    llm_error: str = ""  # LLM调用错误信息
    
    # 综合评估
    overall_risk: str = "low"  # low / medium / high
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)


class ReportReviewer:
    """报告审查器"""
    
    def __init__(self, kb_manager: KnowledgeBaseManager, enable_llm: bool = True):
        """
        Args:
            kb_manager: 知识库管理器
            enable_llm: 是否启用LLM语义审查
        """
        self.kb = kb_manager
        self.query = KnowledgeBaseQuery(kb_manager)
        self.enable_llm = enable_llm
        self.llm_reviewer = LLMReviewer() if enable_llm else None
    
    def review(self, doc_path: str, verbose: bool = True) -> ReviewResult:
        """
        审查报告
        
        Args:
            doc_path: 文档路径
            verbose: 是否打印详情
        
        Returns:
            ReviewResult
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"🔍 审查报告: {os.path.basename(doc_path)}")
            print(f"{'='*60}")
        
        # 处理doc文件
        if doc_path.lower().endswith('.doc'):
            doc_path = convert_doc_to_docx(doc_path)
        
        # 检测类型
        report_type = detect_report_type(doc_path)
        
        # 提取数据
        result = extract_report(doc_path)
        
        # 1. 基础校验
        validation = validate_report(result)
        if verbose:
            print(f"\n📋 基础校验: {validation.summary}")
        
        # 2. 与知识库对比
        comparisons = self._compare_with_kb(result, report_type)
        if verbose and comparisons:
            abnormal = [c for c in comparisons if c.is_abnormal]
            print(f"📊 知识库对比: {len(abnormal)} 项异常")
        
        # 3. 查找相似案例
        similar_cases = self._find_similar(result, report_type)
        if verbose:
            print(f"🔎 相似案例: {len(similar_cases)} 个")
        
        # 4. LLM语义审查
        llm_issues = []
        llm_error = ""
        if self.enable_llm and self.llm_reviewer and self.llm_reviewer.is_available():
            if verbose:
                print(f"🤖 LLM语义审查...")
            llm_result = self.llm_reviewer.review(result, report_type)
            llm_issues = llm_result.issues
            llm_error = llm_result.error_message
            if verbose:
                print(f"   发现 {len(llm_issues)} 个语义问题")
        elif verbose and self.enable_llm:
            print(f"🤖 LLM未配置，跳过语义审查")
        
        # 5. 综合评估
        review_result = ReviewResult(
            validation=validation,
            comparisons=comparisons,
            similar_cases=similar_cases,
            llm_issues=llm_issues,
            llm_error=llm_error,
        )
        
        self._evaluate(review_result)
        
        if verbose:
            self._print_result(review_result)
        
        return review_result
    
    def _compare_with_kb(self, result, report_type: str) -> List[ComparisonResult]:
        """与知识库对比"""
        comparisons = []
        
        # 获取知识库统计
        price_stats = self.query.get_price_range(report_type)
        area_stats = self.query.get_area_range(report_type)
        correction_stats = self.query.get_correction_stats(report_type)
        
        # 如果知识库没有数据，跳过对比
        if price_stats['count'] == 0:
            return comparisons
        
        # 对比每个案例
        for case in result.cases:
            # 价格对比
            price = None
            if hasattr(case, 'transaction_price') and case.transaction_price.value:
                price = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price.value:
                price = case.rental_price.value
            elif hasattr(case, 'final_price') and case.final_price.value:
                price = case.final_price.value
            
            if price and price_stats['count'] > 0:
                is_abnormal = price < price_stats['min'] * 0.5 or price > price_stats['max'] * 1.5
                comparisons.append(ComparisonResult(
                    item=f"实例{case.case_id}价格",
                    current_value=price,
                    kb_min=price_stats['min'],
                    kb_max=price_stats['max'],
                    kb_avg=price_stats['avg'],
                    is_abnormal=is_abnormal,
                    description="价格明显偏离知识库范围" if is_abnormal else "",
                ))
            
            # 修正系数对比
            for name, field in [
                ('区位修正', 'location_correction'),
                ('实物修正', 'physical_correction'),
            ]:
                if hasattr(case, field):
                    val = getattr(case, field).value
                    key = field.replace('_correction', '')
                    stats = correction_stats.get(key, {})
                    
                    if val and stats.get('count', 0) > 0:
                        is_abnormal = val < stats['min'] * 0.8 or val > stats['max'] * 1.2
                        comparisons.append(ComparisonResult(
                            item=f"实例{case.case_id}{name}",
                            current_value=val,
                            kb_min=stats['min'],
                            kb_max=stats['max'],
                            kb_avg=stats['avg'],
                            is_abnormal=is_abnormal,
                            description=f"{name}系数偏离知识库范围" if is_abnormal else "",
                        ))
        
        return comparisons
    
    def _find_similar(self, result, report_type: str) -> List[Dict]:
        """查找相似案例"""
        # 获取估价对象信息
        address = result.subject.address.value or ""
        area = result.subject.building_area.value or 0
        
        # 获取价格参考
        price = 0
        if hasattr(result, 'final_unit_price') and result.final_unit_price.value:
            price = result.final_unit_price.value
        
        # 查找相似案例
        similar = self.query.find_similar_cases(
            address=address,
            area=area,
            price=price,
            report_type=report_type,
            top_k=5
        )
        
        return [case for case, score in similar]
    
    def _evaluate(self, review_result: ReviewResult):
        """综合评估"""
        # 计算风险等级
        error_count = len([i for i in review_result.validation.issues if i.level == 'error'])
        warning_count = len([i for i in review_result.validation.issues if i.level == 'warning'])
        abnormal_count = len([c for c in review_result.comparisons if c.is_abnormal])
        llm_critical = len([i for i in review_result.llm_issues if i.severity == 'critical'])
        llm_major = len([i for i in review_result.llm_issues if i.severity == 'major'])
        
        if error_count > 0 or abnormal_count > 2 or llm_critical > 0:
            review_result.overall_risk = 'high'
        elif warning_count > 3 or abnormal_count > 0 or llm_major > 0:
            review_result.overall_risk = 'medium'
        else:
            review_result.overall_risk = 'low'
        
        # 生成摘要
        parts = []
        if error_count > 0:
            parts.append(f"{error_count}个严重错误")
        if warning_count > 0:
            parts.append(f"{warning_count}个警告")
        if abnormal_count > 0:
            parts.append(f"{abnormal_count}项数据异常")
        if len(review_result.llm_issues) > 0:
            parts.append(f"{len(review_result.llm_issues)}个语义问题")
        
        if parts:
            review_result.summary = f"发现 " + "，".join(parts)
        else:
            review_result.summary = "未发现明显问题"
        
        # 生成建议
        if error_count > 0:
            review_result.recommendations.append("请先修正数据完整性问题")
        if abnormal_count > 0:
            review_result.recommendations.append("请核实偏离知识库范围的数据")
        if len(review_result.llm_issues) > 0:
            review_result.recommendations.append("请关注LLM发现的语义问题")
        if len(review_result.similar_cases) > 0:
            review_result.recommendations.append("可参考相似案例进行核对")
    
    def _print_result(self, review_result: ReviewResult):
        """打印结果"""
        print(f"\n{'='*60}")
        print(f"📋 审查结果")
        print(f"{'='*60}")
        
        # 风险等级
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        print(f"风险等级: {risk_icon.get(review_result.overall_risk, '')} {review_result.overall_risk}")
        print(f"摘要: {review_result.summary}")
        
        # 基础校验问题
        if review_result.validation.issues:
            print(f"\n基础校验问题 ({len(review_result.validation.issues)} 个):")
            for i, issue in enumerate(review_result.validation.issues, 1):
                icon = "❌" if issue.level == 'error' else "⚠️"
                print(f"  {i}. {icon} [{issue.category}] {issue.description}")
                if issue.position:
                    print(f"      📍 位置: 表格{issue.position.get('table', 0)+1}, 第{issue.position.get('row', 0)+1}行")
        
        # 公式验证
        if review_result.validation.formula_checks:
            print(f"\n公式验证 ({len(review_result.validation.formula_checks)} 项):")
            for fc in review_result.validation.formula_checks:
                status = "✓" if fc.is_valid else "✗"
                print(f"  {status} 实例{fc.case_id}: 期望{fc.expected:.0f} 实际{fc.actual:.0f} 差异{fc.difference:.0f}")
        
        # 知识库对比
        abnormal = [c for c in review_result.comparisons if c.is_abnormal]
        if abnormal:
            print(f"\n知识库对比异常 ({len(abnormal)} 项):")
            for c in abnormal:
                print(f"  ⚠️ {c.item}: {c.current_value:.2f}")
                print(f"      知识库范围: {c.kb_min:.2f} ~ {c.kb_max:.2f} (平均: {c.kb_avg:.2f})")
        
        # LLM语义审查问题
        if review_result.llm_issues:
            print(f"\nLLM语义审查 ({len(review_result.llm_issues)} 个问题):")
            for i, issue in enumerate(review_result.llm_issues, 1):
                severity_icon = {"critical": "🔴", "major": "🟠", "minor": "🟡"}.get(issue.severity, "⚪")
                print(f"  {i}. {severity_icon} [{issue.type}] {issue.description}")
                if issue.case_id:
                    print(f"      涉及: 实例{issue.case_id}")
                if issue.factor:
                    print(f"      因素: {issue.factor}")
                if issue.suggestion:
                    print(f"      建议: {issue.suggestion}")
        
        if review_result.llm_error:
            print(f"\n⚠️ LLM审查异常: {review_result.llm_error}")
        
        # 相似案例
        if review_result.similar_cases:
            print(f"\n相似案例参考 ({len(review_result.similar_cases)} 个):")
            for case in review_result.similar_cases[:3]:
                addr = case.get('address', {}).get('value', '未知')
                price = case.get('transaction_price', {}).get('value') or \
                        case.get('rental_price', {}).get('value') or \
                        case.get('final_price', {}).get('value') or 0
                print(f"  - {addr}: {price:.0f}元/㎡")
        
        # 建议
        if review_result.recommendations:
            print(f"\n💡 建议:")
            for rec in review_result.recommendations:
                print(f"  • {rec}")


# ============================================================================
# 便捷函数
# ============================================================================

def review_report(doc_path: str, kb_path: str = "./knowledge_base/storage", verbose: bool = True) -> ReviewResult:
    """审查报告的便捷函数"""
    kb = KnowledgeBaseManager(kb_path)
    reviewer = ReportReviewer(kb)
    return reviewer.review(doc_path, verbose)
