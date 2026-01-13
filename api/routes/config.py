"""
系统配置接口
============

提供系统配置信息，供前端初始化使用。
"""

from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..config import settings
from ..auth import get_current_user, get_optional_user, require_roles
from ..iam_client import UserContext

router = APIRouter(prefix="/config", tags=["系统配置"])


# ============================================================================
# 响应模型
# ============================================================================

class AuthConfig(BaseModel):
    """认证配置"""
    iam_enabled: bool
    iam_login_url: Optional[str] = None
    iam_logout_url: Optional[str] = None
    iam_app_code: Optional[str] = None


class FeatureConfig(BaseModel):
    """功能开关配置"""
    enable_llm: bool
    enable_vector: bool
    enable_audit_log: bool = True
    enable_batch_upload: bool = True
    enable_export: bool = True
    max_upload_size_mb: int = 50
    allowed_extensions: list[str]


class SystemInfo(BaseModel):
    """系统信息"""
    name: str
    version: str
    description: str


class SystemConfigResponse(BaseModel):
    """系统配置响应"""
    success: bool = True
    system: SystemInfo
    auth: AuthConfig
    features: FeatureConfig


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    success: bool = True
    logged_in: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    org_id: Optional[str] = None
    org_name: Optional[str] = None
    roles: list[str] = []
    permissions: list[str] = []


# ============================================================================
# 接口
# ============================================================================

@router.get("", summary="获取系统配置", response_model=SystemConfigResponse)
async def get_system_config():
    """
    获取系统配置（无需登录）

    前端启动时调用，用于：
    - 判断是否启用 IAM 登录
    - 获取功能开关状态
    - 显示系统信息
    """
    # 构建 IAM 登录 URL
    iam_login_url = None
    iam_logout_url = None

    if settings.iam_enabled:
        iam_base = settings.iam_base_url.rstrip('/')
        app_code = settings.iam_app_code
        # 假设 IAM 的登录页面格式
        iam_login_url = f"{iam_base}/login?app_code={app_code}"
        iam_logout_url = f"{iam_base}/logout?app_code={app_code}"

    return SystemConfigResponse(
        system=SystemInfo(
            name="房地产估价知识库系统",
            version="3.0.0",
            description="基于比较法的房地产估价报告知识库系统",
        ),
        auth=AuthConfig(
            iam_enabled=settings.iam_enabled,
            iam_login_url=iam_login_url,
            iam_logout_url=iam_logout_url,
            iam_app_code=settings.iam_app_code if settings.iam_enabled else None,
        ),
        features=FeatureConfig(
            enable_llm=settings.enable_llm,
            enable_vector=settings.enable_vector,
            enable_audit_log=True,
            enable_batch_upload=True,
            enable_export=True,
            max_upload_size_mb=50,
            allowed_extensions=list(settings.allowed_extensions),
        ),
    )


@router.get("/user", summary="获取当前用户信息", response_model=UserInfoResponse)
async def get_current_user_info(
    request: Request,
    user: Optional[UserContext] = Depends(get_optional_user),
):
    """
    获取当前登录用户信息

    返回：
    - 用户基本信息
    - 角色列表
    - 权限列表
    """
    if not user:
        return UserInfoResponse(logged_in=False)

    # 根据角色生成权限列表
    permissions = _get_permissions_by_roles(user.roles)

    return UserInfoResponse(
        logged_in=True,
        user_id=user.user_id,
        username=user.username,
        org_id=user.org_id,
        org_name=user.org_name,
        roles=user.roles,
        permissions=permissions,
    )


@router.get("/permissions", summary="获取权限定义")
async def get_permission_definitions(
    user: UserContext = Depends(get_current_user),
):
    """
    获取系统权限定义

    返回所有权限及其说明，供前端权限管理使用
    """
    return {
        "success": True,
        "permissions": PERMISSION_DEFINITIONS,
        "roles": ROLE_DEFINITIONS,
    }


@router.get("/menus", summary="获取用户菜单")
async def get_user_menus(
    user: UserContext = Depends(get_current_user),
):
    """
    获取当前用户可访问的菜单

    根据用户角色过滤菜单项
    """
    permissions = set(_get_permissions_by_roles(user.roles))

    # 过滤菜单
    filtered_menus = []
    for menu in MENU_CONFIG:
        # 检查菜单权限
        if menu.get("permission") and menu["permission"] not in permissions:
            continue

        # 处理子菜单
        if menu.get("children"):
            children = [
                child for child in menu["children"]
                if not child.get("permission") or child["permission"] in permissions
            ]
            if children:
                menu_copy = {**menu, "children": children}
                filtered_menus.append(menu_copy)
        else:
            filtered_menus.append(menu)

    return {
        "success": True,
        "menus": filtered_menus,
    }


