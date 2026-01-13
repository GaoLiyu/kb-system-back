"""知识库模块"""

import os

# 根据环境变量选择使用数据库版本还是文件版本
USE_DATABASE = os.getenv('KB_USE_DATABASE', 'false').lower() == 'true'

if USE_DATABASE:
    """使用数据库版本"""
    from .kb_manager_db import KnowledgeBaseManager
    try:
        from .vector_store_milvus import MilvusVectorStore as VectorStore
        from .vector_store_milvus import MilvusVectorStoreConfig as VectorStoreConfig
    except ImportError:
        VectorStore = None
        VectorStoreConfig = None
else:
    """使用文件版本"""
    from .kb_manager import KnowledgeBaseManager, result_to_dict
    try:
        from .vector_store import VectorStore, VectorStoreConfig
    except ImportError:
        VectorStore = None
        VectorStoreConfig = None

from .kb_query import KnowledgeBaseQuery

__all__ = [
    'KnowledgeBaseManager',
    'KnowledgeBaseQuery',
    'result_to_dict',
    'VectorStore',
    'VectorStoreConfig',
    'USE_DATABASE',
]
