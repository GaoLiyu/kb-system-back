"""
提取器模块
==========
从Word文档提取结构化数据
"""

import os

from .text_utils import (
    normalize_text, normalize_label, parse_number, parse_floor,
    match_field, find_matching_field, extract_year, extract_date,
    FIELD_SYNONYMS
)
from .table_utils import (
    get_effective_row_cells, row_to_text_list, get_row_cells_simple,
    find_header_row, find_column_indices, find_row_by_label, find_rows_by_labels,
    score_table_type, auto_detect_tables, extract_property_rights_generic,
    TABLE_TYPE_RULES
)
from .base_extractor import (
    BaseExtractor, LocatedValue, Position, Factor,
    ExtractionStats, ExtractionWarning
)

from .biaozhunfang_extractor import (
    BiaozhunfangExtractor,
    BiaozhunfangExtractionResult,
    Case as BiaozhunfangCase,
    Subject as BiaozhunfangSubject
)

from .shezhi_extractor import (
    ShezhiExtractor,
    ShezhiExtractionResult,
    Case as ShezhiCase,
    Subject as ShezhiSubject
)

from .zujin_extractor import (
    ZujinExtractor,
    ZujinExtractionResult,
    Case as ZujinCase,
    Subject as ZujinSubject
)


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


def extract_report(doc_path: str, report_type: str = None, original_filename: str = None):
    """
    根据文件名或指定类型自动选择提取器并提取数据

    Args:
        doc_path: 文档路径
        report_type: 报告类型（可选），支持 'biaozhunfang', 'zujin', 'shezhi'
        original_filename:

    Returns:
        提取结果（BiaozhunfangExtractionResult / ZujinExtractionResult / ShezhiExtractionResult）
    """
    filename = (original_filename or os.path.basename(doc_path)).lower()

    # 税务标准房
    if report_type == 'biaozhunfang' or '标准房' in filename or 'biaozhunfang' in filename or '电梯多层' in filename or '税务' in filename:
        return BiaozhunfangExtractor(auto_detect=True).extract(doc_path)

    # 租金评估
    elif report_type == 'zujin' or  '租金' in filename or 'zujin' in filename:
        return ZujinExtractor(auto_detect=True).extract(doc_path)

    # 市场价值-现状价值（批量评估）
    elif report_type == 'xianzhi' or  '现值' in filename or '现状价值' in filename or '市场价值' in filename or 'xianzhi' in filename:
        return XianzhibExtractor().extract(doc_path)

    # 司法评估（人民法院）- 使用ShezhiExtractor + 自动检测
    elif  report_type == 'shezhi' or '司法' in filename or '人民法院' in filename or 'sifa' in filename or '涉执' in filename:
        return ShezhiExtractor(auto_detect=True).extract(doc_path)

    else:
        # 默认用涉执，启用自动检测
        extractor = ShezhiExtractor()
        extractor.auto_detect = True
        return extractor.extract(doc_path)

# 兼容旧版本的类名导出
BiaozhunfangCase = BiaozhunfangCase
ShezhiCase = ShezhiCase
ZujinCase = ZujinCase

__all__ = [
    # 基础工具
    'normalize_text',
    'normalize_label',
    'parse_number',
    'parse_floor',
    'match_field',
    'find_matching_field',
    'extract_year',
    'extract_date',
    'FIELD_SYNONYMS',

    # 表格工具
    'get_effective_row_cells',
    'row_to_text_list',
    'get_row_cells_simple',
    'find_header_row',
    'find_column_indices',
    'find_row_by_label',
    'find_rows_by_labels',
    'score_table_type',
    'auto_detect_tables',
    'extract_property_rights_generic',
    'TABLE_TYPE_RULES',

    # 基类和数据结构
    'BaseExtractor',
    'Position',
    'LocatedValue',
    'Factor',
    'ExtractionWarning',
    'ExtractionStats',

    # 提取器
    'BiaozhunfangExtractor',
    'ShezhiExtractor',
    'ZujinExtractor',

    # 提取结果
    'BiaozhunfangExtractionResult',
    'ShezhiExtractionResult',
    'ZujinExtractionResult',

    # Case 和 Subject 类
    'BiaozhunfangCase',
    'BiaozhunfangSubject',
    'ShezhiCase',
    'ShezhiSubject',
    'ZujinCase',
    'ZujinSubject',

    # 便捷函数
    'extract_report',

    'XianzhibExtractor',
    'XianzhibExtractionResult',

    # 内容提取
    'extract_document_content',
    'content_to_dict',
    'get_paragraphs_text',
    'get_filtered_paragraphs_for_review',
    'mark_issues',
    'DocumentContent',
    'ContentItem',
]
