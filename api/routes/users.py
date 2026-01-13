"""
用户管理接口
============

提供用户的增删改查、登录登出等功能
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field

from ..auth import (
    get_current_user,
    require_roles,
    authenticate_user,
    create_user_token,
    revoke_user_token,
    revoke_all_user_tokens,
)
from ..iam_client import UserContext
from ..models.user import User, UserRepository, OrganizationRepository


router = APIRouter(prefix="/users", tags=["用户管理"])


# ============================================================================
# 请求/响应模型
# ============================================================================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    message: str = ""


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    real_name: str = Field("", description="真实姓名")
    email: str = Field("", description="邮箱")
    phone: str = Field("", description="手机号")
    org_id: Optional[int] = Field(None, description="组织ID")
    roles: List[str] = Field(default=["viewer"], description="角色列表")


class UpdateUserRequest(BaseModel):
    """更新用户请求"""
    real_name: Optional[str] = Field(None, description="真实姓名")
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")
    org_id: Optional[int] = Field(None, description="组织ID")
    status: Optional[str] = Field(None, description="状态")


class UpdateRolesRequest(BaseModel):
    """更新角色请求"""
    roles: List[str] = Field(..., description="角色列表")


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, description="新密码")


class ResetPasswordRequest(BaseModel):
    """重置密码请求（管理员）"""
    new_password: str = Field(..., min_length=6, description="新密码")


# ============================================================================
# 辅助函数
# ============================================================================

def user_to_response(user: User) -> dict:
    """将User转换为响应格式"""
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "email": user.email,
        "phone": user.phone,
        "org_id": user.org_id,
        "org_name": user.org_name,
        "status": user.status,
        "roles": user.roles,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def get_client_ip(request: Request) -> str:
    """获取客户端IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return request.client.host if request.client else ""


# ============================================================================
# 登录登出
# ============================================================================

@router.post("/login", summary="用户登录", response_model=LoginResponse)
async def login(request: Request, req: LoginRequest):
    """
    用户登录

    验证用户名密码，返回访问Token
    """
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    user, error = authenticate_user(req.username, req.password, ip_address)

    if not user:
        return LoginResponse(success=False, message=error)

    # 创建Token
    token = create_user_token(user, ip_address, user_agent[:200])

    return LoginResponse(
        success=True,
        token=token,
        user=user_to_response(user),
        message="登录成功",
    )


