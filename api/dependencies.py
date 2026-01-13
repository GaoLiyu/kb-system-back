"""
FastAPI 依赖注入
===============

提供便捷的依赖注入工具，简化路由中的认证授权使用。

使用示例：
    from api.dependencies import CurrentUser, RequireRoles, OrgScoped

    # 方式1: 使用类依赖
    @router.get("/cases")
    async def list_cases(user: UserContext = Depends(CurrentUser())):
        pass

    # 方式2: 使用预定义依赖
    @router.delete("/report/{id}")
    async def delete_report(user: UserContext = Depends(require_admin)):
        pass
"""

from fastapi import Depends, Request, HTTPException
from typing import Optional

from .auth import (
    get_current_user,
    get_optional_user,
    get_data_scope,
    require_roles,
    require_org_access,
    require_permission,
    DataScope,
    # 预定义角色依赖
    require_admin,
    require_reviewer,
    require_editor,
    require_viewer,
)
from .iam_client import UserContext


# ============================================================================
# 类式依赖（更灵活）
# ============================================================================

class CurrentUser:
    """
    当前用户依赖

    Args:
        required: 是否必须登录，默认 True

    Usage:
        # 必须登录
        user: UserContext = Depends(CurrentUser())

        # 可选登录
        user: Optional[UserContext] = Depends(CurrentUser(required=False))
    """

    def __init__(self, required: bool = True):
        self.required = required

    async def __call__(self, request: Request) -> Optional[UserContext]:
        if self.required:
            return await get_current_user(request, None)
        else:
            return await get_optional_user(request, None)


class RequireRoles:
    """
    角色要求依赖

    Usage:
        user: UserContext = Depends(RequireRoles("admin", "reviewer"))
    """

    def __init__(self, *roles: str):
        self.roles = roles
        self._checker = require_roles(*roles)

    async def __call__(self, request: Request) -> UserContext:
        # 从请求头中提取 credentials
        from fastapi.security import HTTPAuthorizationCredentials

        auth_header = request.headers.get("Authorization", "")
        credentials = None
        if auth_header.startswith("Bearer "):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=auth_header[7:]
            )

        return await self._checker(request, credentials)


class OrgScoped:
    """
    组织范围数据依赖

    Usage:
        scope: DataScope = Depends(OrgScoped())
    """

    async def __call__(self, request: Request) -> DataScope:
        return await get_data_scope(request, None)


class RequireOrgAccess:
    """
    组织访问权限依赖

    Usage:
        @router.get("/org/{org_id}/data")
        async def get_org_data(
            org_id: str,
            user: UserContext = Depends(RequireOrgAccess("org_id"))
        ):
            pass
    """

    def __init__(self, org_id_param: str = 'org_id'):
        self.org_id_param = org_id_param
        self._checker = require_org_access(org_id_param)

    async def __call__(self, request: Request) -> UserContext:
        return await self._checker(request, None)


class RequirePermission:
    """
    细粒度权限依赖

    Usage:
        user: UserContext = Depends(RequirePermission("kb:report", "delete"))
    """

    def __init__(self, resource: str, action: str = None):
        self.resource = resource
        self.action = action
        self._checker = require_permission(resource, action)

    async def __call__(self, request: Request) -> UserContext:
        return await self._checker(request, None)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 用户上下文
    'UserContext',
    'DataScope',

    # 类式依赖
    'CurrentUser',
    'RequireRoles',
    'OrgScoped',
    'RequireOrgAccess',
    'RequirePermission',

    # 函数式依赖
    'get_current_user',
    'get_optional_user',
    'get_data_scope',
    'require_roles',
    'require_org_access',
    'require_permission',

    # 预定义角色依赖
    'require_admin',
    'require_reviewer',
    'require_editor',
    'require_viewer',
]