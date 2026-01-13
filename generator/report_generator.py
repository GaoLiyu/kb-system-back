"""
报告生成辅助
============
基于知识库提供生成支持

主要功能：
1. 推荐可比实例 - 根据估价对象找相似案例
2. 提供修正系数参考 - 基于历史数据
3. 生成文本片段 - 基于模板和知识库
"""

import os
import sys
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base import KnowledgeBaseManager, KnowledgeBaseQuery


class ReportGenerator:
    """报告生成辅助器"""
    
    def __init__(self, kb_manager: KnowledgeBaseManager):
        """
        Args:
            kb_manager: 知识库管理器
        """
        self.kb = kb_manager
        self.query = KnowledgeBaseQuery(kb_manager)
    
    def suggest_cases(self,
                      address: str,
                      area: float,
                      report_type: str,
                      count: int = 5) -> List[Dict]:
        """
        推荐可比实例
        
        Args:
            address: 估价对象地址
            area: 估价对象面积
            report_type: 报告类型
            count: 推荐数量
        
        Returns:
            推荐的案例列表
        """
        similar = self.query.find_similar_cases(
            address=address,
            area=area,
            report_type=report_type,
            top_k=count
        )
        
        return [case for case, score in similar]
    
    def get_correction_reference(self, report_type: str) -> Dict:
        """
        获取修正系数参考值
        
        Args:
            report_type: 报告类型
        
        Returns:
            各修正系数的统计值
        """
        return self.query.get_correction_stats(report_type)
    
    def get_price_reference(self, 
                            report_type: str,
                            area: float = None) -> Dict:
        """
        获取价格参考
        
        Args:
            report_type: 报告类型
            area: 面积（可选，用于筛选相近面积的案例）
        
        Returns:
            价格统计
        """
        if area:
            # 筛选面积相近的案例
            cases = self.query.search_cases(
                report_type=report_type,
                min_area=area * 0.5,
                max_area=area * 1.5,
            )
            
            prices = []
            for case in cases:
                price = case.get('transaction_price', {}).get('value') or \
                        case.get('rental_price', {}).get('value') or \
                        case.get('final_price', {}).get('value')
                if price:
                    prices.append(price)
            
            if prices:
                return {
                    'min': min(prices),
                    'max': max(prices),
                    'avg': sum(prices) / len(prices),
                    'count': len(prices),
                }
        
        return self.query.get_price_range(report_type)
    
    def generate_factor_description(self,
                                    factor_name: str,
                                    level: str,
                                    report_type: str) -> str:
        """
        生成因素描述（基于知识库中的类似描述）
        
        Args:
            factor_name: 因素名称
            level: 等级（优/较优/一般/较差/差）
            report_type: 报告类型
        
        Returns:
            描述文本
        """
        # 从知识库中查找类似的因素描述
        cases = self.query.search_cases(report_type=report_type, limit=20)
        
        descriptions = []
        for case in cases:
            for factor_type in ['location_factors', 'physical_factors', 'rights_factors']:
                factors = case.get(factor_type, {})
                if factor_name in factors:
                    factor = factors[factor_name]
                    if factor.get('level') == level and factor.get('description'):
                        descriptions.append(factor['description'])
        
        # 返回最常见的描述（简化版）
        if descriptions:
            return descriptions[0]
        
        return f"{factor_name}{level}"
    
    def get_template_data(self, report_type: str) -> Dict:
        """
        获取报告模板数据
        
        Args:
            report_type: 报告类型
        
        Returns:
            模板数据（因素列表、修正系数范围等）
        """
        correction_stats = self.query.get_correction_stats(report_type)
        price_stats = self.query.get_price_range(report_type)
        area_stats = self.query.get_area_range(report_type)
        
        return {
            'report_type': report_type,
            'price_range': price_stats,
            'area_range': area_stats,
            'correction_reference': correction_stats,
            'case_count_in_kb': self.kb.stats()['total_cases'],
        }


# ============================================================================
# 便捷函数
# ============================================================================

def create_generator(kb_path: str = "./knowledge_base/storage") -> ReportGenerator:
    """创建生成器"""
    kb = KnowledgeBaseManager(kb_path)
    return ReportGenerator(kb)
