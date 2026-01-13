"""
用户模型和数据库操作
====================

提供用户、组织的CRUD操作
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import bcrypt

from knowledge_base.db_connection import pg_cursor


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class Organization:
    """组织模型"""
    id: int = 0
    org_code: str = ""
    org_name: str = ""
    parent_id: Optional[int] = None
    level: int = 1
    sort_order: int = 0
    status: str = "active"
    description: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class User:
    """用户模型"""
    id: int = 0
    username: str = ""
    password_hash: str = ""
    real_name: str = ""
    email: str = ""
    phone: str = ""
    avatar: str = ""
    org_id: Optional[int] = None
    org_name: str = ""  # 关联查询
    status: str = "active"
    last_login_at: Optional[datetime] = None
    last_login_ip: str = ""
    login_fail_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    roles: List[str] = field(default_factory=list)


# ============================================================================
# 密码工具
# ============================================================================

def hash_password(password: str) -> str:
    """对密码进行哈希"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


# ============================================================================
# 用户操作
# ============================================================================

class UserRepository:
    """用户数据访问"""

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT u.*, o.org_name
                FROM users u
                LEFT JOIN organizations o ON u.org_id = o.id
                WHERE u.id = %s
            """, (user_id,))
            row = cursor.fetchone()

            if not row:
                return None

            user = UserRepository._row_to_user(row, cursor.description)
            user.roles = UserRepository._get_user_roles(cursor, user_id)
            return user

    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        """根据用户名获取用户"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT u.*, o.org_name
                FROM users u
                LEFT JOIN organizations o ON u.org_id = o.id
                WHERE u.username = %s
            """, (username,))
            row = cursor.fetchone()

            if not row:
                return None

            user = UserRepository._row_to_user(row, cursor.description)
            user.roles = UserRepository._get_user_roles(cursor, user.id)
            return user

    @staticmethod
    def list_users(
        org_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[User], int]:
        """查询用户列表"""
        with pg_cursor(commit=False) as cursor:
            # 构建查询条件
            conditions = []
            params = []

            if org_id:
                conditions.append("u.org_id = %s")
                params.append(org_id)

            if status:
                conditions.append("u.status = %s")
                params.append(status)

            if keyword:
                conditions.append("(u.username ILIKE %s OR u.real_name ILIKE %s OR u.email ILIKE %s)")
                params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 查询总数
            cursor.execute(f"""
                SELECT COUNT(*) FROM users u WHERE {where_clause}
            """, params)
            total = cursor.fetchone()[0]

            # 查询列表
            offset = (page - 1) * page_size
            cursor.execute(f"""
                SELECT u.*, o.org_name
                FROM users u
                LEFT JOIN organizations o ON u.org_id = o.id
                WHERE {where_clause}
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])

            users = []
            for row in cursor.fetchall():
                user = UserRepository._row_to_user(row, cursor.description)
                user.roles = UserRepository._get_user_roles(cursor, user.id)
                users.append(user)

            return users, total

    @staticmethod
    def create(
        username: str,
        password: str,
        real_name: str = "",
        email: str = "",
        phone: str = "",
        org_id: Optional[int] = None,
        roles: List[str] = None,
        created_by: Optional[int] = None,
    ) -> User:
        """创建用户"""
        password_hash = hash_password(password)

        with pg_cursor(commit=True) as cursor:
            # 插入用户
            cursor.execute("""
                INSERT INTO users (username, password_hash, real_name, email, phone, org_id, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (username, password_hash, real_name, email, phone, org_id, created_by))
            user_id = cursor.fetchone()[0]

            # 分配角色
            if roles:
                for role in roles:
                    cursor.execute("""
                        INSERT INTO user_roles (user_id, role_code) VALUES (%s, %s)
                        ON CONFLICT (user_id, role_code) DO NOTHING
                    """, (user_id, role))

            return UserRepository.get_by_id(user_id)

    @staticmethod
    def update(
        user_id: int,
        real_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        org_id: Optional[int] = None,
        status: Optional[str] = None,
        avatar: Optional[str] = None,
    ) -> Optional[User]:
        """更新用户信息"""
        updates = []
        params = []

        if real_name is not None:
            updates.append("real_name = %s")
            params.append(real_name)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if phone is not None:
            updates.append("phone = %s")
            params.append(phone)
        if org_id is not None:
            updates.append("org_id = %s")
            params.append(org_id)
        if status is not None:
            updates.append("status = %s")
            params.append(status)
        if avatar is not None:
            updates.append("avatar = %s")
            params.append(avatar)

        if not updates:
            return UserRepository.get_by_id(user_id)

        params.append(user_id)

        with pg_cursor(commit=True) as cursor:
            cursor.execute(f"""
                UPDATE users SET {", ".join(updates)} WHERE id = %s
            """, params)

        return UserRepository.get_by_id(user_id)

    @staticmethod
    def update_password(user_id: int, new_password: str) -> bool:
        """更新密码"""
        password_hash = hash_password(new_password)

        with pg_cursor(commit=True) as cursor:
            cursor.execute("""
                UPDATE users 
                SET password_hash = %s, password_changed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (password_hash, user_id))
            return cursor.rowcount > 0

    @staticmethod
    def update_roles(user_id: int, roles: List[str]) -> bool:
        """更新用户角色"""
        with pg_cursor(commit=True) as cursor:
            # 删除现有角色
            cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))

            # 添加新角色
            for role in roles:
                cursor.execute("""
                    INSERT INTO user_roles (user_id, role_code) VALUES (%s, %s)
                """, (user_id, role))

            return True

    @staticmethod
    def delete(user_id: int) -> bool:
        """删除用户"""
        with pg_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return cursor.rowcount > 0

    @staticmethod
    def update_login_info(user_id: int, ip_address: str, success: bool):
        """更新登录信息"""
        with pg_cursor(commit=True) as cursor:
            if success:
                cursor.execute("""
                    UPDATE users 
                    SET last_login_at = CURRENT_TIMESTAMP, 
                        last_login_ip = %s,
                        login_fail_count = 0
                    WHERE id = %s
                """, (ip_address, user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET login_fail_count = login_fail_count + 1
                    WHERE id = %s
                """, (user_id,))

    @staticmethod
    def check_username_exists(username: str, exclude_id: Optional[int] = None) -> bool:
        """检查用户名是否存在"""
        with pg_cursor(commit=False) as cursor:
            if exclude_id:
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE username = %s AND id != %s",
                    (username, exclude_id)
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE username = %s",
                    (username,)
                )
            return cursor.fetchone()[0] > 0

    @staticmethod
    def _row_to_user(row: tuple, description) -> User:
        """将数据库行转换为User对象"""
        columns = [col.name for col in description]
        data = dict(zip(columns, row))

        return User(
            id=data.get('id', 0),
            username=data.get('username', ''),
            password_hash=data.get('password_hash', ''),
            real_name=data.get('real_name', '') or '',
            email=data.get('email', '') or '',
            phone=data.get('phone', '') or '',
            avatar=data.get('avatar', '') or '',
            org_id=data.get('org_id'),
            org_name=data.get('org_name', '') or '',
            status=data.get('status', 'active'),
            last_login_at=data.get('last_login_at'),
            last_login_ip=data.get('last_login_ip', '') or '',
            login_fail_count=data.get('login_fail_count', 0),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
        )

    @staticmethod
    def _get_user_roles(cursor, user_id: int) -> List[str]:
        """获取用户角色"""
        cursor.execute(
            "SELECT role_code FROM user_roles WHERE user_id = %s",
            (user_id,)
        )
        return [row[0] for row in cursor.fetchall()]


# ============================================================================
# 组织操作
# ============================================================================

class OrganizationRepository:
    """组织数据访问"""

    @staticmethod
    def get_by_id(org_id: int) -> Optional[Organization]:
        """根据ID获取组织"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("SELECT * FROM organizations WHERE id = %s", (org_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return OrganizationRepository._row_to_org(row, cursor.description)

    @staticmethod
    def list_all(status: Optional[str] = None) -> List[Organization]:
        """获取所有组织"""
        with pg_cursor(commit=False) as cursor:
            if status:
                cursor.execute(
                    "SELECT * FROM organizations WHERE status = %s ORDER BY sort_order, id",
                    (status,)
                )
            else:
                cursor.execute("SELECT * FROM organizations ORDER BY sort_order, id")

            return [
                OrganizationRepository._row_to_org(row, cursor.description)
                for row in cursor.fetchall()
            ]

    @staticmethod
    def create(
        org_code: str,
        org_name: str,
        parent_id: Optional[int] = None,
        description: str = "",
    ) -> Organization:
        """创建组织"""
        with pg_cursor(commit=True) as cursor:
            # 计算层级
            level = 1
            if parent_id:
                cursor.execute("SELECT level FROM organizations WHERE id = %s", (parent_id,))
                row = cursor.fetchone()
                if row:
                    level = row[0] + 1

            cursor.execute("""
                INSERT INTO organizations (org_code, org_name, parent_id, level, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (org_code, org_name, parent_id, level, description))
            org_id = cursor.fetchone()[0]

            return OrganizationRepository.get_by_id(org_id)

    @staticmethod
    def update(
        org_id: int,
        org_name: Optional[str] = None,
        status: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Organization]:
        """更新组织"""
        updates = []
        params = []

        if org_name is not None:
            updates.append("org_name = %s")
            params.append(org_name)
        if status is not None:
            updates.append("status = %s")
            params.append(status)
        if description is not None:
            updates.append("description = %s")
            params.append(description)

        if not updates:
            return OrganizationRepository.get_by_id(org_id)

        params.append(org_id)

        with pg_cursor(commit=True) as cursor:
            cursor.execute(f"""
                UPDATE organizations SET {", ".join(updates)} WHERE id = %s
            """, params)

        return OrganizationRepository.get_by_id(org_id)

    @staticmethod
    def delete(org_id: int) -> bool:
        """删除组织"""
        with pg_cursor(commit=True) as cursor:
            # 检查是否有子组织
            cursor.execute("SELECT COUNT(*) FROM organizations WHERE parent_id = %s", (org_id,))
            if cursor.fetchone()[0] > 0:
                raise ValueError("存在子组织，无法删除")

            # 检查是否有用户
            cursor.execute("SELECT COUNT(*) FROM users WHERE org_id = %s", (org_id,))
            if cursor.fetchone()[0] > 0:
                raise ValueError("组织下存在用户，无法删除")

            cursor.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_org(row: tuple, description) -> Organization:
        """将数据库行转换为Organization对象"""
        columns = [col.name for col in description]
        data = dict(zip(columns, row))

        return Organization(
            id=data.get('id', 0),
            org_code=data.get('org_code', ''),
            org_name=data.get('org_name', ''),
            parent_id=data.get('parent_id'),
            level=data.get('level', 1),
            sort_order=data.get('sort_order', 0),
            status=data.get('status', 'active'),
            description=data.get('description', '') or '',
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
        )
