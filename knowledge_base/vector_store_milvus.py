"""
Milvus 向量存储
===============
基于 Milvus 的向量检索
"""

import os
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .db_connection import connect_milvus, get_milvus_collection, MILVUS_CONFIG


@dataclass
class MilvusVectorStoreConfig:
    """向量存储配置"""
    model_path: str = os.getenv("EMBEDDING_MODEL_PATH", "/data/models/bge-large-zh-v1.5")
    dimension: int = 1024       # BGE-large维度
    batch_size: int = 32        # 编码批次大小


class MilvusVectorStore:
    """
    Milvus 向量存储

    功能：
    - 案例向量化存储
    - 相似案例检索
    - 批量重建索引
    """

    def __init__(self, config: MilvusVectorStoreConfig = None):
        """初始化向量存储"""
        self.config = config or MilvusVectorStoreConfig()

        # 连接 Milvus
        connect_milvus()

        # 延迟加载
        self._model = None
        self._dirty = False

    @property
    def model(self):
        """延迟加载embedding模型"""
        if self._model is None:
            print(f"📦 加载Embedding模型: {self.config.model_path}")
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.config.model_path,
                    device="cpu"
                )
                print(f"   ✓ 模型加载完成")
            except Exception as e:
                print(f"   ✗ 模型加载失败: {e}")
                raise
        return self._model

    @property
    def collection(self):
        """获取 Milvus Collection"""
        return get_milvus_collection()

    @property
    def is_dirty(self):
        """索引是否需要重建"""
        return self._dirty

    def mark_dirty(self):
        """标记索引需要重建"""
        self._dirty = True

    def build_case_text(self, case_data: Dict) -> str:
        """构建案例的向量化文本"""
        parts = []

        # 基础信息
        address = case_data.get('address', {})
        if isinstance(address, dict):
            address = address.get('value', '')
        parts.append(f"地址：{address}")

        # 区域信息
        district = case_data.get('district', '')
        if district:
            parts.append(f"区域：{district}")

        street = case_data.get('street', '')
        if street:
            parts.append(f"街道：{street}")

        # 用途
        usage = case_data.get('usage', '')
        if usage:
            parts.append(f"用途：{usage}")

        # 结构
        structure = case_data.get('structure', '')
        if structure:
            parts.append(f"结构：{structure}")

        # 面积
        area = case_data.get('building_area', {})
        if isinstance(area, dict):
            area = area.get('value', 0)
        if area:
            parts.append(f"建筑面积：{area}平方米")

        # 楼层
        floor = case_data.get('current_floor', 0)
        total_floor = case_data.get('total_floor', 0)
        if floor and total_floor:
            parts.append(f"楼层：{floor}/{total_floor}层")
        elif floor:
            parts.append(f"楼层：{floor}层")

        # 建成年份
        build_year = case_data.get('build_year', 0)
        if build_year:
            parts.append(f"建成年份：{build_year}年")

        # 朝向
        orientation = case_data.get('orientation', '')
        if orientation:
            parts.append(f"朝向：{orientation}")

        # 装修
        decoration = case_data.get('decoration', '')
        if decoration:
            parts.append(f"装修：{decoration}")

        # 因素描述
        for factor_type in ['location_factors', 'physical_factors', 'rights_factors']:
            factors = case_data.get(factor_type, {})
            if isinstance(factors, dict):
                for factor_name, factor_data in factors.items():
                    if isinstance(factor_data, dict):
                        desc = factor_data.get('description', '')
                        if desc and len(desc) > 2:
                            parts.append(desc)

        return " ".join(parts)

    def encode(self, texts: List[str]) -> np.ndarray:
        """文本编码为向量"""
        if not texts:
            return np.array([])

        vectors = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            show_progress_bar=len(texts) > 10,
            normalize_embeddings=True
        )
        return vectors

    def encode_query(self, query: str) -> np.ndarray:
        """编码查询文本（添加BGE查询前缀）"""
        query_with_prefix = f"为这个句子生成表示以用于检索相关文章：{query}"
        vector = self.model.encode(
            [query_with_prefix],
            normalize_embeddings=True
        )
        return vector

    def rebuild(self, cases: List[Dict]):
        """重建向量索引"""
        if not cases:
            print("⚠️ 没有案例数据，跳过向量索引构建")
            self._dirty = False
            return

        print(f"🔨 重建向量索引: {len(cases)}个案例")

        # 清空现有数据
        self.clear()

        # 构建数据
        case_ids = []
        doc_ids = []
        report_types = []
        texts = []

        for case in cases:
            case_id = case.get('case_id_full') or case.get('case_id')
            if not case_id:
                continue

            text = self.build_case_text(case)
            if text.strip():
                case_ids.append(case_id)
                doc_ids.append(case.get('from_doc', ''))
                report_types.append(case.get('report_type', ''))
                texts.append(text)

        if not texts:
            print("⚠️ 没有有效文本，跳过向量索引构建")
            self._dirty = False
            return

        # 编码
        print(f"   编码 {len(texts)} 条文本...")
        vectors = self.encode(texts)

        # 插入到 Milvus
        print(f"   插入到 Milvus...")
        collection = self.collection

        # 分批插入
        batch_size = 1000
        for i in range(0, len(case_ids), batch_size):
            end = min(i + batch_size, len(case_ids))
            collection.insert([
                case_ids[i:end],
                doc_ids[i:end],
                report_types[i:end],
                vectors[i:end].tolist(),
            ])

        # 刷新
        collection.flush()

        self._dirty = False
        print(f"   ✓ 向量索引构建完成: {len(case_ids)}条向量")

    def add(self, case_data: Dict):
        """添加单个案例到向量索引"""
        case_id = case_data.get('case_id_full') or case_data.get('case_id')
        if not case_id:
            return

        text = self.build_case_text(case_data)
        if not text.strip():
            return

        vector = self.encode([text])

        collection = self.collection
        collection.insert([
            [case_id],
            [case_data.get('from_doc', '')],
            [case_data.get('report_type', '')],
            vector.tolist(),
        ])
        collection.flush()

    def delete(self, case_ids: List[str]):
        """删除案例向量"""
        if not case_ids:
            return

        collection = self.collection
        expr = f"case_id in {case_ids}"
        collection.delete(expr)
        collection.flush()

    def search(self,
               query: str,
               top_k: int = 20,
               report_type: str = None) -> List[Tuple[str, float]]:
        """向量检索"""
        collection = self.collection

        # 确保 collection 已加载
        collection.load()

        # 编码查询
        query_vector = self.encode_query(query)

        # 搜索参数
        search_params = {
            "metric_type": "IP",
            "params": {"nprobe": 10},
        }

        # 过滤条件
        expr = None
        if report_type:
            expr = f'report_type == "{report_type}"'

        # 搜索
        results = collection.search(
            data=query_vector.tolist(),
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["case_id"],
        )

        # 组装结果
        output = []
        for hits in results:
            for hit in hits:
                output.append((hit.entity.get('case_id'), hit.score))

        return output

    def search_by_case(self,
                       case_data: Dict,
                       top_k: int = 10,
                       exclude_self: bool = True) -> List[Tuple[str, float]]:
        """根据案例查找相似案例"""
        text = self.build_case_text(case_data)
        if not text.strip():
            return []

        # 搜索更多以便排除自己
        results = self.search(text, top_k=top_k + 5)

        # 排除自己
        if exclude_self:
            self_id = case_data.get('case_id_full') or case_data.get('case_id')
            results = [(cid, score) for cid, score in results if cid != self_id]

        return results[:top_k]

    def clear(self):
        """清空向量索引"""
        from pymilvus import utility

        collection_name = MILVUS_CONFIG['collection']
        if utility.has_collection(collection_name):
            utility.drop_collection(collection_name)

        # 重新创建
        self._create_collection()

    def _create_collection(self):
        """创建 Collection"""
        from pymilvus import Collection, FieldSchema, CollectionSchema, DataType

        collection_name = MILVUS_CONFIG['collection']

        fields = [
            FieldSchema(name="case_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="report_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.config.dimension),
        ]

        schema = CollectionSchema(fields=fields, description="案例向量库")
        collection = Collection(name=collection_name, schema=schema)

        # 创建索引
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "IP",
            "params": {"nlist": 1024}
        }
        collection.create_index(field_name="embedding", index_params=index_params)

        return collection

    def get_stats(self) -> Dict:
        """获取统计信息"""
        collection = self.collection
        collection.flush()

        return {
            'total_vectors': collection.num_entities,
            'dimension': self.config.dimension,
            'is_dirty': self._dirty,
            'collection': MILVUS_CONFIG['collection'],
        }


# ============================================================================
# 便捷函数
# ============================================================================

_vector_store_instance = None


def get_milvus_vector_store() -> MilvusVectorStore:
    """获取向量存储单例"""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = MilvusVectorStore()
    return _vector_store_instance


def reset_milvus_vector_store():
    """重置向量存储单例"""
    global _vector_store_instance
    _vector_store_instance = None
