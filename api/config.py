"""
API 配置
========
从全局配置导入，提供 API 特定的便捷访问
"""

# 直接从全局配置导入
from config import settings, Settings

# 为了兼容性，保留 APISettings 别名
APISettings = Settings

__all__ = ['settings', 'Settings', 'APISettings']