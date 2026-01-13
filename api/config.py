"""
API配置
"""

import os
from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """API配置"""
    
    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # 知识库配置
    kb_path: str = "./knowledge_base/storage"
    enable_vector: bool = True
    enable_llm: bool = True
    use_database: bool = True
    embedding_model_path: str = "/data/models/bge-large-zh-v1.5"
    
    # 上传配置
    upload_dir: str = "./uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: set = {".doc", ".docx"}

    # LLM配置
    llm_api_key: str = ""
    llm_base_url: str = "https://api.siliconflow.cn/v1"
    llm_model: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"

    # CORS配置
    cors_origins: list = ["*"]

    # IAM配置
    iam_enabled: bool = os.getenv("IAM_ENABLED", "false").lower() == 'true'
    iam_base_url: str = os.getenv("IAM_BASE_URL", "http://localhost:8080")
    iam_app_code: str = os.getenv("IAM_APP_CODE", "real-estate_kb")
    iam_app_secret: str = os.getenv("IAM_APP_SECRET", "")

    # 鉴权配置
    api_token: str = os.getenv("API_TOKEN", "changeme")  # 生产环境务必修改
    token_expire_hours: int = 24
    
    class Config:
        env_prefix = "KB_"
        env_file = ".env"
        extra = 'ignore'


settings = APISettings()

# 确保上传目录存在
os.makedirs(settings.upload_dir, exist_ok=True)

# 设置环境变量供其他模块读取
os.environ['KB_USE_DATABASE'] = str(settings.use_database).lower()
os.environ['EMBEDDING_MODEL_PATH'] = settings.embedding_model_path