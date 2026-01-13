#!/usr/bin/env python3
"""
数据库初始化脚本
"""

import os
import sys

# 加载 .env
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.db_connection import get_pg_connection, get_milvus_collection, connect_milvus


def init_postgresql():
    """初始化 PostgreSQL 表"""
    print("初始化 PostgreSQL...")

    conn = get_pg_connection()
    cursor = conn.cursor()

    try:
        # documents 表
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS documents
                       (
                           id
                           SERIAL
                           PRIMARY
                           KEY,
                           doc_id
                           VARCHAR
                       (
                           64
                       ) UNIQUE NOT NULL,
                           filename VARCHAR
                       (
                           255
                       ),
                           file_path VARCHAR
                       (
                           500
                       ),
                           file_type VARCHAR
                       (
                           20
                       ),
                           report_type VARCHAR
                       (
                           50
                       ),
                           address TEXT,
                           area FLOAT,
                           case_count INT DEFAULT 0,
                           create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           metadata JSONB
                           )
                       """)
        print("  ✓ documents 表")

        # cases 表
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS cases
                       (
                           id
                           SERIAL
                           PRIMARY
                           KEY,
                           case_id
                           VARCHAR
                       (
                           64
                       ) UNIQUE NOT NULL,
                           doc_id VARCHAR
                       (
                           64
                       ) REFERENCES documents
                       (
                           doc_id
                       ) ON DELETE CASCADE,
                           report_type VARCHAR
                       (
                           50
                       ),
                           address TEXT,
                           district VARCHAR
                       (
                           100
                       ),
                           street VARCHAR
                       (
                           100
                       ),
                           area FLOAT,
                           price FLOAT,
                           usage VARCHAR
                       (
                           50
                       ),
                           build_year INT,
                           total_floor INT,
                           current_floor INT,
                           orientation VARCHAR
                       (
                           20
                       ),
                           decoration VARCHAR
                       (
                           20
                       ),
                           structure VARCHAR
                       (
                           50
                       ),
                           case_data JSONB,
                           create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                           )
                       """)
        print("  ✓ cases 表")

        # review_tasks 表（审查任务/日志）
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS review_tasks
                       (
                           id
                           SERIAL
                           PRIMARY
                           KEY,
                           task_id
                           VARCHAR
                       (
                           64
                       ) UNIQUE NOT NULL,
                           filename VARCHAR
                       (
                           255
                       ),
                           file_path VARCHAR
                       (
                           500
                       ),
                           review_mode VARCHAR
                       (
                           20
                       ) DEFAULT 'full',
                           status VARCHAR
                       (
                           20
                       ) DEFAULT 'pending',
                           overall_risk VARCHAR
                       (
                           20
                       ),
                           issue_count INT DEFAULT 0,
                           validation_count INT DEFAULT 0,
                           llm_count INT DEFAULT 0,
                           result JSONB,
                           error TEXT,
                           create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           start_time TIMESTAMP,
                           end_time TIMESTAMP
                           )
                       """)
        print("  ✓ review_tasks 表")

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_report_type ON documents(report_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_doc_id ON cases(doc_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_usage ON cases(usage)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_area ON cases(area)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_price ON cases(price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_create_time ON review_tasks(create_time DESC)")
        print("  ✓ 索引创建完成")

        # GIN 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN(metadata)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_case_data ON cases USING GIN(case_data)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_result ON review_tasks USING GIN(result)")
        print("  ✓ GIN 索引创建完成")

        conn.commit()
        print("PostgreSQL 初始化完成")

    except Exception as e:
        conn.rollback()
        print(f"PostgreSQL 初始化失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def init_milvus():
    """初始化 Milvus Collection"""
    print("\n初始化 Milvus...")

    try:
        connect_milvus()
        from pymilvus import Collection, FieldSchema, CollectionSchema, DataType, utility

        config = get_milvus_collection()
        collection_name = config['collection']

        if utility.has_collection(collection_name):
            print(f"  Collection '{collection_name}' 已存在")
            return

        fields = [
            FieldSchema(name="case_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="report_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
        ]

        schema = CollectionSchema(fields=fields, description="案例向量索引")
        collection = Collection(name=collection_name, schema=schema)

        # 创建索引
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        collection.create_index(field_name="embedding", index_params=index_params)

        print(f"  ✓ Collection '{collection_name}' 创建完成")
        print("Milvus 初始化完成")

    except Exception as e:
        print(f"Milvus 初始化失败: {e}")
        raise


def main():
    print("=" * 50)
    print("数据库初始化")
    print("=" * 50)

    init_postgresql()

    try:
        init_milvus()
    except Exception as e:
        print(f"Milvus 初始化跳过: {e}")

    print("\n" + "=" * 50)
    print("初始化完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
