"""
数据库连接配置
==============
PostgreSQL 和 Milvus 连接管理
"""

import os
from typing import Optional
from contextlib import contextmanager


# ============================================================================
# PostgreSQL 配置
# ============================================================================

PG_CONFIG = {
    'host': os.getenv('PG_HOST', '127.0.0.1'),
    'port': int(os.getenv('PG_PORT', '5432')),
    'user': os.getenv('PG_USER', 'kb_admin'),
    'password': os.getenv('PG_PASSWORD', ''),
    'database': os.getenv('PG_DATABASE', 'real_estate_kb'),
}


def get_pg_connection():
    """获取 PostgreSQL 连接"""
    import psycopg2
    return psycopg2.connect(
        host=PG_CONFIG['host'],
        port=PG_CONFIG['port'],
        user=PG_CONFIG['user'],
        password=PG_CONFIG['password'],
        database=PG_CONFIG['database'],
    )


@contextmanager
def pg_cursor(commit=True):
    """PostgreSQL 游标上下文管理器"""
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# Milvus 配置
# ============================================================================

MILVUS_CONFIG = {
    'host': os.getenv('MILVUS_HOST', '127.0.0.1'),
    'port': int(os.getenv('MILVUS_PORT', '19540')),
    'collection': os.getenv('MILVUS_COLLECTION', 'case_vectors'),
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


if __name__ == "__main__":
    test_all_connections()
