"""
API模块
=======
FastAPI接口层，提供HTTP API访问知识库系统
"""

from .app import app
from .config import settings

__all__ = ['app', 'settings']
