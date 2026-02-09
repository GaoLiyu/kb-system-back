"""
自定义异常和异常处理器
"""

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from .schemas import error_response


# ============================================================================
# 自定义异常
# ============================================================================

class KBException(Exception):
    """知识库基础异常"""
    def __init__(self, message: str, error_code: str = "KB_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class ExtractionError(KBException):
    """提取错误"""
    def __init__(self, message: str):
        super().__init__(message, "EXTRACTION_ERROR")


class ValidationError(KBException):
    """校验错误"""
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class NotFoundError(KBException):
    """资源不存在"""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} 不存在: {resource_id}", "NOT_FOUND")


# ============================================================================
# 异常处理器
# ============================================================================

async def kb_exception_handler(request: Request, exc: KBException):
    """处理知识库异常"""
    return JSONResponse(
        status_code=400,
        content=error_response(
            message=exc.message,
            error_code=exc.error_code,
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """处理 HTTP 异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.detail,
            error_code=f"HTTP_{exc.status_code}",
        ),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """处理未知异常"""
    # 生产环境不返回详细错误信息
    return JSONResponse(
        status_code=500,
        content=error_response(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
        ),
    )


def register_exception_handlers(app):
    """注册异常处理器"""
    app.add_exception_handler(KBException, kb_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    # 生产环境可以启用通用异常处理
    # app.add_exception_handler(Exception, general_exception_handler)