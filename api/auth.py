"""
认证授权模块 - 支持 IAM JWT 和简单 Token 两种模式
=================================================

功能：
1. 认证（Authentication）- 验证用户身份
2. 授权（Authorization）- 基于角色的访问控制 (RBAC)
3. 数据隔离（Data Scope）- 基于组织的数据权限

使用示例：
    # 仅认证
    @router.get("/cases")
    async def list_cases(user: UserContext = Depends(get_current_user)):
        pass

    # 角色控制
    @router.delete("/report/{id}")
    async def delete_report(user: UserContext = Depends(require_roles("admin"))):
        pass

    # 数据隔离
    @router.get("/org/reports")
    async def list_org_reports(scope: DataScope = Depends(get_data_scope)):
        # scope.org_id 用于过滤数据
        pass
"""
import secrets
import hashlib
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List, Set, Tuple
from pydantic import BaseModel
from datetime import datetime, timedelta

from .config import settings
from .models.user import User, UserRepository, verify_password
from .iam_client import iam_client, UserContext


# ============================================================================
# 安全配置
# ============================================================================

security = HTTPBearer(auto_error=False)


# ============================================================================
# 数据范围模型
# ============================================================================

class DataScope(BaseModel):
    """数据访问范围"""
    scope_type: str  # ALL, ORG, SELF
    org_id: Optional[str] = None
    org_ids: Optional[List[str]] = None  # 可访问的组织列表
    user_id: Optional[str] = None

    def can_access_org(self, target_org_id: str) -> bool:
        """检查是否可以访问指定组织的数据"""
        if self.scope_type == 'ALL':
            return True
        if self.scope_type == 'ORG':
            if self.org_ids:
                return target_org_id in self.org_ids
            return target_org_id == self.org_id
        return False

    def can_access_user(self, target_user_id: str) -> bool:
        """检查是否可以访问指定用户的数据"""
        if self.scope_type in ('ALL', 'ORG'):
            return True
        return target_user_id == self.user_id

    def get_filter_condition(self) -> dict:
        """获取数据库查询过滤条件"""
        if self.scope_type == 'ALL':
            return {}
        elif self.scope_type == 'ORG':
            if self.org_ids:
                return {'org_id__in': self.org_ids}
            return {'org_id': self.org_id}
        else:  # SELF
            return {'user_id': self.user_id}


