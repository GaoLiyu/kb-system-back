"""路由模块"""

from .kb import router as kb_router
from .search import router as search_router
from .review import router as review_router
from .generate import router as generate_router
from .stats import router as stats_router
from .config import router as config_router
from .audit import router as audit_router
from .users import router as users_router
from .tasks import router as tasks_router
from .sse import router as sse_router

__all__ = [
    'kb_router',
    'search_router',
    'review_router',
    'generate_router',
    'stats_router',
    'config_router',
    'audit_router',
    'users_router',
    'tasks_router',
    'sse_router'
]
