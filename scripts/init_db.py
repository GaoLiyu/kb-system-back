#!/usr/bin/env python3
"""
数据库初始化脚本 - Python 版本
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
        # ========== 1. 组织/机构表 ==========
        print("创建 organizations 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id SERIAL PRIMARY KEY,
                org_code VARCHAR(50) UNIQUE NOT NULL,
                org_name VARCHAR(200) NOT NULL,
                parent_id INTEGER REFERENCES organizations(id),
                level INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'active',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_parent ON organizations(parent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_org_status ON organizations(status)")

        cursor.execute("""
            INSERT INTO organizations (org_code, org_name, description)
            VALUES ('default', '默认组织', '系统默认组织')
            ON CONFLICT (org_code) DO NOTHING
        """)
        print("  ✓ organizations 表")

        # ========== 2. 用户表 ==========
        print("创建 users 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                real_name VARCHAR(100),
                email VARCHAR(100),
                phone VARCHAR(20),
                avatar VARCHAR(500),
                org_id INTEGER REFERENCES organizations(id),
                status VARCHAR(20) DEFAULT 'active',
                last_login_at TIMESTAMP,
                last_login_ip VARCHAR(50),
                login_fail_count INTEGER DEFAULT 0,
                password_changed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                remark TEXT
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        cursor.execute("COMMENT ON TABLE users IS '用户表'")
        cursor.execute("COMMENT ON COLUMN users.username IS '用户名，唯一'")
        cursor.execute("COMMENT ON COLUMN users.password_hash IS '密码哈希，使用bcrypt'")
        cursor.execute("COMMENT ON COLUMN users.status IS '状态：active-正常，inactive-禁用，locked-锁定'")
        print("  ✓ users 表")

        # ========== 3. 用户角色关联表 ==========
        print("创建 user_roles 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role_code VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, role_code)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_code)")

        cursor.execute("COMMENT ON TABLE user_roles IS '用户角色关联表'")
        cursor.execute("COMMENT ON COLUMN user_roles.role_code IS '角色编码：super_admin/admin/reviewer/editor/viewer'")
        print("  ✓ user_roles 表")

        # ========== 4. 用户Token表 ==========
        print("创建 user_tokens 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash VARCHAR(255) NOT NULL,
                token_type VARCHAR(20) DEFAULT 'access',
                device_info VARCHAR(200),
                ip_address VARCHAR(50),
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_hash ON user_tokens(token_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_expires ON user_tokens(expires_at)")

        cursor.execute("""
            CREATE OR REPLACE FUNCTION clean_expired_tokens()
            RETURNS INTEGER AS $$
            DECLARE
                deleted_count INTEGER;
            BEGIN
                DELETE FROM user_tokens WHERE expires_at < CURRENT_TIMESTAMP;
                GET DIAGNOSTICS deleted_count = ROW_COUNT;
                RETURN deleted_count;
            END;
            $$ LANGUAGE plpgsql
        """)
        print("  ✓ user_tokens 表")

        # ========== 5. documents 表 ==========
        print("创建 documents 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                doc_id VARCHAR(64) UNIQUE NOT NULL,
                filename VARCHAR(255),
                file_path VARCHAR(500),
                file_type VARCHAR(20),
                report_type VARCHAR(50),
                address TEXT,
                area FLOAT,
                case_count INT DEFAULT 0,
                org_id VARCHAR(64),
                create_by VARCHAR(64),
                update_by VARCHAR(64),
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_report_type ON documents(report_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_org_id ON documents(org_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN(metadata)")
        print("  ✓ documents 表")

        # ========== 6. cases 表 ==========
        print("创建 cases 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id SERIAL PRIMARY KEY,
                case_id VARCHAR(64) UNIQUE NOT NULL,
                doc_id VARCHAR(64) REFERENCES documents(doc_id) ON DELETE CASCADE,
                report_type VARCHAR(50),
                address TEXT,
                district VARCHAR(100),
                street VARCHAR(100),
                area FLOAT,
                price FLOAT,
                usage VARCHAR(50),
                build_year INT,
                total_floor INT,
                current_floor INT,
                orientation VARCHAR(20),
                decoration VARCHAR(20),
                structure VARCHAR(50),
                org_id VARCHAR(64),
                create_by VARCHAR(64),
                case_data JSONB,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_doc_id ON cases(doc_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_usage ON cases(usage)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_area ON cases(area)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_price ON cases(price)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases(org_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_case_data ON cases USING GIN(case_data)")
        print("  ✓ cases 表")

        # ========== 7. review_tasks 表 ==========
        print("创建 review_tasks 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_tasks (
                id SERIAL PRIMARY KEY,
                task_id VARCHAR(64) UNIQUE NOT NULL,
                filename VARCHAR(255),
                file_path VARCHAR(500),
                review_mode VARCHAR(20) DEFAULT 'full',
                status VARCHAR(20) DEFAULT 'pending',
                overall_risk VARCHAR(20),
                issue_count INT DEFAULT 0,
                validation_count INT DEFAULT 0,
                llm_count INT DEFAULT 0,
                org_id VARCHAR(64),
                create_by VARCHAR(64),
                result JSONB,
                error TEXT,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                start_time TIMESTAMP,
                end_time TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_create_time ON review_tasks(create_time DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_org_id ON review_tasks(org_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_tasks_result ON review_tasks USING GIN(result)")
        print("  ✓ review_tasks 表")

        # ========== 8. 操作日志表 ==========
        print("创建 audit_logs 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(64),
                username VARCHAR(128),
                org_id VARCHAR(64),
                org_name VARCHAR(128),
                action VARCHAR(64) NOT NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128),
                resource_name VARCHAR(256),
                method VARCHAR(16),
                path VARCHAR(512),
                query_params TEXT,
                ip_address VARCHAR(64),
                user_agent VARCHAR(512),
                status VARCHAR(16) DEFAULT 'success',
                status_code INT,
                error_message TEXT,
                detail JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_ms INT
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_org_id ON audit_logs(org_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_type ON audit_logs(resource_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON audit_logs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON audit_logs(user_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_org_time ON audit_logs(org_id, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id)")

        cursor.execute("COMMENT ON TABLE audit_logs IS '操作日志表'")
        cursor.execute("COMMENT ON COLUMN audit_logs.action IS '操作类型: create/read/update/delete/upload/download/export/login/logout'")
        cursor.execute("COMMENT ON COLUMN audit_logs.resource_type IS '资源类型: report/case/review_task/user/system'")
        cursor.execute("COMMENT ON COLUMN audit_logs.status IS '状态: success/failed'")
        cursor.execute("COMMENT ON COLUMN audit_logs.detail IS '操作详情，JSON格式'")

        cursor.execute("""
            CREATE OR REPLACE FUNCTION clean_old_audit_logs(days_to_keep INT DEFAULT 90)
            RETURNS INT AS $$
            DECLARE
                deleted_count INT;
            BEGIN
                DELETE FROM audit_logs
                WHERE created_at < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;
                GET DIAGNOSTICS deleted_count = ROW_COUNT;
                RETURN deleted_count;
            END;
            $$ LANGUAGE plpgsql
        """)
        print("  ✓ audit_logs 表")

        # ========== 9. 触发器 ==========
        print("创建触发器...")
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)

        cursor.execute("DROP TRIGGER IF EXISTS trigger_users_updated_at ON users")
        cursor.execute("""
            CREATE TRIGGER trigger_users_updated_at
                BEFORE UPDATE ON users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at()
        """)

        cursor.execute("DROP TRIGGER IF EXISTS trigger_organizations_updated_at ON organizations")
        cursor.execute("""
            CREATE TRIGGER trigger_organizations_updated_at
                BEFORE UPDATE ON organizations
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at()
        """)
        print("  ✓ 触发器创建完成")

        # ========== 10. 创建默认管理员用户 ==========
        print("创建默认管理员用户...")
        cursor.execute("""
            SELECT id FROM organizations WHERE org_code = 'default'
        """)
        default_org_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO users (username, password_hash, real_name, org_id, status)
            VALUES (
                'admin',
                '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G2D0W3xFfF5k5e',
                '系统管理员',
                %s,
                'active'
            )
            ON CONFLICT (username) DO NOTHING
            RETURNING id
        """, (default_org_id,))

        result = cursor.fetchone()
        if result:
            admin_user_id = result[0]
            cursor.execute("""
                INSERT INTO user_roles (user_id, role_code) VALUES (%s, 'super_admin')
            """, (admin_user_id,))
            print("  ✓ 默认管理员用户创建完成")
        else:
            print("  ✓ 默认管理员用户已存在")

        conn.commit()
        print("\n✓ PostgreSQL 初始化完成")

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
        print("✓ Milvus 初始化完成")

    except Exception as e:
        print(f"Milvus 初始化跳过: {e}")


def main():
    print("=" * 60)
    print("数据库初始化")
    print("=" * 60)

    init_postgresql()

    try:
        init_milvus()
    except Exception as e:
        print(f"Milvus 初始化跳过: {e}")

    print("\n" + "=" * 60)
    print("初始化完成")
    print("=" * 60)
    print("用户管理表: organizations, users, user_roles, user_tokens")
    print("业务表: documents, cases, review_tasks")
    print("操作日志表: audit_logs")
    print("默认管理员: admin / admin123")
    print("⚠️  请立即修改默认密码！")
    print("=" * 60)


if __name__ == "__main__":
    main()