# ============================================================================
# 权限定义
# ============================================================================

# 权限定义
PERMISSION_DEFINITIONS = {
    # 知识库
    "kb:view": {"name": "查看知识库", "description": "查看报告和案例列表"},
    "kb:upload": {"name": "上传报告", "description": "上传新报告到知识库"},
    "kb:delete": {"name": "删除报告", "description": "从知识库删除报告"},
    "kb:rebuild": {"name": "重建索引", "description": "重建向量索引"},

    # 搜索
    "search:case": {"name": "搜索案例", "description": "搜索知识库案例"},

    # 审查
    "review:submit": {"name": "提交审查", "description": "提交报告审查任务"},
    "review:view": {"name": "查看任务", "description": "查看审查任务列表"},
    "review:delete": {"name": "删除任务", "description": "删除审查任务"},
    "review:export": {"name": "导出结果", "description": "导出审查结果"},

    # 生成
    "generate:suggest": {"name": "推荐案例", "description": "获取推荐可比实例"},

    # 统计
    "stats:view": {"name": "查看统计", "description": "查看系统统计信息"},

    # 系统
    "system:audit": {"name": "审计日志", "description": "查看操作日志"},
    "system:config": {"name": "系统配置", "description": "管理系统配置"},
    "system:user": {"name": "用户管理", "description": "管理系统用户"},
}

# 角色定义
ROLE_DEFINITIONS = {
    "super_admin": {
        "name": "超级管理员",
        "description": "拥有所有权限",
        "permissions": list(PERMISSION_DEFINITIONS.keys()),
    },
    "admin": {
        "name": "管理员",
        "description": "组织管理员，可管理本组织数据",
        "permissions": [
            "kb:view", "kb:upload", "kb:delete", "kb:rebuild",
            "search:case",
            "review:submit", "review:view", "review:delete", "review:export",
            "generate:suggest",
            "stats:view",
            "system:audit",
        ],
    },
    "reviewer": {
        "name": "审查员",
        "description": "可以提交和查看审查任务",
        "permissions": [
            "kb:view",
            "search:case",
            "review:submit", "review:view", "review:export",
            "generate:suggest",
            "stats:view",
        ],
    },
    "editor": {
        "name": "编辑员",
        "description": "可以上传和编辑报告",
        "permissions": [
            "kb:view", "kb:upload",
            "search:case",
            "review:view",
            "generate:suggest",
            "stats:view",
        ],
    },
    "viewer": {
        "name": "只读用户",
        "description": "只能查看数据",
        "permissions": [
            "kb:view",
            "search:case",
            "review:view",
            "stats:view",
        ],
    },
}

# 菜单配置
MENU_CONFIG = [
    {
        "path": "/dashboard",
        "name": "Dashboard",
        "title": "首页",
        "icon": "HomeFilled",
    },
    {
        "path": "/kb",
        "name": "KnowledgeBase",
        "title": "知识库",
        "icon": "Folder",
        "children": [
            {
                "path": "/kb/reports",
                "name": "Reports",
                "title": "报告管理",
                "permission": "kb:view",
            },
            {
                "path": "/kb/cases",
                "name": "Cases",
                "title": "案例搜索",
                "permission": "search:case",
            },
        ],
    },
    {
        "path": "/review",
        "name": "Review",
        "title": "报告审查",
        "icon": "DocumentChecked",
        "children": [
            {
                "path": "/review/tasks",
                "name": "ReviewTasks",
                "title": "审查任务",
                "permission": "review:view",
            },
            {
                "path": "/review/instant",
                "name": "InstantReview",
                "title": "即时审查",
                "permission": "review:submit",
            },
        ],
    },
    {
        "path": "/generate",
        "name": "Generate",
        "title": "报告生成",
        "icon": "EditPen",
        "permission": "generate:suggest",
    },
    {
        "path": "/stats",
        "name": "Stats",
        "title": "统计分析",
        "icon": "DataAnalysis",
        "permission": "stats:view",
    },
    {
        "path": "/system",
        "name": "System",
        "title": "系统管理",
        "icon": "Setting",
        "permission": "system:audit",
        "children": [
            {
                "path": "/system/audit",
                "name": "AuditLogs",
                "title": "操作日志",
                "permission": "system:audit",
            },
        ],
    },
]


def _get_permissions_by_roles(roles: list[str]) -> list[str]:
    """根据角色获取权限列表"""
    permissions = set()

    for role in roles:
        role_def = ROLE_DEFINITIONS.get(role)
        if role_def:
            permissions.update(role_def["permissions"])

    return list(permissions)
