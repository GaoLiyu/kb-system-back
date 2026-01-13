"""
添加组织和用户字段
"""
import sys
sys.path.insert(0, '/data/python/real-estate-kb')

from knowledge_base.db_connection import pg_cursor

def migrate():
    """添加 org_id, create_by, update_by 字段"""

    with pg_cursor() as cursor:
        # ========== documents 表 ==========
        print("正在修改 documents 表...")

        # 添加 org_id
        cursor.execute("""
            ALTER TABLE documents 
            ADD COLUMN IF NOT EXISTS org_id VARCHAR(64)
        """)

        # 添加 create_by
        cursor.execute("""
            ALTER TABLE documents 
            ADD COLUMN IF NOT EXISTS create_by VARCHAR(64)
        """)

        # 添加 update_by
        cursor.execute("""
            ALTER TABLE documents 
            ADD COLUMN IF NOT EXISTS update_by VARCHAR(64)
        """)

        # 添加 update_time
        cursor.execute("""
            ALTER TABLE documents 
            ADD COLUMN IF NOT EXISTS update_time TIMESTAMP
        """)

        # 添加索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_org_id ON documents(org_id)
        """)

        print("  ✓ documents 表修改完成")

        # ========== cases 表 ==========
        print("正在修改 cases 表...")

        # 添加 org_id
        cursor.execute("""
            ALTER TABLE cases 
            ADD COLUMN IF NOT EXISTS org_id VARCHAR(64)
        """)

        # 添加 create_by
        cursor.execute("""
            ALTER TABLE cases 
            ADD COLUMN IF NOT EXISTS create_by VARCHAR(64)
        """)

        # 添加索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases(org_id)
        """)

        print("  ✓ cases 表修改完成")

        # ========== review_tasks 表 ==========
        print("正在修改 review_tasks 表...")

        # 添加 org_id
        cursor.execute("""
            ALTER TABLE review_tasks 
            ADD COLUMN IF NOT EXISTS org_id VARCHAR(64)
        """)

        # 添加 create_by
        cursor.execute("""
            ALTER TABLE review_tasks 
            ADD COLUMN IF NOT EXISTS create_by VARCHAR(64)
        """)

        # 添加索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_tasks_org_id ON review_tasks(org_id)
        """)

        print("  ✓ review_tasks 表修改完成")

    print("\n✓ 所有表迁移完成!")


def set_default_org(default_org_id: str = 'default', default_user_id: str = 'system'):
    """给历史数据设置默认值"""

    with pg_cursor() as cursor:
        print(f"\n正在设置默认值: org_id='{default_org_id}', create_by='{default_user_id}'")

        cursor.execute("""
            UPDATE documents SET org_id = %s WHERE org_id IS NULL
        """, (default_org_id,))
        print(f"  ✓ documents 更新 {cursor.rowcount} 条")

        cursor.execute("""
            UPDATE documents SET create_by = %s WHERE create_by IS NULL
        """, (default_user_id,))

        cursor.execute("""
            UPDATE cases SET org_id = %s WHERE org_id IS NULL
        """, (default_org_id,))
        print(f"  ✓ cases 更新 {cursor.rowcount} 条")

        cursor.execute("""
            UPDATE cases SET create_by = %s WHERE create_by IS NULL
        """, (default_user_id,))

        cursor.execute("""
            UPDATE review_tasks SET org_id = %s WHERE org_id IS NULL
        """, (default_org_id,))
        print(f"  ✓ review_tasks 更新 {cursor.rowcount} 条")

        cursor.execute("""
            UPDATE review_tasks SET create_by = %s WHERE create_by IS NULL
        """, (default_user_id,))

    print("\n✓ 默认值设置完成!")


if __name__ == '__main__':
    migrate()
    set_default_org()