# ============================================================================
# 核心认证函数
# ============================================================================

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserContext:
    """
    获取当前用户（核心认证函数）

    - IAM 模式：验证 JWT，返回真实用户上下文
    - 简单模式：验证 Token，返回模拟用户

    Returns:
        UserContext: 用户上下文，包含 user_id, org_id, roles 等

    Raises:
        HTTPException 401: Token 无效或未提供
    """
    # 获取 Token
    token = None
    if credentials:
        token = credentials.credentials

    # 也支持从 query 参数获取（用于跳转场景）
    if not token:
        token = request.query_params.get('token')

    if not token:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    # 1. 尝试用户Token验证（本地用户）
    user = verify_user_token(token)
    if user:
        context = user_to_context(user)
        request.state.user = context
        request.state.token = token
        return context

    # 2. IAM 模式
    if settings.iam_enabled:
        try:
            user = iam_client.verify_token(token)
            request.state.user = user
            request.state.token = token
            return user
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))

    # 简单 Token 模式
    else:
        if token != settings.api_token:
            raise HTTPException(status_code=401, detail="无效的Token")

        # 返回模拟用户（简单模式下默认是超级管理员）
        user = UserContext(
            user_id='default_user',
            org_id='default',
            roles=['admin'],
        )
        request.state.user = user
        request.state.token = token
        return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[UserContext]:
    """
    可选认证（不强制要求登录）

    用于某些接口允许匿名访问但登录后有更多权限的场景
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


# ============================================================================
# 角色检查
# ============================================================================

# 角色层级定义（高级角色包含低级角色的权限）
ROLE_HIERARCHY = {
    'super_admin': {'super_admin', 'admin', 'reviewer', 'editor', 'viewer'},
    'admin': {'admin', 'reviewer', 'editor', 'viewer'},
    'reviewer': {'reviewer', 'viewer'},
    'editor': {'editor', 'viewer'},
    'viewer': {'viewer'},
}


def get_effective_roles(roles: List[str]) -> Set[str]:
    """获取有效角色（包含继承的角色）"""
    effective = set()
    for role in roles:
        effective.update(ROLE_HIERARCHY.get(role, {role}))
    return effective


def require_roles(*allowed_roles: str):
    """
    角色检查依赖工厂

    Args:
        allowed_roles: 允许的角色列表，满足其一即可

    Usage:
        @router.delete("/report/{id}")
        async def delete_report(user: UserContext = Depends(require_roles("admin"))):
            pass

        @router.post("/review")
        async def submit_review(user: UserContext = Depends(require_roles("admin", "reviewer"))):
            pass
    """
    async def role_checker(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> UserContext:
        user = await get_current_user(request, credentials)

        # 获取用户的有效角色
        effective_roles = get_effective_roles(user.roles)

        # 检查是否有允许的角色
        if not any(role in effective_roles for role in allowed_roles):
            raise HTTPException(
                status_code=403,
                detail=f"权限不足，需要以下角色之一: {', '.join(allowed_roles)}"
            )

        return user

    return role_checker


# ============================================================================
# 组织数据隔离
# ============================================================================

async def get_data_scope(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> DataScope:
    """
    获取数据访问范围

    根据用户角色和组织确定可访问的数据范围：
    - super_admin: 全部数据
    - admin: 本组织及下级组织数据
    - 其他: 仅本组织数据或仅自己的数据

    Usage:
        @router.get("/reports")
        async def list_reports(scope: DataScope = Depends(get_data_scope)):
            if scope.scope_type == 'ALL':
                return get_all_reports()
            elif scope.scope_type == 'ORG':
                return get_reports_by_org(scope.org_id)
            else:
                return get_reports_by_user(scope.user_id)
    """
    user = await get_current_user(request, credentials)
    token = request.state.token

    effective_roles = get_effective_roles(user.roles)

    # 超级管理员：全部数据
    if 'super_admin' in effective_roles:
        return DataScope(
            scope_type='ALL',
            org_id=user.org_id,
            user_id=user.user_id,
        )

    # IAM 模式：从 IAM 获取数据范围
    if settings.iam_enabled:
        try:
            iam_scope = iam_client.get_data_scope(token, 'kb')
            return DataScope(
                scope_type=iam_scope.get('scope', 'SELF'),
                org_id=user.org_id,
                org_ids=iam_scope.get('org_ids'),
                user_id=user.user_id,
            )
        except Exception:
            pass

    # 管理员：本组织数据
    if 'admin' in effective_roles:
        return DataScope(
            scope_type='ORG',
            org_id=user.org_id,
            user_id=user.user_id,
        )

    # 默认：仅自己的数据
    return DataScope(
        scope_type='SELF',
        org_id=user.org_id,
        user_id=user.user_id,
    )


def require_org_access(org_id_param: str = 'org_id'):
    """
    组织访问权限检查

    检查用户是否有权限访问指定组织的数据

    Args:
        org_id_param: 路径参数或查询参数中组织ID的名称

    Usage:
        @router.get("/org/{org_id}/reports")
        async def get_org_reports(
            org_id: str,
            user: UserContext = Depends(require_org_access("org_id"))
        ):
            pass
    """
    async def org_checker(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> UserContext:
        user = await get_current_user(request, credentials)
        scope = await get_data_scope(request, credentials)

        # 获取目标组织ID
        target_org_id = request.path_params.get(org_id_param) or \
                        request.query_params.get(org_id_param)

        if target_org_id and not scope.can_access_org(target_org_id):
            raise HTTPException(
                status_code=403,
                detail="无权访问该组织的数据"
            )

        return user

    return org_checker


# ============================================================================
# 细粒度权限检查（需要 IAM 支持）
# ============================================================================

def require_permission(resource: str, action: str = None):
    """
    细粒度权限检查（需要 IAM 策略引擎支持）

    Args:
        resource: 资源标识，如 "kb:report", "kb:case"
        action: 操作，如 "create", "read", "update", "delete"

    Usage:
        @router.post("/upload")
        async def upload_report(
            user: UserContext = Depends(require_permission("kb:report", "create"))
        ):
            pass
    """
    async def permission_checker(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> UserContext:
        user = await get_current_user(request, credentials)

        # 简单模式下，admin 角色拥有全部权限
        if not settings.iam_enabled:
            if 'admin' in get_effective_roles(user.roles):
                return user
            raise HTTPException(status_code=403, detail="权限不足")

        # IAM 模式：调用策略引擎评估
        token = request.state.token
        allowed = iam_client.evaluate_policy(token, resource, action)

        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"无权执行此操作: {resource}:{action or '*'}"
            )

        return user

    return permission_checker


# ============================================================================
# 辅助函数
# ============================================================================

def get_user_from_request(request: Request) -> Optional[UserContext]:
    """从 request.state 获取用户（用于非 Depends 场景）"""
    return getattr(request.state, 'user', None)


def get_token_from_request(request: Request) -> Optional[str]:
    """从 request.state 获取 token"""
    return getattr(request.state, 'token', None)


# ============================================================================
# 便捷依赖（向后兼容）
# ============================================================================

# 保留 verify_token 作为别名，便于旧代码迁移
async def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> bool:
    """
    简单验证（向后兼容）

    建议新代码使用 get_current_user
    """
    await get_current_user(request, credentials)
    return True


# 常用角色依赖
require_admin = require_roles('admin')
require_reviewer = require_roles('admin', 'reviewer')
require_editor = require_roles('admin', 'editor')
require_viewer = require_roles('admin', 'reviewer', 'editor', 'viewer')


# ============================================================================
# 用户登录相关函数
# ============================================================================

def generate_token() -> str:
    """生成随机的Token"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """对Token进行哈希（用于存储）"""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_user_token(token: str):
    """
    验证用户Token，返回User对象
    """
    from knowledge_base.db_connection import pg_cursor

    token_hash = hash_token(token)

    try:
        with pg_cursor(commit=True) as cursor:
            # 查找有效Token
            cursor.execute("""
               SELECT user_id
               FROM user_tokens
               WHERE token_hash = %s
                 AND expires_at > CURRENT_TIMESTAMP
           """, (token_hash,))
            row = cursor.fetchone()

            if not row:
                return None

            user_id = row[0]

            # 更新最后使用时间
            cursor.execute("""
               UPDATE user_tokens
               SET last_used_at = CURRENT_TIMESTAMP
               WHERE token_hash = %s
           """, (token_hash,))

            # 获取用户信息
            from .models.user import UserRepository
            return UserRepository.get_by_id(user_id)
    except Exception:
        return None


def user_to_context(user) -> UserContext:
    """将User模型转换为UserContext"""
    return UserContext(
        user_id=str(user.id),
        username=user.real_name or user.username,
        org_id=str(user.org_id) if user.org_id else 'default',
        org_name=getattr(user, 'org_name', '') or '',
        roles=user.roles if hasattr(user, 'roles') else [],
    )


def authenticate_user(username: str, password: str, ip_address: str = "") -> tuple:
    """
    验证用户名密码

    返回: (User, error_message)
    """
    from .models.user import UserRepository, verify_password

    user = UserRepository.get_by_username(username)

    if not user:
        return None, "用户名或密码错误"

    # 检查用户状态
    if user.status == 'inactive':
        return None, "用户已被禁用"

    if user.status == 'locked':
        return None, "用户已被锁定，请联系管理员"

    # 检查登录失败次数
    if user.login_fail_count >= 5:
        UserRepository.update(user.id, status='locked')
        return None, "登录失败次数过多，账号已被锁定"

    # 验证密码
    if not verify_password(password, user.password_hash):
        UserRepository.update_login_info(user.id, ip_address, success=False)
        remaining = 5 - user.login_fail_count - 1
        return None, f"用户名或密码错误，还剩 {remaining} 次尝试机会"

    # 登录成功
    UserRepository.update_login_info(user.id, ip_address, success=True)
    return user, ""


def create_user_token(user, ip_address: str = "", device_info: str = "") -> str:
    """
    为用户创建访问Token
    """
    from knowledge_base.db_connection import pg_cursor

    token = generate_token()
    token_hash = hash_token(token)

    # Token有效期
    token_expire_hours = getattr(settings, 'token_expire_hours', 24)
    expires_at = datetime.now() + timedelta(hours=token_expire_hours)

    with pg_cursor(commit=True) as cursor:
        cursor.execute("""
           INSERT INTO user_tokens (user_id, token_hash, token_type, device_info, ip_address, expires_at)
           VALUES (%s, %s, 'access', %s, %s, %s)
       """, (user.id, token_hash, device_info[:200] if device_info else None, ip_address, expires_at))

    return token


def revoke_user_token(token: str) -> bool:
    """
    撤销Token（登出）
    """
    from knowledge_base.db_connection import pg_cursor

    token_hash = hash_token(token)

    with pg_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM user_tokens WHERE token_hash = %s", (token_hash,))
        return cursor.rowcount > 0


def revoke_all_user_tokens(user_id: int) -> int:
    """
    撤销用户的所有Token
    """
    from knowledge_base.db_connection import pg_cursor

    with pg_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM user_tokens WHERE user_id = %s", (user_id,))