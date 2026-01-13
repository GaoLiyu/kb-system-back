"""
IAM Center 客户端
"""
import time
import httpx
from typing import Optional, Dict, List
from functools import lru_cache
from jose import jwt, jwk, JWTError
from pydantic import BaseModel

from .config import settings


class UserContext(BaseModel):
    """用户上下文"""
    user_id: str
    org_id: str
    roles: List[str] = []
    perm_ver: Optional[int] = None

    # 扩展信息（从 IAM 获取）
    username: Optional[str] = None
    org_name: Optional[str] = None


class IAMClient:
    """IAM 客户端"""

    def __init__(self):
        self.base_url = settings.iam_base_url
        self.app_code = settings.iam_app_code
        self._jwks_cache = None
        self._jwks_cache_time = 0
        self._jwks_cache_ttl = 86400  # 24小时

    def _get_jwks(self) -> Dict:
        """获取 JWKS 公钥（带缓存）"""
        now = time.time()

        # 检查缓存
        if self._jwks_cache and (now - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks_cache

        # 请求 JWKS
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url}/.well-known/jwks.json")
                resp.raise_for_status()
                self._jwks_cache = resp.json()
                self._jwks_cache_time = now
                return self._jwks_cache
        except Exception as e:
            # 如果有缓存，继续使用旧缓存
            if self._jwks_cache:
                return self._jwks_cache
            raise Exception(f"获取 JWKS 失败: {e}")

    def _get_public_key(self, token: str):
        """从 JWKS 获取公钥"""
        jwks = self._get_jwks()

        # 解析 token header 获取 kid
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
        except JWTError:
            raise Exception("无效的 Token 格式")

        # 查找对应的公钥
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return jwk.construct(key)

        # 如果没有 kid，使用第一个
        if jwks.get('keys'):
            return jwk.construct(jwks['keys'][0])

        raise Exception("未找到匹配的公钥")

    def verify_token(self, token: str) -> UserContext:
        """验证 JWT Token 并返回用户上下文"""
        try:
            # 获取公钥
            public_key = self._get_public_key(token)

            # 验证并解码
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                options={
                    'verify_aud': False,  # 暂不验证 audience
                    'verify_exp': True,
                }
            )

            return UserContext(
                user_id=payload.get('sub'),
                org_id=payload.get('org_id'),
                roles=payload.get('roles', []),
                perm_ver=payload.get('perm_ver'),
            )

        except jwt.ExpiredSignatureError:
            raise Exception("Token 已过期")
        except JWTError as e:
            raise Exception(f"Token 验证失败: {e}")

    def get_user_menus(self, token: str) -> List[Dict]:
        """获取用户菜单"""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self.base_url}/me/menus",
                    params={'app': self.app_code},
                    headers={'Authorization': f'Bearer {token}'}
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get('data', [])
        except Exception as e:
            raise Exception(f"获取菜单失败: {e}")

    def evaluate_policy(self, token: str, resource: str, action: str = None) -> bool:
        """评估权限"""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.base_url}/policy/evaluate",
                    json={
                        'resource': resource,
                        'action': action or resource,
                    },
                    headers={'Authorization': f'Bearer {token}'}
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get('data', {}).get('allowed', False)
        except Exception:
            return False

    def get_data_scope(self, token: str, domain: str) -> Dict:
        """获取数据范围"""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self.base_url}/policy/data-scope",
                    params={'domain': domain},
                    headers={'Authorization': f'Bearer {token}'}
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get('data', {})
        except Exception as e:
            # 默认返回仅自己
            return {'scope': 'SELF', 'org_ids': None, 'user_id': None}


# 单例
iam_client = IAMClient()