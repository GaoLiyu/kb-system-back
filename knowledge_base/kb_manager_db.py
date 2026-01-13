"""
知识库管理（数据库版）
=====================
使用 PostgreSQL 存储元数据
"""

import os
import sys
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import generate_id, get_timestamp
from .db_connection import pg_cursor, test_pg_connection


def result_to_dict(result) -> Dict:
    """将提取结果转为字典"""
    def loc_val_to_dict(lv):
        if lv is None:
            return {'value': None, 'position': {}, 'raw_text': ''}
        return {
            'value': lv.value,
            'position': {
                'table_index': lv.position.table_index,
                'row_index': lv.position.row_index,
                'col_index': lv.position.col_index,
            },
            'raw_text': lv.raw_text
        }

    def factor_to_dict(f):
        return {
            'name': f.name,
            'description': f.description,
            'level': f.level,
            'index': f.index,
        }

    def case_to_dict(case):
        data = {
            'case_id': case.case_id,
            'address': loc_val_to_dict(case.address),
        }

        # 通用字段
        for field in ['building_area', 'transaction_price', 'rental_price',
                      'transaction_correction', 'market_correction', 'location_correction',
                      'physical_correction', 'rights_correction', 'adjusted_price',
                      'structure_factor', 'floor_factor', 'orientation_factor',
                      'age_factor', 'physical_composite', 'composite_result',
                      'vs_result', 'decoration_price', 'final_price']:
            if hasattr(case, field):
                val = getattr(case, field)
                if hasattr(val, 'value'):
                    data[field] = loc_val_to_dict(val)

        # 字符串字段
        for field in ['transaction_date', 'data_source', 'location', 'usage',
                      'p1_transaction', 'p2_date', 'p3_physical', 'p4_location']:
            if hasattr(case, field):
                data[field] = getattr(case, field)

        # 因素
        for factor_type in ['location_factors', 'physical_factors', 'rights_factors']:
            if hasattr(case, factor_type):
                factors = getattr(case, factor_type)
                if factors:
                    data[factor_type] = {k: factor_to_dict(v) for k, v in factors.items()}

        return data

    # 主体
    data = {
        'source_file': result.source_file,
        'subject': {
            'address': loc_val_to_dict(result.subject.address),
            'building_area': loc_val_to_dict(result.subject.building_area),
        },
        'cases': [case_to_dict(c) for c in result.cases],
    }

    # 估价对象额外字段
    subject = result.subject
    for field in ['unit_price', 'total_price']:
        if hasattr(subject, field):
            data['subject'][field] = loc_val_to_dict(getattr(subject, field))

    for field in ['structure', 'floor', 'usage', 'cert_no', 'owner', 'location_code']:
        if hasattr(subject, field):
            data['subject'][field] = getattr(subject, field)

    # 最终结果
    if hasattr(result, 'final_unit_price'):
        data['final_unit_price'] = loc_val_to_dict(result.final_unit_price)
    if hasattr(result, 'final_total_price'):
        data['final_total_price'] = loc_val_to_dict(result.final_total_price)
    if hasattr(result, 'floor_factor'):
        data['floor_factor'] = result.floor_factor

    return data


