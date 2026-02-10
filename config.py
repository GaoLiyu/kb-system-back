"""
全局配置
========
统一管理所有配置项
"""

import os
from typing import Set, List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    统一配置类

    配置优先级（从高到低）：
    1. 环境变量
    2. .env 文件
    3. 默认值
    """

    # ========================================================================
    # 应用基础配置
    # ========================================================================
    app_name: str = "房地产估价知识库系统"
    version: str = "3.0.0"
    debug: bool = False

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000

    api_token: str = "boyixuishaoyulideson"

    # ========================================================================
    # 数据库配置
    # ========================================================================
    # PostgreSQL
    pg_host: str = Field(default="127.0.0.1", alias="PG_HOST")
    pg_port: int = Field(default=5432, alias="PG_PORT")
    pg_user: str = Field(default="kb_admin", alias="PG_USER")
    pg_password: str = Field(default="", alias="PG_PASSWORD")
    pg_database: str = Field(default="real_estate_kb", alias="PG_DATABASE")

    # 连接池
    pg_pool_min: int = Field(default=2, alias="PG_POOL_MIN")
    pg_pool_max: int = Field(default=10, alias="PG_POOL_MAX")

    # Milvus
    milvus_host: str = Field(default="127.0.0.1", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19540, alias="MILVUS_PORT")
    milvus_collection: str = Field(default="case_vectors", alias="MILVUS_COLLECTION")

    # ========================================================================
    # 知识库配置
    # ========================================================================
    kb_path: str = "./knowledge_base/storage"
    enable_vector: bool = True
    enable_llm: bool = True
    use_database: bool = True
    embedding_model_path: str = "/opt/models/bge-large-zh-v1.5"

    # ========================================================================
    # LLM 配置
    # ========================================================================
    llm_api_key: str = ""
    llm_base_url: str = "https://api.siliconflow.cn/v1"
    llm_model: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
    llm_timeout: int = 60
    llm_max_retries: int = 3

    # ========================================================================
    # 认证配置
    # ========================================================================
    iam_enabled: bool = False
    iam_base_url: str = "http://localhost:8080"
    iam_app_code: str = "real-estate_kb"
    iam_app_secret: str = ""

    token_expire_hours: int = 24

    # ========================================================================
    # 上传配置
    # ========================================================================
    upload_dir: str = "./uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: Set[str] = {".doc", ".docx"}

    # ========================================================================
    # CORS 配置
    # ========================================================================
    cors_origins: List[str] = ["*"]

    # ========================================================================
    # 校验配置
    # ========================================================================
    validation_correction_min: float = 0.85
    validation_correction_max: float = 1.15
    validation_formula_tolerance: float = 10.0
    validation_min_case_count: int = 3

    class Config:
        env_file = ".env"
        env_prefix = "KB_"
        extra = "ignore"
        populate_by_name = True  # 允许使用别名


# 全局配置实例
settings = Settings()

# ========================================================================
# 兼容旧代码的常量导出
# ========================================================================

# 知识库目录（兼容）
KB_DIR = settings.kb_path

# 校验配置（兼容）
VALIDATION_CONFIG = {
    'correction_range': (settings.validation_correction_min, settings.validation_correction_max),
    'formula_tolerance': settings.validation_formula_tolerance,
    'min_case_count': settings.validation_min_case_count,
}


# ========================================================================
# 初始化
# ========================================================================

def init_config():
    """初始化配置（创建必要的目录等）"""
    # 确保上传目录存在
    os.makedirs(settings.upload_dir, exist_ok=True)

    # 确保知识库目录存在
    os.makedirs(settings.kb_path, exist_ok=True)

    # 设置环境变量供其他模块读取
    os.environ['KB_USE_DATABASE'] = str(settings.use_database).lower()
    os.environ['EMBEDDING_MODEL_PATH'] = settings.embedding_model_path


# 自动初始化
init_config()