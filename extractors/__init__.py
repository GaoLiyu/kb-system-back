"""
提取器模块
==========
从Word文档提取结构化数据
"""

import os

from .shezhi_extractor import ShezhiExtractor, ShezhiExtractionResult
from .zujin_extractor import ZujinExtractor, ZujinExtractionResult
from .biaozhunfang_extractor import BiaozhunfangExtractor, BiaozhunfangExtractionResult
from .xianzhi_extractor import XianzhibExtractor, XianzhibExtractionResult
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
        提取结果（ShezhiExtractionResult / ZujinExtractionResult / BiaozhunfangExtractionResult / XianzhibExtractionResult）
    """
    filename = os.path.basename(doc_path).lower()

    # 税务标准房
    if '标准房' in filename or 'biaozhunfang' in filename or '电梯多层' in filename or '税务' in filename:
        return BiaozhunfangExtractor().extract(doc_path)

    # 租金评估
    elif '租金' in filename or 'zujin' in filename:
        return ZujinExtractor().extract(doc_path)

    # 市场价值-现状价值（批量评估）
    elif '现值' in filename or '现状价值' in filename or '市场价值' in filename or 'xianzhi' in filename:
        return XianzhibExtractor().extract(doc_path)

    # 司法评估（人民法院）- 使用ShezhiExtractor + 自动检测
    elif '司法' in filename or '人民法院' in filename or 'sifa' in filename:
        extractor = ShezhiExtractor()
        extractor.auto_detect = True  # 启用自动检测表格索引
        return extractor.extract(doc_path)

    # 涉执报告
    elif '涉执' in filename or 'shezhi' in filename:
        return ShezhiExtractor().extract(doc_path)

    else:
        # 默认用涉执，启用自动检测
        extractor = ShezhiExtractor()
        extractor.auto_detect = True
        return extractor.extract(doc_path)


__all__ = [
    'ShezhiExtractor',
    'ZujinExtractor',
    'BiaozhunfangExtractor',
    'XianzhibExtractor',
    'ShezhiExtractionResult',
    'ZujinExtractionResult',
    'BiaozhunfangExtractionResult',
    'XianzhibExtractionResult',
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