@router.post("/logout", summary="退出登录")
async def logout(
    request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """
    退出登录

    撤销当前Token
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        revoke_user_token(token)

    return {"success": True, "message": "已退出登录"}


@router.post("/logout-all", summary="退出所有设备")
async def logout_all(current_user: UserContext = Depends(get_current_user)):
    """
    退出所有设备

    撤销该用户的所有Token
    """
    try:
        user_id = int(current_user.user_id)
        count = revoke_all_user_tokens(user_id)
        return {"success": True, "message": f"已退出 {count} 个设备"}
    except (ValueError, TypeError):
        return {"success": True, "message": "已退出登录"}


# ============================================================================
# 用户信息
# ============================================================================

@router.get("/me", summary="获取当前用户信息")
async def get_me(current_user: UserContext = Depends(get_current_user)):
    """
    获取当前登录用户信息
    """
    # 如果是数据库用户，获取完整信息
    try:
        user_id = int(current_user.user_id)
        user = UserRepository.get_by_id(user_id)
        if user:
            return {"success": True, "user": user_to_response(user)}
    except (ValueError, TypeError):
        pass

    # 返回UserContext信息
    return {
        "success": True,
        "user": {
            "id": current_user.user_id,
            "username": current_user.username,
            "real_name": current_user.username,
            "org_id": current_user.org_id,
            "org_name": current_user.org_name,
            "roles": current_user.roles,
        },
    }


@router.put("/me", summary="更新个人信息")
async def update_me(
    req: UpdateUserRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """
    更新当前用户个人信息

    只能修改：真实姓名、邮箱、手机号
    """
    try:
        user_id = int(current_user.user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无法修改非本地用户")

    user = UserRepository.update(
        user_id,
        real_name=req.real_name,
        email=req.email,
        phone=req.phone,
        # 不允许自己修改org_id和status
    )

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {"success": True, "user": user_to_response(user)}


@router.post("/me/change-password", summary="修改密码")
async def change_password(
    req: ChangePasswordRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """
    修改当前用户密码
    """
    try:
        user_id = int(current_user.user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="无法修改非本地用户密码")

    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 验证旧密码
    from ..models.user import verify_password
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")

    # 更新密码
    UserRepository.update_password(user_id, req.new_password)

    # 撤销所有Token，强制重新登录
    revoke_all_user_tokens(user_id)

    return {"success": True, "message": "密码修改成功，请重新登录"}


# ============================================================================
# 用户管理（管理员）
# ============================================================================

@router.get("", summary="用户列表")
async def list_users(
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    获取用户列表（管理员）
    """
    users, total = UserRepository.list_users(
        org_id=org_id,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": [user_to_response(u) for u in users],
    }


@router.get("/{user_id}", summary="用户详情")
async def get_user(
    user_id: int,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    获取用户详情（管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {"success": True, "user": user_to_response(user)}


@router.post("", summary="创建用户")
async def create_user(
    req: CreateUserRequest,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    创建用户（管理员）
    """
    # 检查用户名是否存在
    if UserRepository.check_username_exists(req.username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 验证角色
    valid_roles = {"super_admin", "admin", "reviewer", "editor", "viewer"}
    for role in req.roles:
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"无效的角色: {role}")

    # 只有超级管理员可以创建超级管理员
    if "super_admin" in req.roles and "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="只有超级管理员可以创建超级管理员")

    try:
        created_by = int(current_user.user_id)
    except (ValueError, TypeError):
        created_by = None

    user = UserRepository.create(
        username=req.username,
        password=req.password,
        real_name=req.real_name,
        email=req.email,
        phone=req.phone,
        org_id=req.org_id,
        roles=req.roles,
        created_by=created_by,
    )

    return {"success": True, "user": user_to_response(user)}


@router.put("/{user_id}", summary="更新用户")
async def update_user(
    user_id: int,
    req: UpdateUserRequest,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    更新用户信息（管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能修改超级管理员（除非自己是超级管理员）
    if "super_admin" in user.roles and "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="无权修改超级管理员")

    user = UserRepository.update(
        user_id,
        real_name=req.real_name,
        email=req.email,
        phone=req.phone,
        org_id=req.org_id,
        status=req.status,
    )

    return {"success": True, "user": user_to_response(user)}


@router.put("/{user_id}/roles", summary="更新用户角色")
async def update_user_roles(
    user_id: int,
    req: UpdateRolesRequest,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    更新用户角色（管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能修改超级管理员的角色（除非自己是超级管理员）
    if "super_admin" in user.roles and "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="无权修改超级管理员角色")

    # 验证角色
    valid_roles = {"super_admin", "admin", "reviewer", "editor", "viewer"}
    for role in req.roles:
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"无效的角色: {role}")

    # 只有超级管理员可以分配超级管理员角色
    if "super_admin" in req.roles and "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="只有超级管理员可以分配超级管理员角色")

    UserRepository.update_roles(user_id, req.roles)

    user = UserRepository.get_by_id(user_id)
    return {"success": True, "user": user_to_response(user)}


@router.post("/{user_id}/reset-password", summary="重置密码")
async def reset_password(
    user_id: int,
    req: ResetPasswordRequest,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    重置用户密码（管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能重置超级管理员密码（除非自己是超级管理员）
    if "super_admin" in user.roles and "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="无权重置超级管理员密码")

    UserRepository.update_password(user_id, req.new_password)

    # 撤销该用户的所有Token
    revoke_all_user_tokens(user_id)

    return {"success": True, "message": "密码已重置"}


@router.delete("/{user_id}", summary="删除用户")
async def delete_user(
    user_id: int,
    current_user: UserContext = Depends(require_roles("super_admin")),
):
    """
    删除用户（仅超级管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不能删除自己
    if str(user_id) == current_user.user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    # 不能删除超级管理员
    if "super_admin" in user.roles:
        raise HTTPException(status_code=403, detail="不能删除超级管理员")

    UserRepository.delete(user_id)

    return {"success": True, "message": "用户已删除"}


@router.post("/{user_id}/unlock", summary="解锁用户")
async def unlock_user(
    user_id: int,
    current_user: UserContext = Depends(require_roles("admin")),
):
    """
    解锁被锁定的用户（管理员）
    """
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.status != 'locked':
        raise HTTPException(status_code=400, detail="用户未被锁定")

    UserRepository.update(user_id, status='active')

    # 重置登录失败计数
    from knowledge_base.db_connection import pg_cursor
    with pg_cursor(commit=True) as cursor:
        cursor.execute("UPDATE users SET login_fail_count = 0 WHERE id = %s", (user_id,))

    return {"success": True, "message": "用户已解锁"}


# ============================================================================
# 组织管理
# ============================================================================

@router.get("/orgs/list", summary="组织列表")
async def list_organizations(
    current_user: UserContext = Depends(get_current_user),
):
    """
    获取组织列表
    """
    orgs = OrganizationRepository.list_all(status='active')

    return {
        "success": True,
        "organizations": [
            {
                "id": org.id,
                "org_code": org.org_code,
                "org_name": org.org_name,
                "parent_id": org.parent_id,
                "level": org.level,
            }
            for org in orgs
        ],
    }


# ============================================================================
# 角色定义
# ============================================================================

@router.get("/roles/list", summary="角色列表")
async def list_roles(
    current_user: UserContext = Depends(get_current_user),
):
    """
    获取角色列表
    """
    from ..routes.config import ROLE_DEFINITIONS

    roles = []
    for code, info in ROLE_DEFINITIONS.items():
        roles.append({
            "code": code,
            "name": info["name"],
            "description": info["description"],
        })

    return {"success": True, "roles": roles}
