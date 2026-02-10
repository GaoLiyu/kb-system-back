"""
数据库连接配置
==============
PostgreSQL 和 Milvus 连接管理
"""

import os
from typing import Optional
from contextlib import contextmanager
import threading

from config import settings

# ============================================================================
# PostgreSQL 配置
# ============================================================================

PG_CONFIG = {
    'host': settings.pg_host,
    'port': settings.pg_port,
    'user': settings.pg_user,
    'password': settings.pg_password,
    'database': settings.pg_database,
}



# ============================================================================
# 连接池管理
# ============================================================================

# 连接池配置
POOL_CONFIG = {
    'minconn': settings.pg_pool_min,
    'maxconn': settings.pg_pool_max,
}

class ConnectionPool:
    """PostgreSQL 连接池管理器（线程安全的单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._pool = None
        self._initialized = True

    def _create_pool(self):
        """创建连接池"""
        # if self._pool is None:
        #     return

        try:
            from psycopg2 import pool

            self._pool = pool.ThreadedConnectionPool(
                POOL_CONFIG['minconn'],
                POOL_CONFIG['maxconn'],
                **PG_CONFIG,
            )
            print(f"PostgreSQL 连接池已创建，最小连接数: {POOL_CONFIG['minconn']}, 最大连接数: {POOL_CONFIG['maxconn']}")
        except Exception as e:
            print(f"PostgreSQL 连接池创建失败: {e}")
            raise e

    def get_connection(self):
        """获取连接"""
        if self._pool is None:
            with self._lock:
                self._create_pool()
        return self._pool.getconn()

    def release_connection(self, conn):
        """释放连接"""
        if self._pool is not None and conn is not None:
            try:
                self._pool.putconn(conn)
            except Exception:
                pass

    def close_all(self):
        """关闭所有链接"""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    def get_stats(self) -> dict:
        """获取连接池状态"""
        if self._pool is None:
            return {'status': 'not_initialized'}

        return {
            'status': 'active',
            'min_connections': POOL_CONFIG['minconn'],
            'max_connections': POOL_CONFIG['maxconn'],
        }


# 全局连接池实例
_connection_pool = ConnectionPool()



def get_pg_connection():
    """获取 PostgreSQL 连接（从连接池）"""
    return _connection_pool.get_connection()


def release_pg_connection(conn):
    """释放 PostgreSQL 连接（归还到连接池）"""
    _connection_pool.release_connection(conn)


@contextmanager
def pg_cursor(commit=True):
    """
    PostgreSQL 游标上下文管理器

    自动管理连接的获取和释放

    Usage:
        with pg_cursor() as cursor:
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
    """
    conn = None
    cursor = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_pg_connection(conn)


# ============================================================================
# Milvus 配置
# ============================================================================

MILVUS_CONFIG = {
    'host': settings.milvus_host,
    'port': settings.milvus_port,
    'collection': settings.milvus_collection,
}


_milvus_connected = False


def connect_milvus():
    """连接 Milvus"""
    global _milvus_connected
    if _milvus_connected:
        return

    from pymilvus import connections
    connections.connect(
        alias="default",
        host=MILVUS_CONFIG['host'],
        port=MILVUS_CONFIG['port'],
    )
    _milvus_connected = True


def get_milvus_collection():
    """获取 Milvus Collection"""
    connect_milvus()
    from pymilvus import Collection
    return Collection(MILVUS_CONFIG['collection'])


# ============================================================================
# 连接测试
# ============================================================================

def test_pg_connection() -> bool:
    """测试 PostgreSQL 连接"""
    try:
        with pg_cursor() as cursor:
            cursor.execute("SELECT 1")
            return True
    except Exception as e:
        print(f"PostgreSQL 连接失败: {e}")
        return False


def test_milvus_connection() -> bool:
    """测试 Milvus 连接"""
    try:
        connect_milvus()
        from pymilvus import utility
        return utility.has_collection(MILVUS_CONFIG['collection'])
    except Exception as e:
        print(f"Milvus 连接失败: {e}")
        return False


def test_all_connections():
    """测试所有连接"""
    print("测试数据库连接...")

    pg_ok = test_pg_connection()
    print(f"  PostgreSQL: {'✓' if pg_ok else '✗'}")

    milvus_ok = test_milvus_connection()
    print(f"  Milvus: {'✓' if milvus_ok else '✗'}")

    return pg_ok and milvus_ok


def get_pool_stats() -> dict:
    """获取连接池统计信息"""
    return _connection_pool.get_stats()


# ============================================================================
# 应用关闭时清理
# ============================================================================

def cleanup():
    """清理资源（应用关闭时调用）"""
    _connection_pool.close_all()


if __name__ == "__main__":
    test_all_connections()
