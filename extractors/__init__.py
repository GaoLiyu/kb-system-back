"""
提取器模块
==========
从Word文档提取结构化数据
"""

import os

from .shezhi_extractor import ShezhiExtractor, ShezhiExtractionResult
from .zujin_extractor import ZujinExtractor, ZujinExtractionResult
from .biaozhunfang_extractor import BiaozhunfangExtractor, BiaozhunfangExtractionResult
from .content_extractor import (
    extract_document_content,
    content_to_dict,
    get_paragraphs_text,
    get_filtered_paragraphs_for_review,
    mark_issues,
    DocumentContent,
    ContentItem,
)


def extract_report(doc_path: str):
    """
    根据文件名自动选择提取器并提取数据

    Args:
        doc_path: 文档路径

    Returns:
        提取结果（ShezhiExtractionResult / ZujinExtractionResult / BiaozhunfangExtractionResult）
    """
    filename = os.path.basename(doc_path).lower()

    if '涉执' in filename or 'shezhi' in filename:
        return ShezhiExtractor().extract(doc_path)
    elif '租金' in filename or 'zujin' in filename:
        return ZujinExtractor().extract(doc_path)
    elif '标准房' in filename or 'biaozhunfang' in filename:
        return BiaozhunfangExtractor().extract(doc_path)
    else:
        # 默认用涉执
        return ShezhiExtractor().extract(doc_path)


__all__ = [
    'ShezhiExtractor',
    'ZujinExtractor',
    'BiaozhunfangExtractor',
    'ShezhiExtractionResult',
    'ZujinExtractionResult',
    'BiaozhunfangExtractionResult',
    'extract_report',
    # 内容提取
    'extract_document_content',
    'content_to_dict',
    'get_paragraphs_text',
    'get_filtered_paragraphs_for_review',
    'mark_issues',
    'DocumentContent',
    'ContentItem',
]
