"""
知识库管理
==========
负责数据的存储和索引
"""

import os
import sys
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import generate_id, get_timestamp


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
    """知识库管理器"""
    
    def __init__(self, base_path: str = "./knowledge_base/storage", enable_vector: bool = True):
        self.base_path = base_path
        self.reports_path = os.path.join(base_path, "reports")
        self.cases_path = os.path.join(base_path, "cases")
        self.index_path = os.path.join(base_path, "index")
        self.enable_vector = enable_vector
        
        # 创建目录
        for path in [self.reports_path, self.cases_path, self.index_path]:
            os.makedirs(path, exist_ok=True)
        
        # 加载索引
        self.index = self._load_index()

        # 向量存储（延时初始化）
        self._vector_store = None
    
    def _load_index(self) -> Dict:
        """加载索引"""
        index_file = os.path.join(self.index_path, "main_index.json")
        if os.path.exists(index_file):
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'reports': [], 'cases': []}
    
    def _save_index(self):
        """保存索引"""
        index_file = os.path.join(self.index_path, "main_index.json")
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    @property
    def vector_store(self):
        """获取向量存储（延迟加载）"""
        if not self.enable_vector:
            return None

        if self._vector_store is None:
            try:
                from .vector_store import VectorStore
                self._vector_store = VectorStore(self.base_path)
            except ImportError as e:
                print(f"⚠️ 向量存储不可用（缺少依赖）: {e}")
                self.enable_vector = False
                return None
        return self._vector_store

    def rebuild_vector_index(self):
        """重建向量索引"""
        if not self.enable_vector or self.vector_store is None:
            print("⚠️ 向量存储不可用")
            return

        # 加载所有案例完整数据
        cases = []
        for case_item in self.index.get('cases', []):
            case_id = case_item.get('case_id')
            case_data = self.get_case(case_id)
            if case_data:
                cases.append(case_data)

        # 重建索引
        self.vector_store.rebuild(cases)

    def ensure_vector_index(self):
        """确保向量索引是最新的（如果需要重建则重建）"""
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
        
        # 转为字典
        data = result_to_dict(result)
        data['doc_id'] = doc_id
        data['report_type'] = report_type
        data['extract_time'] = get_timestamp()
        
        # 保存报告
        report_file = os.path.join(self.reports_path, f"{doc_id}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 添加到索引（扩展字段）
        subject = result.subject
        self.index['reports'].append({
            'doc_id': doc_id,
            'report_type': report_type,
            'source_file': result.source_file,
            'address': subject.address.value or '',
            'area': subject.building_area.value or 0,
            'case_count': len(result.cases),
            'create_time': get_timestamp(),
            # 扩展字段
            'district': getattr(subject, 'district', ''),
            'street': getattr(subject, 'street', ''),
            'usage': getattr(subject, 'usage', ''),
            'build_year': getattr(subject, 'build_year', 0),
            'total_floor': getattr(subject, 'total_floor', 0),
            'current_floor': getattr(subject, 'current_floor', 0),
            'structure': getattr(subject, 'structure', ''),
            'value_date': getattr(subject, 'value_date', ''),
            'appraisal_purpose': getattr(subject, 'appraisal_purpose', ''),
        })
        
        # 保存案例并添加到索引
        for case in result.cases:
            case_id = f"{doc_id}_case_{case.case_id}"
            case_data = result_to_dict(result)['cases'][result.cases.index(case)]
            case_data['case_id_full'] = case_id
            case_data['from_doc'] = doc_id
            case_data['report_type'] = report_type
            
            case_file = os.path.join(self.cases_path, f"{case_id}.json")
            with open(case_file, 'w', encoding='utf-8') as f:
                json.dump(case_data, f, ensure_ascii=False, indent=2)
            
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
            
            # 解析交易日期为标准格式
            transaction_date = getattr(case, 'transaction_date', '')
            
            self.index['cases'].append({
                'case_id': case_id,
                'case_label': case.case_id,
                'from_doc': doc_id,
                'report_type': report_type,
                'address': case.address.value or '',
                'area': area,
                'price': price,
                # 扩展字段
                'district': getattr(case, 'district', ''),
                'street': getattr(case, 'street', ''),
                'usage': getattr(case, 'usage', ''),
                'build_year': getattr(case, 'build_year', 0),
                'total_floor': getattr(case, 'total_floor', 0),
                'current_floor': getattr(case, 'current_floor', 0),
                'structure': getattr(case, 'structure', ''),
                'orientation': getattr(case, 'orientation', ''),
                'decoration': getattr(case, 'decoration', ''),
                'transaction_date': transaction_date,
            })
        
        self._save_index()

        # 标记向量索引需要重建
        if self.enable_vector and self._vector_store is not None:
            self._vector_store.mark_dirty()

        return doc_id
    
    def get_report(self, doc_id: str) -> Optional[Dict]:
        """获取报告"""
        report_file = os.path.join(self.reports_path, f"{doc_id}.json")
        if os.path.exists(report_file):
            with open(report_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def get_case(self, case_id: str) -> Optional[Dict]:
        """获取单个案例详情"""
        for doc_id, report in self.index.get("reports", {}).items():
            for case in report.get("cases", []):
                if case.get("case_id") == case_id:
                    return {
                        "case_id": case_id,
                        "doc_id": doc_id,
                        "report_type": report.get("report_type"),
                        **case,
                    }
        return None
    
    def list_reports(self, report_type: str = None) -> List[Dict]:
        """列出报告"""
        reports = self.index.get('reports', [])
        if report_type:
            reports = [r for r in reports if r.get('report_type') == report_type]
        return reports
    
    def list_cases(self, report_type: str = None) -> List[Dict]:
        """列出案例"""
        cases = self.index.get('cases', [])
        if report_type:
            cases = [c for c in cases if c.get('report_type') == report_type]
        return cases
    
    def delete_report(self, doc_id: str) -> bool:
        """删除报告及其案例"""
        # 删除报告文件
        report_file = os.path.join(self.reports_path, f"{doc_id}.json")
        if os.path.exists(report_file):
            os.remove(report_file)
        
        # 删除案例文件
        for case in self.index.get('cases', []):
            if case.get('from_doc') == doc_id:
                case_file = os.path.join(self.cases_path, f"{case['case_id']}.json")
                if os.path.exists(case_file):
                    os.remove(case_file)
        
        # 更新索引
        self.index['reports'] = [r for r in self.index.get('reports', []) if r.get('doc_id') != doc_id]
        self.index['cases'] = [c for c in self.index.get('cases', []) if c.get('from_doc') != doc_id]
        self._save_index()

        # 标记向量索引需要重建
        if self.enable_vector and self._vector_store is not None:
            self._vector_store.mark_dirty()
        
        return True
    
    def stats(self) -> Dict:
        """统计信息"""
        reports = self.index.get('reports', [])
        cases = self.index.get('cases', [])
        
        by_type = {}
        for r in reports:
            t = r.get('report_type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1

        # 向量索引状态
        vector_stats = {}
        if self.enable_vector and self._vector_store is not None:
            vector_stats = self._vector_store.get_stats()
        
        return {
            'total_reports': len(reports),
            'total_cases': len(cases),
            'by_type': by_type,
            'vector_index': vector_stats,
        }
    
    def clear(self):
        """清空知识库"""
        import shutil
        for path in [self.reports_path, self.cases_path]:
            if os.path.exists(path):
                shutil.rmtree(path)
                os.makedirs(path)
        self.index = {'reports': [], 'cases': []}
        self._save_index()

        # 清空向量索引
        if self.enable_vector and self._vector_store is not None:
            vectors_path = os.path.join(self.base_path, 'vectors')
            if os.path.exists(vectors_path):
                shutil.rmtree(vectors_path)
                os.makedirs(vectors_path)
            self._vector_store.mark_dirty()
