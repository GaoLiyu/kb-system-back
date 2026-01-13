"""
操作日志模块
============

记录用户操作行为，支持审计追踪。

使用方式：
    1. 装饰器方式（推荐）
    @audit_log(action="create", resource_type="report")
    async def upload_report(...):
        pass

    2. 手动记录
    await AuditLogger.log(
        request=request,
        action="delete",
        resource_type="report",
        resource_id=doc_id,
    )

    3. 中间件方式（自动记录所有请求）
    app.add_middleware(AuditMiddleware)
"""

import json
import time
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
from enum import Enum
from dataclasses import dataclass, field, asdict

from fastapi import Request, Response
from pydantic import BaseModel


# ============================================================================
# 常量定义
# ============================================================================

class Action(str, Enum):
    """操作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    EXPORT = "export"
    IMPORT = "import"
    LOGIN = "login"
    LOGOUT = "logout"
    SEARCH = "search"
    REVIEW = "review"
    APPROVE = "approve"
    REJECT = "reject"


class ResourceType(str, Enum):
    """资源类型"""
    REPORT = "report"
    CASE = "case"
    REVIEW_TASK = "review_task"
    USER = "user"
    SYSTEM = "system"
    KNOWLEDGE_BASE = "knowledge_base"
    VECTOR_INDEX = "vector_index"


class AuditStatus(str, Enum):
    """状态"""
    SUCCESS = "success"
    FAILED = "failed"


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class AuditLogEntry:
    """审计日志条目"""
    # 用户信息
    user_id: Optional[str] = None
    username: Optional[str] = None
    org_id: Optional[str] = None
    org_name: Optional[str] = None

    # 操作信息
    action: str = ""
    resource_type: str = ""
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None

    # 请求信息
    method: Optional[str] = None
    path: Optional[str] = None
    query_params: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    # 结果信息
    status: str = AuditStatus.SUCCESS
    status_code: Optional[int] = None
    error_message: Optional[str] = None

    # 详情
    detail: Optional[Dict[str, Any]] = None

    # 时间
    created_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        if self.detail:
            data['detail'] = json.dumps(self.detail, ensure_ascii=False)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: int
    user_id: Optional[str]
    username: Optional[str]
    org_id: Optional[str]
    org_name: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    resource_name: Optional[str]
    method: Optional[str]
    path: Optional[str]
    ip_address: Optional[str]
    status: str
    status_code: Optional[int]
    error_message: Optional[str]
    detail: Optional[dict]
    created_at: datetime
    duration_ms: Optional[int]


# ============================================================================
# 审计日志管理器
# ============================================================================

class AuditLogger:
    """审计日志管理器"""

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """获取客户端IP"""
        # 优先从 X-Forwarded-For 获取（经过代理时）
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # 从 X-Real-IP 获取
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 直接获取
        if request.client:
            return request.client.host

        return "unknown"

    @staticmethod
    def _get_user_from_request(request: Request) -> tuple:
        """从请求中获取用户信息"""
        user = getattr(request.state, 'user', None)
        if user:
            return (
                getattr(user, 'user_id', None),
                getattr(user, 'username', None),
                getattr(user, 'org_id', None),
                getattr(user, 'org_name', None),
            )
        return (None, None, None, None)

    @staticmethod
    async def log(
        request: Request,
        action: str,
        resource_type: str,
        resource_id: str = None,
        resource_name: str = None,
        status: str = AuditStatus.SUCCESS,
        status_code: int = None,
        error_message: str = None,
        detail: dict = None,
        duration_ms: int = None,
    ):
        """
        记录审计日志

        Args:
            request: FastAPI 请求对象
            action: 操作类型
            resource_type: 资源类型
            resource_id: 资源ID
            resource_name: 资源名称
            status: 状态
            status_code: HTTP状态码
            error_message: 错误信息
            detail: 详细信息
            duration_ms: 耗时（毫秒）
        """
        try:
            # 获取用户信息
            user_id, username, org_id, org_name = AuditLogger._get_user_from_request(request)

            # 构建日志条目
            entry = AuditLogEntry(
                user_id=user_id,
                username=username,
                org_id=org_id,
                org_name=org_name,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                method=request.method,
                path=str(request.url.path),
                query_params=str(request.query_params) if request.query_params else None,
                ip_address=AuditLogger._get_client_ip(request),
                user_agent=request.headers.get("User-Agent", "")[:500],
                status=status,
                status_code=status_code,
                error_message=error_message,
                detail=detail,
                created_at=datetime.now(),
                duration_ms=duration_ms,
            )

            # 异步写入数据库
            await AuditLogger._save_to_db(entry)

        except Exception as e:
            # 日志记录失败不应影响主业务
            print(f"[AuditLog] 记录失败: {e}")
            traceback.print_exc()

    @staticmethod
    async def _save_to_db(entry: AuditLogEntry):
        """保存到数据库"""
        from knowledge_base.db_connection import pg_cursor

        with pg_cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_logs (
                    user_id, username, org_id, org_name,
                    action, resource_type, resource_id, resource_name,
                    method, path, query_params, ip_address, user_agent,
                    status, status_code, error_message,
                    detail, created_at, duration_ms
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                entry.user_id, entry.username, entry.org_id, entry.org_name,
                entry.action, entry.resource_type, entry.resource_id, entry.resource_name,
                entry.method, entry.path, entry.query_params, entry.ip_address, entry.user_agent,
                entry.status, entry.status_code, entry.error_message,
                json.dumps(entry.detail, ensure_ascii=False) if entry.detail else None,
                entry.created_at,
                entry.duration_ms,
            ))

    @staticmethod
    async def query(
        user_id: str = None,
        org_id: str = None,
        action: str = None,
        resource_type: str = None,
        resource_id: str = None,
        status: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        keyword: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple:
        """
        查询审计日志

        Returns:
            (logs, total)
        """
        from knowledge_base.db_connection import pg_cursor

        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)

        if org_id:
            conditions.append("org_id = %s")
            params.append(org_id)

        if action:
            conditions.append("action = %s")
            params.append(action)

        if resource_type:
            conditions.append("resource_type = %s")
            params.append(resource_type)

        if resource_id:
            conditions.append("resource_id = %s")
            params.append(resource_id)

        if status:
            conditions.append("status = %s")
            params.append(status)

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at <= %s")
            params.append(end_time)

        if keyword:
            conditions.append("(resource_name ILIKE %s OR path ILIKE %s OR error_message ILIKE %s)")
            keyword_param = f"%{keyword}%"
            params.extend([keyword_param, keyword_param, keyword_param])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with pg_cursor(commit=False) as cursor:
            # 查询总数
            cursor.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {where_clause}", params)
            total = cursor.fetchone()[0]

            # 查询数据
            cursor.execute(f"""
                SELECT id, user_id, username, org_id, org_name,
                       action, resource_type, resource_id, resource_name,
                       method, path, ip_address, status, status_code, error_message,
                       detail, created_at, duration_ms
                FROM audit_logs 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])

            logs = []
            for row in cursor.fetchall():
                logs.append({
                    "id": row[0],
                    "user_id": row[1],
                    "username": row[2],
                    "org_id": row[3],
                    "org_name": row[4],
                    "action": row[5],
                    "resource_type": row[6],
                    "resource_id": row[7],
                    "resource_name": row[8],
                    "method": row[9],
                    "path": row[10],
                    "ip_address": row[11],
                    "status": row[12],
                    "status_code": row[13],
                    "error_message": row[14],
                    "detail": row[15],
                    "created_at": row[16].isoformat() if row[16] else None,
                    "duration_ms": row[17],
                })

            return logs, total

    @staticmethod
    async def get_stats(
        org_id: str = None,
        days: int = 7,
    ) -> dict:
        """
        获取统计信息

        Args:
            org_id: 组织ID（可选）
            days: 统计最近几天

        Returns:
            统计数据
        """
        from knowledge_base.db_connection import pg_cursor

        org_condition = "AND org_id = %s" if org_id else ""
        params = [days]
        if org_id:
            params.append(org_id)

        with pg_cursor(commit=False) as cursor:
            # 按操作类型统计
            cursor.execute(f"""
                SELECT action, COUNT(*) 
                FROM audit_logs 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                {org_condition}
                GROUP BY action
                ORDER BY COUNT(*) DESC
            """, params)
            by_action = {row[0]: row[1] for row in cursor.fetchall()}

            # 按资源类型统计
            cursor.execute(f"""
                SELECT resource_type, COUNT(*) 
                FROM audit_logs 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                {org_condition}
                GROUP BY resource_type
                ORDER BY COUNT(*) DESC
            """, params)
            by_resource = {row[0]: row[1] for row in cursor.fetchall()}

            # 按状态统计
            cursor.execute(f"""
                SELECT status, COUNT(*) 
                FROM audit_logs 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                {org_condition}
                GROUP BY status
            """, params)
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            # 按日期统计
            cursor.execute(f"""
                SELECT DATE(created_at) as date, COUNT(*) 
                FROM audit_logs 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                {org_condition}
                GROUP BY DATE(created_at)
                ORDER BY date
            """, params)
            by_date = {str(row[0]): row[1] for row in cursor.fetchall()}

            # 活跃用户
            cursor.execute(f"""
                SELECT user_id, username, COUNT(*) 
                FROM audit_logs 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND user_id IS NOT NULL
                {org_condition}
                GROUP BY user_id, username
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """, params)
            top_users = [
                {"user_id": row[0], "username": row[1], "count": row[2]}
                for row in cursor.fetchall()
            ]

            return {
                "by_action": by_action,
                "by_resource": by_resource,
                "by_status": by_status,
                "by_date": by_date,
                "top_users": top_users,
                "total": sum(by_status.values()),
            }


