"""
临时文件管理器
===========================
统一管理临时文件的创建和清理
"""

import os
import tempfile
import threading
import atexit
import time
from typing import Optional, Set
from pathlib import Path


class TempFileManager:
    """
    临时文件管理器

    功能：
    - 创建临时文件并跟踪
    - 自动清理过期文件
    - 应用退出时清理所有文件

    Usage:
        from utils.temp_file import temp_manager

        # 创建临时文件
        path = temp_manager.create_temp_file(suffix=".docx", prefix="upload_")

        # 使用完后清理
        temp_manager.cleanup(path)

        # 或者使用上下文管理器
        with temp_manager.temp_file(suffix=".docx") as path:
            # 使用文件
            pass
        # 自动清理
    """

    def __init__(self, base_dir: str = None, max_age_hours: int = 24):
        """
        初始化

        Args:
            base_dir: 临时文件目录，默认使用系统临时目录
            max_age_hours: 文件最大保留时间（小时）
        """
        self.base_dir = base_dir or tempfile.gettempdir()
        self.max_age_seconds = max_age_hours * 60 * 60
        self._files: Set[str] = set()
        self._lock = threading.Lock()

        # 确保目录存在
        os.makedirs(self.base_dir, exist_ok=True)

        # 注册退出清理
        atexit.register(self.cleanup_all)

    def create_temp_file(self, suffix: str = "", prefix: str = "kb_") -> str:
        """
        创建临时文件

        Args:
            suffix: 文件后缀（如 ".docx"）
            prefix: 文件前缀

        Returns:
            临时文件路径
        """
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=self.base_dir)
        os.close(fd)

        with self._lock:
            self._files.add(path)

        return path

    def register(self, path: str):
        """注册已存在的文件（用于跟踪外部创建的临时文件）"""
        with self._lock:
            self._files.add(path)

    def cleanup(self, path: str) -> bool:
        """
        清理单个文件

        Args:
            path: 文件路径

        Returns:
            是否成功清理
        """
        with self._lock:
            self._files.discard(path)

        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except Exception as e:
            print(f"清理临时文件失败 {path}: {e}")

        return False

    def cleanup_all(self):
        """清理所有跟踪的临时文件"""
        with self._lock:
            files_to_clean = list(self._files)
            self._files.clear()

        for path in files_to_clean:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def cleanup_expired(self) -> int:
        """
        清理过期文件

        Returns:
            清理文件的数量
        """
        now = time.time()
        cleaned = 0

        with self._lock:
            expired = []
            for path in self._files:
                try:
                    if os.path.exists(path):
                        mtime = os.path.getmtime(path)
                        if now - mtime > self.max_age_seconds:
                            expired.append(path)
                    else:
                        expired.append(path)
                except Exception:
                    expired.append(path)

            for path in expired:
                self._files.discard(path)

        for path in expired:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    cleaned += 1
            except Exception:
                pass

        return cleaned

    def temp_file(self, suffix: str = "", prefix: str = "kb_"):
        """
        上下文管理器，自动清理临时文件

        Usage:
            with temp_manager.temp_file(suffix=".docx") as path:
                # 写入文件
                with open(path, 'wb') as f:
                    f.write(content)
                # 处理文件
                process(path)
            # 自动清理
        """
        return _TempFileContext(self, suffix, prefix)

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            return {
                'tracked_files': len(self._files),
                'base_dir': self.base_dir,
                'max_age_hours': self.max_age_seconds / 60 / 60,
            }


class _TempFileContext:
    """临时文件上下文管理器"""

    def __init__(self, manager: TempFileManager, suffix: str, prefix: str):
        self.manager = manager
        self.suffix = suffix
        self.prefix = prefix
        self.path = None

    def __enter__(self) -> str:
        self.path = self.manager.create_temp_file(self.suffix, self.prefix)
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path:
            self.manager.cleanup(self.path)
        return False


# 全局实例
temp_manager = TempFileManager()


# 导出便捷函数
def create_temp_file(suffix: str = "", prefix: str = "kb_") -> str:
    """创建临时文件"""
    return temp_manager.create_temp_file(suffix, prefix)


def cleanup_temp_file(path: str) -> bool:
    """清理临时文件"""
    return temp_manager.cleanup(path)


def register_temp_file(path: str):
    """注册临时文件"""
    temp_manager.register(path)