class KnowledgeBaseManager:
    """知识库管理器（数据库版）"""

    def __init__(self, base_path: str = "./knowledge_base/storage", enable_vector: bool = True):
        self.base_path = base_path
        self.enable_vector = enable_vector

        # 向量存储（延迟初始化）
        self._vector_store = None

        # 测试数据库连接
        if not test_pg_connection():
            raise RuntimeError("PostgreSQL 连接失败，请检查数据库配置")

    @property
    def vector_store(self):
        """获取向量存储（延迟加载）"""
        if not self.enable_vector:
            return None

        if self._vector_store is None:
            try:
                from .vector_store_milvus import MilvusVectorStore
                self._vector_store = MilvusVectorStore()
            except ImportError as e:
                print(f"⚠️ 向量存储不可用（缺少依赖）: {e}")
                self.enable_vector = False
                return None
            except Exception as e:
                print(f"⚠️ 向量存储初始化失败: {e}")
                self.enable_vector = False
                return None
        return self._vector_store

    def rebuild_vector_index(self):
        """重建向量索引"""
        if not self.enable_vector or self.vector_store is None:
            print("⚠️ 向量存储未启用")
            return

        # 加载所有案例
        cases = []
        for case_item in self.list_cases():
            case_data = self.get_case(case_item['case_id'])
            if case_data:
                cases.append(case_data)

        # 重建索引
        self.vector_store.rebuild(cases)

    def ensure_vector_index(self):
        """确保向量索引是最新的"""
        if not self.enable_vector or self.vector_store is None:
            return

        if self.vector_store.is_dirty:
            self.rebuild_vector_index()

    def add_report(self, result, report_type: str) -> str:
        """
        添加报告到知识库

        Args:
            result: 提取结果
            report_type: 报告类型

        Returns:
            doc_id
        """
        doc_id = generate_id("doc")
        data = result_to_dict(result)
        subject = result.subject

        # 插入文档
        with pg_cursor() as cursor:
            cursor.execute("""
                INSERT INTO documents (doc_id, filename, file_path, file_type, report_type, 
                                       address, area, case_count, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                doc_id,
                result.source_file,
                None,
                'word',
                report_type,
                subject.address.value or '',
                subject.building_area.value or 0,
                len(result.cases),
                json.dumps(data, ensure_ascii=False),
            ))

        # 插入案例
        for case in result.cases:
            case_id = f"{doc_id}_case_{case.case_id}"
            case_data = result_to_dict(result)['cases'][result.cases.index(case)]
            case_data['case_id_full'] = case_id
            case_data['from_doc'] = doc_id
            case_data['report_type'] = report_type

            # 获取价格
            price = 0
            if hasattr(case, 'transaction_price') and case.transaction_price.value:
                price = case.transaction_price.value
            elif hasattr(case, 'rental_price') and case.rental_price.value:
                price = case.rental_price.value
            elif hasattr(case, 'final_price') and case.final_price.value:
                price = case.final_price.value

            # 获取面积
            area = case.building_area.value if case.building_area.value else 0

            with pg_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO cases (case_id, case_id_full, doc_id, report_type, address,
                                       district, street, area, price, usage, build_year,
                                       total_floor, current_floor, orientation, decoration,
                                       structure, case_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    case_id,
                    case_id,
                    doc_id,
                    report_type,
                    case.address.value or '',
                    getattr(case, 'district', ''),
                    getattr(case, 'street', ''),
                    area,
                    price,
                    getattr(case, 'usage', ''),
                    getattr(case, 'build_year', 0),
                    getattr(case, 'total_floor', 0),
                    getattr(case, 'current_floor', 0),
                    getattr(case, 'orientation', ''),
                    getattr(case, 'decoration', ''),
                    getattr(case, 'structure', ''),
                    json.dumps(case_data, ensure_ascii=False),
                ))

        # 添加到向量索引
        if self.enable_vector and self._vector_store is not None:
            self._vector_store.mark_dirty()

        return doc_id

    def get_report(self, doc_id: str) -> Optional[Dict]:
        """获取报告"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT metadata FROM documents WHERE doc_id = %s
            """, (doc_id,))
            row = cursor.fetchone()
            if row:
                data = row[0]
                if isinstance(data, str):
                    return json.loads(data)
                return data
        return None

    def get_case(self, case_id: str) -> Optional[Dict]:
        """获取单个案例详情"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                           SELECT case_id,
                                  doc_id,
                                  report_type,
                                  address,
                                  district,
                                  street,
                                  area,
                                  price, usage, build_year, total_floor, current_floor, orientation, decoration, structure, case_data, create_time
                           FROM cases
                           WHERE case_id = %s
                           """, (case_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "case_id": row[0],
                "doc_id": row[1],
                "report_type": row[2],
                "address": row[3],
                "district": row[4],
                "street": row[5],
                "area": row[6],
                "price": row[7],
                "usage": row[8],
                "build_year": row[9],
                "total_floor": row[10],
                "current_floor": row[11],
                "orientation": row[12],
                "decoration": row[13],
                "structure": row[14],
                "case_data": row[15],
                "create_time": row[16].isoformat() if row[16] else None,
            }

    def list_reports(self, report_type: str = None) -> List[Dict]:
        """列出报告"""
        with pg_cursor(commit=False) as cursor:
            if report_type:
                cursor.execute("""
                    SELECT doc_id, filename, report_type, address, area, case_count, create_time
                    FROM documents WHERE report_type = %s
                    ORDER BY create_time DESC
                """, (report_type,))
            else:
                cursor.execute("""
                    SELECT doc_id, filename, report_type, address, area, case_count, create_time
                    FROM documents ORDER BY create_time DESC
                """)

            columns = ['doc_id', 'source_file', 'report_type', 'address', 'area', 'case_count', 'create_time']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_cases(self, report_type: str = None) -> List[Dict]:
        """列出案例"""
        with pg_cursor(commit=False) as cursor:
            if report_type:
                cursor.execute("""
                    SELECT case_id, doc_id, report_type, address, area, price, district, usage
                    FROM cases WHERE report_type = %s
                    ORDER BY create_time DESC
                """, (report_type,))
            else:
                cursor.execute("""
                    SELECT case_id, doc_id, report_type, address, area, price, district, usage
                    FROM cases ORDER BY create_time DESC
                """)

            columns = ['case_id', 'from_doc', 'report_type', 'address', 'area', 'price', 'district', 'usage']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def delete_report(self, doc_id: str) -> bool:
        """删除报告及其案例"""
        with pg_cursor() as cursor:
            # 级联删除会自动删除关联的案例
            cursor.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))

        # 标记向量索引需要重建
        if self.enable_vector and self._vector_store is not None:
            self._vector_store.mark_dirty()

        return True

    def stats(self) -> Dict:
        """统计信息"""
        with pg_cursor(commit=False) as cursor:
            # 报告总数
            cursor.execute("SELECT COUNT(*) FROM documents")
            total_reports = cursor.fetchone()[0]

            # 案例总数
            cursor.execute("SELECT COUNT(*) FROM cases")
            total_cases = cursor.fetchone()[0]

            # 按类型统计
            cursor.execute("""
                SELECT report_type, COUNT(*) FROM documents 
                GROUP BY report_type
            """)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # 向量索引状态
        vector_stats = {}
        if self.enable_vector:
            try:
                from .vector_store_milvus import MilvusVectorStore
                if self._vector_store is None:
                    self._vector_store = MilvusVectorStore()
                vector_stats = self._vector_store.get_stats()
            except Exception as e:
                vector_stats = {'error': str(e)}

        return {
            'total_reports': total_reports,
            'total_cases': total_cases,
            'by_type': by_type,
            'vector_index': vector_stats,
        }

    def clear(self):
        """清空知识库"""
        with pg_cursor() as cursor:
            cursor.execute("DELETE FROM cases")
            cursor.execute("DELETE FROM documents")

        # 清空向量索引
        if self.enable_vector and self._vector_store is not None:
            self._vector_store.clear()

    def search_cases(self,
                     report_type: str = None,
                     district: str = None,
                     usage: str = None,
                     min_area: float = None,
                     max_area: float = None,
                     min_price: float = None,
                     max_price: float = None,
                     limit: int = 100) -> List[Dict]:
        """
        搜索案例（字段搜索）
        """
        conditions = []
        params = []

        if report_type:
            conditions.append("report_type = %s")
            params.append(report_type)
        if district:
            conditions.append("district LIKE %s")
            params.append(f"%{district}%")
        if usage:
            conditions.append("usage = %s")
            params.append(usage)
        if min_area is not None:
            conditions.append("area >= %s")
            params.append(min_area)
        if max_area is not None:
            conditions.append("area <= %s")
            params.append(max_area)
        if min_price is not None:
            conditions.append("price >= %s")
            params.append(min_price)
        if max_price is not None:
            conditions.append("price <= %s")
            params.append(max_price)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        with pg_cursor(commit=False) as cursor:
            cursor.execute(f"""
                SELECT case_id, doc_id, report_type, address, area, price, 
                       district, usage, case_data
                FROM cases 
                WHERE {where_clause}
                ORDER BY create_time DESC
                LIMIT %s
            """, params)

            results = []
            for row in cursor.fetchall():
                case_data = row[8]
                if isinstance(case_data, str):
                    case_data = json.loads(case_data)

                results.append({
                    'case_id': row[0],
                    'from_doc': row[1],
                    'report_type': row[2],
                    'address': row[3],
                    'area': row[4],
                    'price': row[5],
                    'district': row[6],
                    'usage': row[7],
                    **case_data,
                })

            return results