# ============================================================================
# 装饰器
# ============================================================================

def audit_log(
    action: str,
    resource_type: str,
    resource_id_param: str = None,
    resource_name_param: str = None,
    detail_params: List[str] = None,
):
    """
    审计日志装饰器

    Args:
        action: 操作类型
        resource_type: 资源类型
        resource_id_param: 从函数参数中获取资源ID的参数名
        resource_name_param: 从函数参数中获取资源名称的参数名
        detail_params: 需要记录到detail的参数名列表

    Usage:
        @router.post("/upload")
        @audit_log(action="upload", resource_type="report", resource_name_param="file.filename")
        async def upload_report(file: UploadFile, user: UserContext = Depends(get_current_user)):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取 request 对象
            request = kwargs.get('request')
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # 记录开始时间
            start_time = time.time()

            # 提取资源ID
            resource_id = None
            if resource_id_param:
                resource_id = kwargs.get(resource_id_param)

            # 提取资源名称
            resource_name = None
            if resource_name_param:
                # 支持嵌套属性，如 "file.filename"
                parts = resource_name_param.split(".")
                obj = kwargs.get(parts[0])
                for part in parts[1:]:
                    if obj:
                        obj = getattr(obj, part, None)
                resource_name = str(obj) if obj else None

            # 提取详情参数
            detail = {}
            if detail_params:
                for param in detail_params:
                    if param in kwargs:
                        value = kwargs[param]
                        # 简单类型直接存储
                        if isinstance(value, (str, int, float, bool, type(None))):
                            detail[param] = value
                        else:
                            detail[param] = str(value)

            try:
                # 执行原函数
                result = await func(*args, **kwargs)

                # 计算耗时
                duration_ms = int((time.time() - start_time) * 1000)

                # 记录成功日志
                if request:
                    await AuditLogger.log(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        resource_id=str(resource_id) if resource_id else None,
                        resource_name=resource_name,
                        status=AuditStatus.SUCCESS,
                        status_code=200,
                        detail=detail if detail else None,
                        duration_ms=duration_ms,
                    )

                return result

            except Exception as e:
                # 计算耗时
                duration_ms = int((time.time() - start_time) * 1000)

                # 记录失败日志
                if request:
                    await AuditLogger.log(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        resource_id=str(resource_id) if resource_id else None,
                        resource_name=resource_name,
                        status=AuditStatus.FAILED,
                        status_code=500,
                        error_message=str(e),
                        detail=detail if detail else None,
                        duration_ms=duration_ms,
                    )

                # 继续抛出异常
                raise

        return wrapper
    return decorator


# ============================================================================
# 中间件（可选，记录所有请求）
# ============================================================================

class AuditMiddleware:
    """
    审计日志中间件

    自动记录所有请求，适合需要完整审计的场景。
    注意：会产生大量日志，建议配合过滤规则使用。

    Usage:
        from api.audit import AuditMiddleware
        app.add_middleware(AuditMiddleware, exclude_paths=["/health", "/docs"])
    """

    def __init__(
        self,
        app,
        exclude_paths: List[str] = None,
        exclude_methods: List[str] = None,
    ):
        self.app = app
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/redoc", "/openapi.json"]
        self.exclude_methods = exclude_methods or ["OPTIONS"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # 检查是否需要排除
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        if request.method in self.exclude_methods:
            await self.app(scope, receive, send)
            return

        # 记录开始时间
        start_time = time.time()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 计算耗时
            duration_ms = int((time.time() - start_time) * 1000)

            # 推断操作类型和资源类型
            action, resource_type = self._infer_action_and_resource(request)

            # 记录日志
            try:
                await AuditLogger.log(
                    request=request,
                    action=action,
                    resource_type=resource_type,
                    status=AuditStatus.SUCCESS if status_code < 400 else AuditStatus.FAILED,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                print(f"[AuditMiddleware] 记录失败: {e}")

    def _infer_action_and_resource(self, request: Request) -> tuple:
        """从请求推断操作类型和资源类型"""
        method = request.method
        path = request.url.path

        # 推断操作类型
        action_map = {
            "GET": Action.READ,
            "POST": Action.CREATE,
            "PUT": Action.UPDATE,
            "PATCH": Action.UPDATE,
            "DELETE": Action.DELETE,
        }
        action = action_map.get(method, Action.READ)

        # 推断资源类型
        resource_type = ResourceType.SYSTEM
        if "/kb/" in path or "/report" in path:
            resource_type = ResourceType.REPORT
        elif "/case" in path:
            resource_type = ResourceType.CASE
        elif "/review" in path:
            resource_type = ResourceType.REVIEW_TASK
        elif "/user" in path:
            resource_type = ResourceType.USER

        # 特殊操作
        if "upload" in path:
            action = Action.UPLOAD
        elif "download" in path or "export" in path:
            action = Action.EXPORT
        elif "search" in path:
            action = Action.SEARCH

        return action, resource_type


# ============================================================================
# 便捷函数
# ============================================================================

async def log_action(
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str = None,
    resource_name: str = None,
    detail: dict = None,
):
    """便捷记录函数"""
    await AuditLogger.log(
        request=request,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        detail=detail,
    )
