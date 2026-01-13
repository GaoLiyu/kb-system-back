#!/usr/bin/env python3
"""
数据迁移脚本
============
将现有 JSON 文件数据迁移到 PostgreSQL 和 Milvus
"""

import os
import sys
import json
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_json_index(base_path: str) -> Dict:
    """加载现有的JSON索引"""
    index_file = os.path.join(base_path, "index", "main_index.json")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {'reports': [], 'cases': []}


def load_json_report(base_path: str, doc_id: str) -> Dict:
    """加载报告JSON文件"""
    report_file = os.path.join(base_path, "index", "reports", f"{doc_id}.json")
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_json_case(base_path: str, case_id: str) -> Dict:
    """加载案例JSON文件"""
    case_file = os.path.join(base_path, "cases", f"{case_id}.json")
    if os.path.exists(case_file):
        with open(case_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def migrate_to_postgres(base_path: str):
    """将数据迁移到 PostgreSQL"""
    print("正在将数据迁移到 PostgreSQL...")

    from knowledge_base.db_connection import pg_cursor

    # 加载索引
    index = load_json_index(base_path)

    reports = index.get('reports', [])
    cases = index.get('cases', [])

    print(f"  ✓ 已加载 {len(reports)} 个报告和 {len(cases)} 个案例")

    # 迁移报告
    migrated_reports = 0
    for report_info in reports:
        doc_id = report_info.get('doc_id')
        report_data = load_json_report(base_path, doc_id)

        if not report_data:
            print(f"  ⚠️ 忽略不存在的报告 {doc_id}")
            continue

        try:
            with pg_cursor() as cursor:
                # 检查是否已存在
                cursor.execute("SELECT 1 FROM documents WHERE doc_id = %s", (doc_id,))
                if cursor.fetchone():
                    continue

                cursor.execute("""
                   INSERT INTO documents (doc_id, filename, report_type, address, area,
                                          case_count, create_time, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   """, (
                       doc_id,
                       report_info.get('source_file', ''),
                       report_info.get('report_type', ''),
                       report_info.get('address', ''),
                       report_info.get('area', 0),
                       report_info.get('case_count', 0),
                       report_info.get('create_time', None),
                       json.dumps(report_data, ensure_ascii=False),
                   ))
            migrated_reports += 1
        except Exception as e:
            print(f"  ✗ 迁移报告失败 {doc_id}: {e}")

    print(f"  ✓ 迁移了 {migrated_reports} 个报告")

    # 迁移案例
    migrated_cases = 0
    for case_info in cases:
        case_id = case_info.get('case_id')
        case_data = load_json_case(base_path, case_id)

        if not case_data:
            print(f"  ⚠️ 案例文件不存在: {case_id}")
            continue

        try:
            with pg_cursor() as cursor:
                # 检查是否已存在
                cursor.execute("SELECT 1 FROM cases WHERE case_id = %s", (case_id,))
                if cursor.fetchone():
                    continue

                cursor.execute("""
                   INSERT INTO cases (case_id, case_id_full, doc_id, report_type, address,
                                      district, street, area, price, usage, build_year,
                                      total_floor, current_floor, orientation, decoration,
                                      structure, case_data)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   """, (
                       case_id,
                       case_id,
                       case_info.get('from_doc', ''),
                       case_info.get('report_type', ''),
                       case_info.get('address', ''),
                       case_info.get('district', ''),
                       case_info.get('street', ''),
                       case_info.get('area', 0),
                       case_info.get('price', 0),
                       case_info.get('usage', ''),
                       case_info.get('build_year', 0),
                       case_info.get('total_floor', 0),
                       case_info.get('current_floor', 0),
                       case_info.get('orientation', ''),
                       case_info.get('decoration', ''),
                       case_info.get('structure', ''),
                       json.dumps(case_data, ensure_ascii=False),
                   ))
            migrated_cases += 1
        except Exception as e:
            print(f"  ✗ 迁移案例失败 {case_id}: {e}")

    print(f"  ✓ 迁移案例: {migrated_cases}/{len(cases)}")


def rebuild_vector_index():
    """重建向量索引"""
    print("正在重建向量索引...")

    from knowledge_base.kb_manager_db import KnowledgeBaseManager

    manager = KnowledgeBaseManager(enable_vector=True)
    manager.rebuild_vector_index()

    print("  ✓ 重建完成")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="数据迁移脚本")
    parser.add_argument("--source", default="./knowledge_base/storage",
                        help="源数据目录（JSON文件所在目录）")
    parser.add_argument("--skip-vector", action="store_true",
                        help="跳过向量索引重建")

    args = parser.parse_args()

    print("=" * 50)
    print("数据迁移")
    print("=" * 50)
    print(f"源目录: {args.source}")

    # 检查源目录
    if not os.path.exists(args.source):
        print(f"✗ 源目录不存在: {args.source}")
        return False

    # 迁移到 PostgreSQL
    try:
        migrate_to_postgres(args.source)
    except Exception as e:
        print(f"✗ PostgreSQL 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 重建向量索引
    if not args.skip_vector:
        try:
            rebuild_vector_index()
        except Exception as e:
            print(f"✗ 向量索引重建失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    print("=" * 50)
    print("✓ 数据迁移完成")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
