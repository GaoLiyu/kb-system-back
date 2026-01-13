"""
FAISS向量存储
=============
基于FAISS的向量检索，使用BGE-large-zh embedding
"""

import os
import json
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class VectorStoreConfig:
    """向量存储配置"""
    model_path: str = "/data/models/bge-large-zh-v1.5"
    index_type: str = "FlatIP"  # 内积，配合归一化等价于余弦相似度
    dimension: int = 1024       # BGE-large维度
    batch_size: int = 32        # 编码批次大小


class VectorStore:
    """
    FAISS向量存储
    
    功能：
    - 案例向量化存储
    - 相似案例检索
    - 批量重建索引
    """
    
    def __init__(self, storage_path: str, config: VectorStoreConfig = None):
        """
        初始化向量存储
        
        Args:
            storage_path: 存储路径
            config: 配置
        """
        self.storage_path = storage_path
        self.config = config or VectorStoreConfig()
        
        # 路径
        self.vectors_path = os.path.join(storage_path, "vectors")
        self.index_file = os.path.join(self.vectors_path, "cases.index")
        self.ids_file = os.path.join(self.vectors_path, "cases_ids.json")
        
        # 确保目录存在
        os.makedirs(self.vectors_path, exist_ok=True)
        
        # 延迟加载
        self._model = None
        self._index = None
        self._case_ids = []  # FAISS索引位置 -> case_id映射
        self._dirty = True   # 是否需要重建
        
        # 尝试加载已有索引
        self._load_index()
    
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
    def index(self):
        """获取FAISS索引"""
        return self._index
    
    @property
    def is_dirty(self):
        """索引是否需要重建"""
        return self._dirty
    
    def mark_dirty(self):
        """标记索引需要重建"""
        self._dirty = True
    
    def _load_index(self):
        """加载已有索引"""
        if os.path.exists(self.index_file) and os.path.exists(self.ids_file):
            try:
                import faiss
                self._index = faiss.read_index(self.index_file)
                with open(self.ids_file, 'r', encoding='utf-8') as f:
                    self._case_ids = json.load(f)
                self._dirty = False
                print(f"📂 加载向量索引: {len(self._case_ids)}条")
            except Exception as e:
                print(f"⚠️ 加载向量索引失败: {e}")
                self._index = None
                self._case_ids = []
                self._dirty = True
    
    def _save_index(self):
        """保存索引"""
        if self._index is not None:
            import faiss
            faiss.write_index(self._index, self.index_file)
            with open(self.ids_file, 'w', encoding='utf-8') as f:
                json.dump(self._case_ids, f, ensure_ascii=False)
    
    def build_case_text(self, case_data: Dict) -> str:
        """
        构建案例的向量化文本
        
        Args:
            case_data: 案例数据（从JSON加载的字典）
        
        Returns:
            用于向量化的文本
        """
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
        
        # 因素描述（重要的语义信息）
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
        """
        文本编码为向量
        
        Args:
            texts: 文本列表
        
        Returns:
            向量数组 (n, dim)
        """
        if not texts:
            return np.array([])
        
        # BGE模型建议添加指令前缀
        # 对于检索任务，query加前缀，passage不加
        vectors = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            show_progress_bar=len(texts) > 10,
            normalize_embeddings=True  # 归一化，使内积等价于余弦相似度
        )
        return vectors
    
    def encode_query(self, query: str) -> np.ndarray:
        """
        编码查询文本（添加BGE查询前缀）
        
        Args:
            query: 查询文本
        
        Returns:
            查询向量 (1, dim)
        """
        # BGE模型的查询前缀
        query_with_prefix = f"为这个句子生成表示以用于检索相关文章：{query}"
        vector = self.model.encode(
            [query_with_prefix],
            normalize_embeddings=True
        )
        return vector
    
    def rebuild(self, cases: List[Dict]):
        """
        重建向量索引
        
        Args:
            cases: 案例列表，每个案例需包含case_id和完整数据
        """
        import faiss
        
        if not cases:
            print("⚠️ 没有案例数据，跳过向量索引构建")
            self._index = None
            self._case_ids = []
            self._dirty = False
            return
        
        print(f"🔨 重建向量索引: {len(cases)}个案例")
        
        # 构建文本
        texts = []
        case_ids = []
        for case in cases:
            case_id = case.get('case_id_full') or case.get('case_id')
            if not case_id:
                continue
            
            text = self.build_case_text(case)
            if text.strip():
                texts.append(text)
                case_ids.append(case_id)
        
        if not texts:
            print("⚠️ 没有有效文本，跳过向量索引构建")
            self._index = None
            self._case_ids = []
            self._dirty = False
            return
        
        # 编码
        print(f"   编码 {len(texts)} 条文本...")
        vectors = self.encode(texts)
        
        # 创建索引
        print(f"   构建FAISS索引...")
        dimension = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dimension)  # 内积索引
        self._index.add(vectors.astype(np.float32))
        
        self._case_ids = case_ids
        self._dirty = False
        
        # 保存
        self._save_index()
        print(f"   ✓ 向量索引构建完成: {self._index.ntotal}条向量")
    
    def search(self, 
               query: str, 
               top_k: int = 20,
               filter_ids: List[str] = None) -> List[Tuple[str, float]]:
        """
        向量检索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            filter_ids: 限定在这些ID中搜索（可选）
        
        Returns:
            [(case_id, score), ...]
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        
        # 编码查询
        query_vector = self.encode_query(query)
        
        # 搜索
        # 如果有filter_ids，搜更多然后过滤
        search_k = top_k * 3 if filter_ids else top_k
        search_k = min(search_k, self._index.ntotal)
        
        scores, indices = self._index.search(
            query_vector.astype(np.float32), 
            search_k
        )
        
        # 组装结果
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self._case_ids):
                continue
            
            case_id = self._case_ids[idx]
            score = float(scores[0][i])
            
            # 过滤
            if filter_ids and case_id not in filter_ids:
                continue
            
            results.append((case_id, score))
            
            if len(results) >= top_k:
                break
        
        return results
    
    def search_by_case(self,
                       case_data: Dict,
                       top_k: int = 10,
                       exclude_self: bool = True) -> List[Tuple[str, float]]:
        """
        根据案例查找相似案例
        
        Args:
            case_data: 案例数据
            top_k: 返回数量
            exclude_self: 是否排除自己
        
        Returns:
            [(case_id, score), ...]
        """
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
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_vectors': self._index.ntotal if self._index else 0,
            'dimension': self.config.dimension,
            'is_dirty': self._dirty,
            'index_file': self.index_file,
        }


# ============================================================================
# 便捷函数
# ============================================================================

_vector_store_instance = None

def get_vector_store(storage_path: str = None) -> VectorStore:
    """获取向量存储单例"""
    global _vector_store_instance
    if _vector_store_instance is None:
        if storage_path is None:
            storage_path = "./knowledge_base/storage"
        _vector_store_instance = VectorStore(storage_path)
    return _vector_store_instance


def reset_vector_store():
    """重置向量存储单例"""
    global _vector_store_instance
    _vector_store_instance = None
