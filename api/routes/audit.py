"""
审计日志接口
============

提供审计日志的查询和统计功能。
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException

from ..auth import get_current_user, require_roles, get_data_scope, DataScope
from ..iam_client import UserContext
from ..audit import AuditLogger, Action, ResourceType

router = APIRouter(prefix="/audit", tags=["审计日志"])


@router.get("/logs", summary="查询审计日志")
async def query_audit_logs(
    user_id: Optional[str] = Query(None, description="用户ID"),
    action: Optional[str] = Query(None, description="操作类型"),
    resource_type: Optional[str] = Query(None, description="资源类型"),
    resource_id: Optional[str] = Query(None, description="资源ID"),
    status: Optional[str] = Query(None, description="状态: success/failed"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: UserContext = Depends(require_roles("admin")),
    scope: DataScope = Depends(get_data_scope),
):
    """
    查询审计日志

    权限要求：admin
    数据范围：根据用户角色自动过滤
    """
    # 解析日期
    start_time = None
    end_time = None

    if start_date:
        try:
            start_time = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="开始日期格式错误，应为 YYYY-MM-DD")

    if end_date:
        try:
            end_time = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="结束日期格式错误，应为 YYYY-MM-DD")

    # 根据数据范围过滤
    org_id_filter = None
    user_id_filter = user_id

    if scope.scope_type == 'ORG':
        org_id_filter = scope.org_id
    elif scope.scope_type == 'SELF':
        user_id_filter = scope.user_id

    # 查询
    logs, total = await AuditLogger.query(
        user_id=user_id_filter,
        org_id=org_id_filter,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        keyword=keyword,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "logs": logs,
    }


@router.get("/logs/my", summary="查询我的操作日志")
async def query_my_logs(
    action: Optional[str] = Query(None, description="操作类型"),
    resource_type: Optional[str] = Query(None, description="资源类型"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: UserContext = Depends(get_current_user),
):
    """
    查询当前用户的操作日志

    权限要求：登录用户
    """
    start_time = None
    end_time = None

    if start_date:
        try:
            start_time = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="开始日期格式错误")

    if end_date:
        try:
            end_time = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="结束日期格式错误")

    logs, total = await AuditLogger.query(
        user_id=user.user_id,
        action=action,
        resource_type=resource_type,
        start_time=start_time,
        end_time=end_time,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs,
    }


@router.get("/stats", summary="审计统计")
async def get_audit_stats(
    days: int = Query(7, ge=1, le=90, description="统计最近几天"),
    user: UserContext = Depends(require_roles("admin")),
    scope: DataScope = Depends(get_data_scope),
):
    """
    获取审计统计信息

    权限要求：admin
    """
    org_id = scope.org_id if scope.scope_type == 'ORG' else None

    stats = await AuditLogger.get_stats(org_id=org_id, days=days)

    return {
        "success": True,
        "days": days,
        **stats,
    }


@router.get("/actions", summary="获取操作类型列表")
async def get_action_types(
    user: UserContext = Depends(get_current_user),
):
    """获取所有操作类型"""
    return {
        "success": True,
        "actions": [
            {"value": a.value, "label": _get_action_label(a.value)}
            for a in Action
        ],
    }


@router.get("/resource-types", summary="获取资源类型列表")
async def get_resource_types(
    user: UserContext = Depends(get_current_user),
):
    """获取所有资源类型"""
    return {
        "success": True,
        "resource_types": [
            {"value": r.value, "label": _get_resource_label(r.value)}
            for r in ResourceType
        ],
    }


@router.get("/logs/{resource_type}/{resource_id}", summary="查询资源操作历史")
async def get_resource_history(
    resource_type: str,
    resource_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserContext = Depends(get_current_user),
):
    """
    查询特定资源的操作历史

    例如：查询某个报告的所有操作记录
    """
    logs, total = await AuditLogger.query(
        resource_type=resource_type,
        resource_id=resource_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs,
    }


# ============================================================================
# 辅助函数
# ============================================================================

def _get_action_label(action: str) -> str:
    """获取操作类型的中文标签"""
    labels = {
        "create": "创建",
        "read": "查看",
        "update": "更新",
        "delete": "删除",
        "upload": "上传",
        "download": "下载",
        "export": "导出",
        "import": "导入",
        "login": "登录",
        "logout": "登出",
        "search": "搜索",
        "review": "审查",
        "approve": "审批通过",
        "reject": "审批拒绝",
    }
    return labels.get(action, action)


def _get_resource_label(resource_type: str) -> str:
    """获取资源类型的中文标签"""
    labels = {
        "report": "报告",
        "case": "案例",
        "review_task": "审查任务",
        "user": "用户",
        "system": "系统",
        "knowledge_base": "知识库",
        "vector_index": "向量索引",
    }
    return labels.get(resource_type, resource_type)
