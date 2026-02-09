"""
API 响应模型
============
统一的响应格式定义
"""

from typing import TypeVar, Generic, Optional, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')


# ============================================================================
# 基础响应模型
# ============================================================================

class BaseResponse(BaseModel):
    """基础响应"""
    success: bool = True
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class DataResponse(BaseResponse, Generic[T]):
    """带数据的响应"""
    data: Optional[T] = None


class ErrorResponse(BaseResponse):
    """错误响应"""
    success: bool = False
    error_code: str = ""
    detail: Optional[Any] = None


# ============================================================================
# 分页响应
# ============================================================================

class PaginationMeta(BaseModel):
    """分页元数据"""
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, total: int, page: int, page_size: int) -> 'PaginationMeta':
        return cls(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if page_size > 0 else 0,
        )


class PaginatedResponse(BaseResponse, Generic[T]):
    """分页响应"""
    data: List[T] = []
    pagination: PaginationMeta


# ============================================================================
# 特定业务响应模型
# ============================================================================

class ReportSummary(BaseModel):
    """报告摘要"""
    doc_id: str
    report_type: str
    address: Optional[str] = None
    source_file: Optional[str] = None
    case_count: int = 0
    extract_time: Optional[str] = None


class CaseSummary(BaseModel):
    """案例摘要"""
    case_id: str
    address: str
    area: Optional[float] = None
    price: Optional[float] = None
    district: Optional[str] = None
    usage: Optional[str] = None
    report_type: Optional[str] = None


class ReviewTaskSummary(BaseModel):
    """审查任务摘要"""
    task_id: str
    filename: str
    status: str
    overall_risk: Optional[str] = None
    issue_count: int = 0
    create_time: Optional[datetime] = None


class StatsOverview(BaseModel):
    """统计概览"""
    total_reports: int
    total_cases: int
    by_type: dict = {}
    vector_index: dict = {}


# ============================================================================
# 便捷函数
# ============================================================================

def success_response(
        data: Any = None,
        message: str = ""
) -> dict:
    """创建成功响应"""
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def error_response(
        message: str,
        error_code: str = "",
        detail: Any = None,
) -> dict:
    """创建错误响应"""
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "detail": detail,
    }


def paginated_response(
        items: list,
        total: int,
        page: int,
        page_size: int,
        message: str = "",
) -> dict:
    """创建分页响应"""
    return {
        "success": True,
        "message": message,
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }