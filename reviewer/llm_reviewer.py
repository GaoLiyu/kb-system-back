"""
LLM语义审查器
=============
使用大模型进行语义级别的审查
"""

import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm_client import get_llm_client, LLMClient
from reviewer.prompts import (
    build_report_review_prompt,
    build_comparison_review_prompt,
    build_factor_review_prompt,
    build_paragraph_review_prompt,
    build_full_document_review_prompt,
)


@dataclass
class LLMIssue:
    """LLM发现的问题"""
    type: str               # CONSISTENCY/LOGIC/CALCULATION等
    severity: str           # minor/major/critical
    description: str        # 问题描述
    span: str = ""          # 原文片段
    suggestion: str = ""    # 修改建议
    case_id: str = ""       # 涉及的实例ID
    factor: str = ""        # 涉及的因素
    paragraph_index: int = None  # 段落索引（用于前端高亮）


@dataclass
class LLMReviewResult:
    """LLM审查结果"""
    issues: List[LLMIssue] = field(default_factory=list)
    raw_responses: List[Dict] = field(default_factory=list)  # 原始响应（调试用）
    error_message: str = ""  # 如果调用失败


class LLMReviewer:
    """LLM语义审查器"""

    def __init__(self, llm_client: LLMClient = None):
        """
        初始化

        Args:
            llm_client: LLM客户端，不传则使用默认配置
        """
        self.llm = llm_client or get_llm_client()

    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self.llm.is_available()

    def review(self, extraction_result, report_type: str = "shezhi") -> LLMReviewResult:
        """
        审查提取结果

        Args:
            extraction_result: 提取结果对象
            report_type: 报告类型

        Returns:
            LLMReviewResult
        """
        if not self.is_available():
            return LLMReviewResult(error_message="LLM未配置，跳过语义审查")

        result = LLMReviewResult()

        # 1. 审查可比实例关系
        try:
            comparison_issues = self._review_comparison(extraction_result, report_type)
            result.issues.extend(comparison_issues)
        except Exception as e:
            result.error_message += f"比较审查失败: {e}\n"

        # 2. 审查因素等级与指数
        try:
            factor_issues = self._review_factors(extraction_result)
            result.issues.extend(factor_issues)
        except Exception as e:
            result.error_message += f"因素审查失败: {e}\n"

        return result

    def _review_comparison(self, result, report_type: str) -> List[LLMIssue]:
        """审查估价对象与可比实例的关系"""
        issues = []

        # 准备估价对象数据
        subject = result.subject
        subject_data = {
            'address': subject.address.value if subject.address else '',
            'area': subject.building_area.value if subject.building_area else 0,
            'usage': getattr(subject, 'usage', ''),
        }

        # 准备可比实例数据
        cases_data = []
        for case in result.cases:
            case_dict = {
                'case_id': case.case_id,
                'address': case.address.value if case.address else '',
                'area': case.building_area.value if hasattr(case, 'building_area') and case.building_area else 0,
            }

            # 价格
            if hasattr(case, 'transaction_price') and case.transaction_price.value:
                case_dict['price'] = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price.value:
                case_dict['price'] = case.rental_price.value
            else:
                case_dict['price'] = 0

            # 修正系数
            for field in ['transaction_correction', 'market_correction', 'location_correction',
                          'physical_correction', 'rights_correction', 'adjusted_price']:
                if hasattr(case, field):
                    val = getattr(case, field)
                    case_dict[field] = val.value if hasattr(val, 'value') else val

            # 因素
            for factor_type in ['location_factors', 'physical_factors']:
                if hasattr(case, factor_type):
                    factors = getattr(case, factor_type)
                    if factors:
                        case_dict[factor_type] = {
                            k: f"{v.level}(指数{v.index})"
                            for k, v in factors.items()
                        }

            cases_data.append(case_dict)

        # 调用LLM
        prompt = build_comparison_review_prompt(subject_data, cases_data, report_type)
        response = self.llm.call_json(prompt)

        # 解析结果
        for error in response.get('errors', []):
            issues.append(LLMIssue(
                type=error.get('type', 'UNKNOWN'),
                severity=error.get('severity', 'minor'),
                description=error.get('comment', ''),
                suggestion=error.get('suggestion', ''),
                case_id=error.get('case_id', ''),
                factor=error.get('factor', ''),
            ))

        return issues

    def _review_factors(self, result) -> List[LLMIssue]:
        """审查因素等级与指数"""
        issues = []

        # 收集所有因素数据
        factors_data = []
        for case in result.cases:
            for factor_type in ['location_factors', 'physical_factors', 'rights_factors']:
                if not hasattr(case, factor_type):
                    continue

                factors = getattr(case, factor_type)
                if not factors:
                    continue

                for name, factor in factors.items():
                    factors_data.append({
                        'case_id': case.case_id,
                        'factor_name': name,
                        'level': factor.level,
                        'index': factor.index,
                    })

        if not factors_data:
            return issues

        # 调用LLM
        prompt = build_factor_review_prompt(factors_data)
        response = self.llm.call_json(prompt)

        # 解析结果
        for error in response.get('errors', []):
            issues.append(LLMIssue(
                type='FACTOR_MISMATCH',
                severity='warning',
                description=error.get('comment', ''),
                suggestion=error.get('suggestion', ''),
                case_id=error.get('case_id', ''),
                factor=error.get('factor_name', ''),
            ))

        return issues

    def review_text(self, text: str, report_type: str = "shezhi") -> LLMReviewResult:
        """
        审查文本片段

        Args:
            text: 报告文本
            report_type: 报告类型

        Returns:
            LLMReviewResult
        """
        if not self.is_available():
            return LLMReviewResult(error_message="LLM未配置")

        result = LLMReviewResult()

        # 如果文本太长，分块处理
        max_chunk = 3000
        chunks = []

        if len(text) <= max_chunk:
            chunks = [text]
        else:
            # 简单分块
            for i in range(0, len(text), max_chunk - 200):
                chunks.append(text[i:i + max_chunk])

        for chunk in chunks:
            try:
                prompt = build_report_review_prompt(chunk, report_type)
                response = self.llm.call_json(prompt)
                result.raw_responses.append(response)

                for error in response.get('errors', []):
                    result.issues.append(LLMIssue(
                        type=error.get('type', 'UNKNOWN'),
                        severity=error.get('severity', 'minor'),
                        description=error.get('comment', ''),
                        span=error.get('span', ''),
                        suggestion=error.get('suggestion', ''),
                    ))
            except Exception as e:
                result.error_message += f"审查失败: {e}\n"

        return result

    def review_paragraphs(self, paragraphs: list, report_type: str = "shezhi") -> LLMReviewResult:
        """
        审查段落列表（只审查文本段落，不审查表格）

        Args:
            paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
            report_type: 报告类型

        Returns:
            LLMReviewResult，issues中包含paragraph_index字段
        """
        if not self.is_available():
            return LLMReviewResult(error_message="LLM未配置")

        result = LLMReviewResult()

        if not paragraphs:
            return result

        # 如果段落太多，分批处理
        batch_size = 50
        for i in range(0, len(paragraphs), batch_size):
            batch = paragraphs[i:i + batch_size]

            try:
                prompt = build_paragraph_review_prompt(batch, report_type)
                response = self.llm.call_json(prompt)
                result.raw_responses.append(response)

                for error in response.get('errors', []):
                    issue = LLMIssue(
                        type=error.get('type', 'UNKNOWN'),
                        severity=error.get('severity', 'minor'),
                        description=error.get('comment', ''),
                        span=error.get('span', ''),
                        suggestion=error.get('suggestion', ''),
                    )
                    # 添加段落索引
                    issue.paragraph_index = error.get('paragraph_index')
                    result.issues.append(issue)
            except Exception as e:
                result.error_message += f"段落审查失败: {e}\n"

        return result

    def review_full_document(self, paragraphs: list, report_type: str = "shezhi") -> LLMReviewResult:
        """
        全文审查（一次性发送整个文档，保持上下文连贯性）

        相比 review_paragraphs，此方法：
        1. 将整个文档作为一个整体发送给LLM
        2. LLM可以理解段落之间的上下文关系
        3. 避免将"标题+解释"这种正常结构误报为问题

        Args:
            paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
            report_type: 报告类型

        Returns:
            LLMReviewResult，issues中包含paragraph_index字段
        """
        if not self.is_available():
            return LLMReviewResult(error_message="LLM未配置")

        result = LLMReviewResult()

        if not paragraphs:
            return result

        # 计算总token数（粗略估计：中文约1.5字/token）
        total_chars = sum(len(p.get('text', '')) for p in paragraphs)
        estimated_tokens = int(total_chars / 1.5)

        # 如果超过20K tokens，需要分段处理（保留buffer给输出）
        max_input_tokens = 20000

        if estimated_tokens <= max_input_tokens:
            # 全文一次性审查
            result = self._review_document_batch(paragraphs, report_type)
        else:
            # 文档太长，智能分段
            result = self._review_document_chunked(paragraphs, report_type, max_input_tokens)

        return result

    def _review_document_batch(self, paragraphs: list, report_type: str) -> LLMReviewResult:
        """
        审查一批段落（内部方法）
        """
        result = LLMReviewResult()

        try:
            prompt = build_full_document_review_prompt(paragraphs, report_type)
            response = self.llm.call_json(prompt)
            result.raw_responses.append(response)

            # 解析错误
            for error in response.get('errors', []):
                issue = LLMIssue(
                    type=error.get('type', 'UNKNOWN'),
                    severity=error.get('severity', 'minor'),
                    description=error.get('comment', ''),
                    span=error.get('span', ''),
                    suggestion=error.get('suggestion', ''),
                )
                # 段落索引
                issue.paragraph_index = error.get('paragraph_index')
                result.issues.append(issue)

        except Exception as e:
            result.error_message = f"全文审查失败: {e}"

        return result

    def _review_document_chunked(self, paragraphs: list, report_type: str, max_tokens: int) -> LLMReviewResult:
        """
        分块审查长文档（保持上下文窗口重叠）
        """
        result = LLMReviewResult()

        # 按结构分块（尝试在标题处分割）
        chunks = self._split_by_structure(paragraphs, max_tokens)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                chunk_result = self._review_document_batch(chunk, report_type)
                result.issues.extend(chunk_result.issues)
                result.raw_responses.extend(chunk_result.raw_responses)

                if chunk_result.error_message:
                    result.error_message += f"[分块{chunk_idx + 1}] {chunk_result.error_message}\n"

            except Exception as e:
                result.error_message += f"[分块{chunk_idx + 1}] 审查失败: {e}\n"

        return result

    def _split_by_structure(self, paragraphs: list, max_tokens: int) -> list:
        """
        按文档结构智能分块

        尝试在标题段落处分割，避免打断"标题+内容"的结构
        """
        import re

        chunks = []
        current_chunk = []
        current_tokens = 0

        # 标题模式
        title_pattern = re.compile(
            r'^[\d一二三四五六七八九十]+[、\.．]|'  # 1、 2. 一、
            r'^[（(][一二三四五六七八九十\d]+[)）]|'  # (一) （1）
            r'^第[一二三四五六七八九十\d]+[章节条款]|'  # 第一章
            r'^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+[、\.]'  # Ⅰ、
        )

        for p in paragraphs:
            text = p.get('text', '')
            p_tokens = int(len(text) / 1.5)

            # 检查是否是标题
            is_title = bool(title_pattern.match(text.strip()))

            # 如果当前块已满且遇到标题，开始新块
            if current_tokens + p_tokens > max_tokens and current_chunk:
                if is_title or current_tokens > max_tokens * 0.8:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_tokens = 0

            current_chunk.append(p)
            current_tokens += p_tokens

        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)

        return chunks


# ============================================================================
# 便捷函数
# ============================================================================

def llm_review(extraction_result, report_type: str = "shezhi") -> LLMReviewResult:
    """LLM审查便捷函数"""
    reviewer = LLMReviewer()
    return reviewer.review(extraction_result, report_type)


def llm_review_paragraphs(paragraphs: list, report_type: str = "shezhi") -> LLMReviewResult:
    """
    LLM审查段落便捷函数

    Args:
        paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
        report_type: 报告类型

    Returns:
        LLMReviewResult
    """
    reviewer = LLMReviewer()
    return reviewer.review_paragraphs(paragraphs, report_type)


def llm_review_full_document(paragraphs: list, report_type: str = "shezhi") -> LLMReviewResult:
    """
    LLM全文审查便捷函数（推荐使用）

    相比 llm_review_paragraphs，此函数：
    1. 将整个文档作为一个整体发送给LLM
    2. LLM可以理解段落之间的上下文关系
    3. 避免将"标题+解释"这种正常结构误报为问题

    Args:
        paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
        report_type: 报告类型

    Returns:
        LLMReviewResult
    """
    reviewer = LLMReviewer()
    return reviewer.review_full_document(paragraphs, report_type)