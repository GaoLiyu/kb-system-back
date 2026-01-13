"""
房地产估价知识库系统 - API服务
==============================

启动方式:
    uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

或者直接运行:
    python -m api.app
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routes import (
    kb_router,
    search_router,
    review_router,
    generate_router,
    stats_router,
    config_router,
    audit_router,
    users_router
)


# ============================================================================
# 创建应用
# ============================================================================

app = FastAPI(
    title="房地产估价知识库系统",
    description="""
    基于比较法的房地产估价报告知识库系统API
    
    ## 功能模块
    
    * **知识库管理** - 上传、删除、查看报告
    * **搜索** - 字段搜索、语义搜索、混合搜索
    * **审查** - 完整审查、快速校验、数据提取
    * **生成辅助** - 推荐案例、参考数据、输入验证
    * **系统配置** - 获取系统配置、用户信息
    * **审计日志** - 操作日志查询和统计
    
    ## 认证
    
    所有接口需要Bearer Token认证:
    ```
    Authorization: Bearer your-token-here
    ```
    """,
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ============================================================================
# 中间件
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 注册路由
# ============================================================================

app.include_router(kb_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(review_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(users_router, prefix="/api")


# ============================================================================
# 静态文件（前端）
# ============================================================================

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# ============================================================================
# 根路由
# ============================================================================

@app.get("/api", tags=["系统"])
def api_root():
    """API根路径"""
    return {
        "name": "房地产估价知识库系统",
        "version": "3.0.0",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["系统"])
def health_check():
    """健康检查"""
    return {"status": "ok"}


# ============================================================================
# 启动入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
