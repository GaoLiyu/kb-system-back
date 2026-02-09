"""
类型定义模块
============
统一管理项目中的类型定义
"""

from typing import Union, Dict, Any, List, Optional, TypeVar, Generic
from dataclasses import dataclass

# ============================================================================
# 提取结果类型
# ============================================================================

# 导入各种提取结果类型
from extractors.shezhi_extractor import ShezhiExtractionResult
from extractors.zujin_extractor import ZujinExtractionResult
from extractors.biaozhunfang_extractor import BiaozhunfangExtractionResult
from extractors.xianzhi_extractor import XianzhibExtractionResult

# 联合类型
ExtractionResult = Union[
    ShezhiExtractionResult,
    ZujinExtractionResult,
    BiaozhunfangExtractionResult,
    XianzhibExtractionResult,
]

# ============================================================================
# 报告类型枚举
# ============================================================================

from enum import Enum


class ReportType(str, Enum):
    """报告类型"""
    SHEZHI = "shezhi"  # 涉执报告
    ZUJIN = "zujin"  # 租金报告
    BIAOZHUNFANG = "biaozhunfang"  # 标准房报告
    XIANZHI = "xianzhi"  # 现值报告


# ============================================================================
# 通用数据类型
# ============================================================================

@dataclass
class LocatedValue:
    """带位置信息的值"""
    value: Any = None
    position: Optional[Dict[str, int]] = None

    def __bool__(self):
        return self.value is not None


@dataclass
class CaseInfo:
    """案例基本信息"""
    case_id: str
    address: str
    area: float
    price: float
    district: str = ""
    usage: str = ""
    report_type: str = ""


@dataclass
class SearchResult:
    """搜索结果"""
    case: Dict[str, Any]
    score: float


# ============================================================================
# API 响应类型
# ============================================================================

T = TypeVar('T')


@dataclass
class APIResponse(Generic[T]):
    """API 响应基类"""
    success: bool = True
    message: str = ""
    data: Optional[T] = None


@dataclass
class PaginatedData(Generic[T]):
    """分页数据"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# 类型别名
# ============================================================================

# JSON 类型
JSON = Dict[str, Any]
JSONList = List[Dict[str, Any]]

# 案例数据
CaseData = Dict[str, Any]
CaseList = List[CaseData]

# 搜索结果
SearchResults = List[SearchResult]

__all__ = [
    # 提取结果
    'ExtractionResult',
    'ShezhiExtractionResult',
    'ZujinExtractionResult',
    'BiaozhunfangExtractionResult',
    'XianzhibExtractionResult',
    # 枚举
    'ReportType',
    # 数据类
    'LocatedValue',
    'CaseInfo',
    'SearchResult',
    'APIResponse',
    'PaginatedData',
    # 类型别名
    'JSON',
    'JSONList',
    'CaseData',
    'CaseList',
    'SearchResults',
]