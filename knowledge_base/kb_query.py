"""
知识库查询
==========
提供检索和相似度匹配功能，为审查和生成提供支持

支持两种模式：
- 文件模式：通过 self.kb.index 访问内存索引
- 数据库模式：直接查询 PostgreSQL
"""

import os
import sys
import json
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import KB_CONFIG

# 检测是否使用数据库模式
USE_DATABASE = os.getenv('KB_USE_DATABASE', 'false').lower() == 'true'


class KnowledgeBaseQuery:
    """知识库查询器"""

    def __init__(self, kb_manager):
        """
        Args:
            kb_manager: KnowledgeBaseManager实例
        """
        self.kb = kb_manager
        self.config = KB_CONFIG
        # 检测是否为数据库版本（通过检查是否有index属性）
        self._use_db = not hasattr(kb_manager, 'index') or USE_DATABASE

    # ========================================================================
    # 内部方法：获取案例列表（兼容两种模式）
    # ========================================================================

    def _get_all_cases(self, report_type: str = None) -> List[Dict]:
        """获取所有案例（兼容文件/数据库模式）"""
        if self._use_db:
            return self._get_cases_from_db(report_type)
        else:
            return self._get_cases_from_index(report_type)

    def _get_cases_from_index(self, report_type: str = None) -> List[Dict]:
        """从内存索引获取案例"""
        cases = self.kb.index.get('cases', [])
        if report_type:
            cases = [c for c in cases if c.get('report_type') == report_type]
        return cases

    def _get_cases_from_db(self, report_type: str = None) -> List[Dict]:
        """从数据库获取案例"""
        try:
            from knowledge_base.db_connection import pg_cursor

            with pg_cursor(commit=False) as cursor:
                if report_type:
                    cursor.execute("""
                        SELECT case_id, doc_id, report_type, address, district, street,
                               area, price, usage, build_year, total_floor, current_floor,
                               orientation, decoration, structure
                        FROM cases 
                        WHERE report_type = %s
                    """, (report_type,))
                else:
                    cursor.execute("""
                        SELECT case_id, doc_id, report_type, address, district, street,
                               area, price, usage, build_year, total_floor, current_floor,
                               orientation, decoration, structure
                        FROM cases
                    """)

                columns = ['case_id', 'from_doc', 'report_type', 'address', 'district',
                          'street', 'area', 'price', 'usage', 'build_year', 'total_floor',
                          'current_floor', 'orientation', 'decoration', 'structure']
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            print(f"⚠️ 从数据库获取案例失败: {e}")
            return []

    # ========================================================================
    # 基础检索
    # ========================================================================

    def search_cases(self,
                     keyword: str = None,
                     report_type: str = None,
                     min_price: float = None,
                     max_price: float = None,
                     min_area: float = None,
                     max_area: float = None,
                     district: str = None,
                     usage: str = None,
                     min_floor: int = None,
                     max_floor: int = None,
                     min_build_year: int = None,
                     max_build_year: int = None,
                     limit: int = 50) -> List[Dict]:
        """
        搜索案例

        Args:
            keyword: 地址关键词
            report_type: 报告类型
            min_price/max_price: 价格范围
            min_area/max_area: 面积范围
            district: 区域
            usage: 用途
            min_floor/max_floor: 楼层范围
            min_build_year/max_build_year: 建成年份范围
            limit: 最大返回数量

        Returns:
            案例列表
        """
        # 数据库模式：使用SQL过滤
        if self._use_db:
            return self._search_cases_db(
                keyword=keyword, report_type=report_type,
                min_price=min_price, max_price=max_price,
                min_area=min_area, max_area=max_area,
                district=district, usage=usage,
                min_floor=min_floor, max_floor=max_floor,
                min_build_year=min_build_year, max_build_year=max_build_year,
                limit=limit
            )

        # 文件模式：内存过滤
        results = []

        for item in self.kb.index.get('cases', []):
            # 类型过滤
            if report_type and item.get('report_type') != report_type:
                continue

            # 关键词过滤
            if keyword and keyword not in item.get('address', ''):
                continue

            # 区域过滤
            if district and district not in item.get('district', ''):
                continue

            # 用途过滤
            if usage and item.get('usage') != usage:
                continue

            # 价格过滤
            price = item.get('price', 0)
            if min_price and price < min_price:
                continue
            if max_price and price > max_price:
                continue

            # 面积过滤
            area = item.get('area', 0)
            if min_area and area < min_area:
                continue
            if max_area and area > max_area:
                continue

            # 楼层过滤
            floor = item.get('current_floor', 0)
            if min_floor and floor < min_floor:
                continue
            if max_floor and floor > max_floor:
                continue

            # 建成年份过滤
            build_year = item.get('build_year', 0)
            if min_build_year and build_year and build_year < min_build_year:
                continue
            if max_build_year and build_year and build_year > max_build_year:
                continue

            # 加载完整数据
            case_data = self.kb.get_case(item['case_id'])
            if case_data:
                results.append(case_data)

            if len(results) >= limit:
                break

        return results

    def _search_cases_db(self, **kwargs) -> List[Dict]:
        """数据库模式的案例搜索"""
        try:
            from knowledge_base.db_connection import pg_cursor

            conditions = []
            params = []

            if kwargs.get('report_type'):
                conditions.append("report_type = %s")
                params.append(kwargs['report_type'])
            if kwargs.get('keyword'):
                conditions.append("address LIKE %s")
                params.append(f"%{kwargs['keyword']}%")
            if kwargs.get('district'):
                conditions.append("district LIKE %s")
                params.append(f"%{kwargs['district']}%")
            if kwargs.get('usage'):
                conditions.append("usage = %s")
                params.append(kwargs['usage'])
            if kwargs.get('min_price') is not None:
                conditions.append("price >= %s")
                params.append(kwargs['min_price'])
            if kwargs.get('max_price') is not None:
                conditions.append("price <= %s")
                params.append(kwargs['max_price'])
            if kwargs.get('min_area') is not None:
                conditions.append("area >= %s")
                params.append(kwargs['min_area'])
            if kwargs.get('max_area') is not None:
                conditions.append("area <= %s")
                params.append(kwargs['max_area'])
            if kwargs.get('min_floor') is not None:
                conditions.append("current_floor >= %s")
                params.append(kwargs['min_floor'])
            if kwargs.get('max_floor') is not None:
                conditions.append("current_floor <= %s")
                params.append(kwargs['max_floor'])
            if kwargs.get('min_build_year') is not None:
                conditions.append("build_year >= %s")
                params.append(kwargs['min_build_year'])
            if kwargs.get('max_build_year') is not None:
                conditions.append("build_year <= %s")
                params.append(kwargs['max_build_year'])

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            limit = kwargs.get('limit', 50)
            params.append(limit)

            with pg_cursor(commit=False) as cursor:
                cursor.execute(f"""
                    SELECT case_id, doc_id, report_type, address, district, street,
                           area, price, usage, build_year, total_floor, current_floor,
                           orientation, decoration, structure, case_data
                    FROM cases 
                    WHERE {where_clause}
                    ORDER BY create_time DESC
                    LIMIT %s
                """, params)

                results = []
                for row in cursor.fetchall():
                    case_data = row[15]
                    if isinstance(case_data, str):
                        case_data = json.loads(case_data)

                    results.append({
                        'case_id': row[0],
                        'from_doc': row[1],
                        'report_type': row[2],
                        'address': row[3],
                        'district': row[4],
                        'street': row[5],
                        'area': row[6],
                        'price': row[7],
                        'usage': row[8],
                        'build_year': row[9],
                        'total_floor': row[10],
                        'current_floor': row[11],
                        'orientation': row[12],
                        'decoration': row[13],
                        'structure': row[14],
                        **(case_data or {}),
                    })

                return results
        except Exception as e:
            print(f"⚠️ 数据库搜索案例失败: {e}")
            return []

    def search_reports(self,
                       keyword: str = None,
                       report_type: str = None,
                       limit: int = 50) -> List[Dict]:
        """搜索报告"""
        if self._use_db:
            return self._search_reports_db(keyword, report_type, limit)

        results = []

        for item in self.kb.index.get('reports', []):
            if report_type and item.get('report_type') != report_type:
                continue

            if keyword and keyword not in item.get('address', ''):
                continue

            report_data = self.kb.get_report(item['doc_id'])
            if report_data:
                results.append(report_data)

            if len(results) >= limit:
                break

        return results

    def _search_reports_db(self, keyword: str = None, report_type: str = None, limit: int = 50) -> List[Dict]:
        """数据库模式的报告搜索"""
        try:
            from knowledge_base.db_connection import pg_cursor

            conditions = []
            params = []

            if report_type:
                conditions.append("report_type = %s")
                params.append(report_type)
            if keyword:
                conditions.append("address LIKE %s")
                params.append(f"%{keyword}%")

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)

            with pg_cursor(commit=False) as cursor:
                cursor.execute(f"""
                    SELECT doc_id, filename, report_type, address, area, case_count, metadata
                    FROM documents 
                    WHERE {where_clause}
                    ORDER BY create_time DESC
                    LIMIT %s
                """, params)

                results = []
                for row in cursor.fetchall():
                    metadata = row[6]
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)

                    results.append({
                        'doc_id': row[0],
                        'source_file': row[1],
                        'report_type': row[2],
                        'address': row[3],
                        'area': row[4],
                        'case_count': row[5],
                        **(metadata or {}),
                    })

                return results
        except Exception as e:
            print(f"⚠️ 数据库搜索报告失败: {e}")
            return []

    # ========================================================================
    # 相似案例查找（为生成和审查提供支持）
    # ========================================================================

    def find_similar_cases(self,
                           address: str = None,
                           area: float = None,
                           price: float = None,
                           district: str = None,
                           usage: str = None,
                           floor: int = None,
                           build_year: int = None,
                           report_type: str = None,
                           top_k: int = 5) -> List[Tuple[Dict, float]]:
        """
        查找相似案例

        Args:
            address: 地址
            area: 面积
            price: 价格（用于对比）
            district: 区域
            usage: 用途
            floor: 楼层
            build_year: 建成年份
            report_type: 报告类型
            top_k: 返回数量

        Returns:
            [(案例, 相似度分数), ...]
        """
        # 获取所有案例
        all_cases = self._get_all_cases(report_type)

        # 计算相似度
        scored = []
        for item in all_cases:
            score = self._calculate_similarity(
                item, address, area, price, district, usage, floor, build_year
            )
            if score > 0:
                # 获取完整案例数据
                case_data = self.kb.get_case(item['case_id'])
                if case_data:
                    scored.append((case_data, score))

        # 排序返回
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _calculate_similarity(self, item: Dict, address: str, area: float,
                              price: float, district: str, usage: str,
                              floor: int, build_year: int) -> float:
        """计算相似度分数"""
        score = 0.0

        # 1. 区域匹配（权重0.25）
        if district:
            item_district = item.get('district', '')
            if item_district and district in item_district:
                score += 0.25

        # 2. 用途匹配（权重0.15）
        if usage:
            item_usage = item.get('usage', '')
            if item_usage and usage == item_usage:
                score += 0.15

        # 3. 面积相似度（权重0.20）
        if area and area > 0:
            item_area = item.get('area', 0)
            if item_area > 0:
                ratio = min(area, item_area) / max(area, item_area)
                if ratio > 0.5:
                    score += ratio * 0.20

        # 4. 价格相似度（权重0.15）
        if price and price > 0:
            item_price = item.get('price', 0)
            if item_price > 0:
                ratio = min(price, item_price) / max(price, item_price)
                if ratio > 0.5:
                    score += ratio * 0.15

        # 5. 楼层相似度（权重0.10）
        if floor and floor > 0:
            item_floor = item.get('current_floor', 0)
            if item_floor > 0:
                diff = abs(floor - item_floor)
                if diff <= 3:
                    score += (1 - diff / 10) * 0.10

        # 6. 建成年份相似度（权重0.10）
        if build_year and build_year > 0:
            item_year = item.get('build_year', 0)
            if item_year > 0:
                diff = abs(build_year - item_year)
                if diff <= 10:
                    score += (1 - diff / 20) * 0.10

        # 7. 地址关键词匹配（权重0.05）
        if address:
            item_address = item.get('address', '')
            if item_address:
                # 简单关键词匹配
                matches = sum(1 for c in address if c in item_address and len(c) > 1)
                if matches > 0:
                    score += min(matches * 0.01, 0.05)

        return score

    # ========================================================================
    # 统计分析（为生成提供参考数据）
    # ========================================================================

    def get_price_range(self, report_type: str = None) -> Dict:
        """获取价格范围统计"""
        cases = self._get_all_cases(report_type)

        prices = []
        for item in cases:
            price = item.get('price', 0)
            if price > 0:
                prices.append(price)

        if not prices:
            return {'min': 0, 'max': 0, 'avg': 0, 'count': 0}

        return {
            'min': min(prices),
            'max': max(prices),
            'avg': sum(prices) / len(prices),
            'count': len(prices),
        }

    def get_area_range(self, report_type: str = None) -> Dict:
        """获取面积范围统计"""
        cases = self._get_all_cases(report_type)

        areas = []
        for item in cases:
            area = item.get('area', 0)
            if area > 0:
                areas.append(area)

        if not areas:
            return {'min': 0, 'max': 0, 'avg': 0, 'count': 0}

        return {
            'min': min(areas),
            'max': max(areas),
            'avg': sum(areas) / len(areas),
            'count': len(areas),
        }

    def get_correction_stats(self, report_type: str = None) -> Dict:
        """获取修正系数统计"""
        cases = self._get_all_cases(report_type)

        stats = {
            'transaction': [],
            'market': [],
            'location': [],
            'physical': [],
            'rights': [],
        }

        for item in cases:
            case_data = self.kb.get_case(item['case_id'])
            if not case_data:
                continue

            for key, field in [
                ('transaction', 'transaction_correction'),
                ('market', 'market_correction'),
                ('location', 'location_correction'),
                ('physical', 'physical_correction'),
                ('rights', 'rights_correction'),
            ]:
                if field in case_data:
                    val = case_data[field]
                    if isinstance(val, dict):
                        val = val.get('value')
                    if val:
                        stats[key].append(val)

        # 计算统计值
        result = {}
        for key, values in stats.items():
            if values:
                result[key] = {
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values),
                    'count': len(values),
                }
            else:
                result[key] = {'min': 0, 'max': 0, 'avg': 0, 'count': 0}

        return result

    # ========================================================================
    # 向量检索（如果启用）
    # ========================================================================

    def vector_search(self, query_text: str, top_k: int = 10) -> List[Tuple[Dict, float]]:
        """
        向量相似搜索

        Args:
            query_text: 查询文本
            top_k: 返回数量

        Returns:
            [(案例, 相似度), ...]
        """
        if not hasattr(self.kb, 'vector_store') or self.kb.vector_store is None:
            return []

        try:
            results = self.kb.vector_store.search(query_text, top_k)

            # 加载完整案例数据
            enriched = []
            for case_id, score in results:
                case_data = self.kb.get_case(case_id)
                if case_data:
                    enriched.append((case_data, score))

            return enriched
        except Exception as e:
            print(f"⚠️ 向量检索失败: {e}")
            return []

    def hybrid_search(self,
                      query_text: str = None,
                      district: str = None,
                      usage: str = None,
                      report_type: str = None,
                      top_k: int = 10) -> List[Dict]:
        """
        混合检索（向量 + 条件过滤）

        Args:
            query_text: 查询文本（用于向量检索）
            district: 区域过滤
            usage: 用途过滤
            report_type: 类型过滤
            top_k: 返回数量

        Returns:
            案例列表
        """
        # 先用向量检索
        if query_text and hasattr(self.kb, 'vector_store') and self.kb.vector_store:
            vector_results = self.vector_search(query_text, top_k * 2)
            candidates = [case for case, _ in vector_results]
        else:
            # 没有向量检索，用普通搜索
            candidates = self._get_all_cases(report_type)[:top_k * 2]

        # 再用条件过滤
        filtered = []
        for case in candidates:
            if district and district not in case.get('district', ''):
                continue
            if usage and case.get('usage') != usage:
                continue
            if report_type and case.get('report_type') != report_type:
                continue
            filtered.append(case)

        return filtered[:top_k]