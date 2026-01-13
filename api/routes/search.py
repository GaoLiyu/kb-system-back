"""
搜索接口
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import get_current_user
from ..iam_client import UserContext
from ..config import settings


router = APIRouter(prefix="/search", tags=["搜索"])


# ============================================================================
# 请求/响应模型
# ============================================================================

class FieldSearchRequest(BaseModel):
    """字段搜索请求"""
    report_type: str = ""
    district: str = ""
    usage: str = ""
    min_area: float = 0
    max_area: float = 0
    min_price: float = 0
    max_price: float = 0
    address_keyword: str = ""
    page: int = 1
    page_size: int = 20


class VectorSearchRequest(BaseModel):
    """向量搜索请求"""
    query: str
    report_type: str = ""
    top_k: int = 10


class HybridSearchRequest(BaseModel):
    """混合搜索请求"""
    query: str
    report_type: str = ""
    district: str = ""
    usage: str = ""
    min_area: float = 0
    max_area: float = 0
    vector_weight: float = 0.6
    top_k: int = 20


class SimilarSearchRequest(BaseModel):
    """相似搜索请求"""
    query: str
    report_type: str = ""
    top_k: int = 10


# ============================================================================
# 获取系统实例
# ============================================================================

_system = None

def get_system():
    global _system
    if _system is None:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from main import RealEstateKBSystem
        _system = RealEstateKBSystem(
            kb_path=settings.kb_path,
            enable_llm=settings.enable_llm,
            enable_vector=settings.enable_vector,
        )
    return _system


# ============================================================================
# 接口
# ============================================================================

@router.post("/field", summary="字段搜索")
def field_search(req: FieldSearchRequest, user: UserContext = Depends(get_current_user)):
    """
    按字段条件搜索案例

    支持多条件组合：类型、区域、用途、面积范围、价格范围、地址关键词
    """
    system = get_system()

    # 构建过滤条件
    filters = {}
    if req.report_type:
        filters['report_type'] = req.report_type
    if req.district:
        filters['district'] = req.district
    if req.usage:
        filters['usage'] = req.usage
    if req.min_area > 0:
        filters['min_area'] = req.min_area
    if req.max_area > 0:
        filters['max_area'] = req.max_area
    if req.min_price > 0:
        filters['min_price'] = req.min_price
    if req.max_price > 0:
        filters['max_price'] = req.max_price
    if req.address_keyword:
        filters['address_keyword'] = req.address_keyword

    # 搜索
    results, total = system.query.search_cases_by_fields(
        filters=filters,
        page=req.page,
        page_size=req.page_size,
    )

    # 转换结果
    cases = []
    for case_data in results:
        cases.append({
            "case_id": case_data.get('case_id_full', ''),
            "address": case_data.get('address', {}).get('value', ''),
            "area": case_data.get('building_area', {}).get('value', 0),
            "price": case_data.get('transaction_price', {}).get('value', 0) or
                     case_data.get('rental_price', {}).get('value', 0),
            "district": case_data.get('district', ''),
            "usage": case_data.get('usage', ''),
            "report_type": case_data.get('report_type', ''),
            "transaction_date": case_data.get('transaction_date', ''),
        })

    return {
        "success": True,
        "total": total,
        "page": req.page,
        "page_size": req.page_size,
        "cases": cases,
    }


@router.post("/vector", summary="向量搜索")
def vector_search(req: VectorSearchRequest, user: UserContext = Depends(get_current_user)):
    """
    使用向量相似度搜索案例

    基于语义理解，找到与查询最相似的案例
    """
    system = get_system()

    if not settings.enable_vector:
        return {"success": False, "error": "向量搜索未启用"}

    # 向量搜索
    results = system.query.search_cases_by_vector(
        query=req.query,
        report_type=req.report_type,
        top_k=req.top_k,
    )

    # 转换结果
    cases = []
    for case_data, score in results:
        cases.append({
            "case_id": case_data.get('case_id_full', ''),
            "address": case_data.get('address', {}).get('value', ''),
            "area": case_data.get('building_area', {}).get('value', 0),
            "price": case_data.get('transaction_price', {}).get('value', 0) or
                     case_data.get('rental_price', {}).get('value', 0),
            "district": case_data.get('district', ''),
            "usage": case_data.get('usage', ''),
            "score": score,
        })

    return {"success": True, "cases": cases, "total": len(cases)}


@router.post("/hybrid", summary="混合搜索")
def hybrid_search(req: HybridSearchRequest, user: UserContext = Depends(get_current_user)):
    """
    混合搜索（向量 + 规则）

    综合利用语义相似度和字段匹配，获得更准确的结果
    """
    system = get_system()

    # 混合搜索
    results = system.query.find_similar_cases_hybrid(
        query=req.query,
        area=None,
        district=req.district,
        usage=req.usage,
        report_type=req.report_type,
        top_k=req.top_k,
        vector_weight=req.vector_weight,
    )

    # 转换结果
    cases = []
    for case_data, score in results:
        cases.append({
            "case_id": case_data.get('case_id_full', ''),
            "address": case_data.get('address', {}).get('value', ''),
            "area": case_data.get('building_area', {}).get('value', 0),
            "price": case_data.get('transaction_price', {}).get('value', 0) or
                     case_data.get('rental_price', {}).get('value', 0),
            "district": case_data.get('district', ''),
            "usage": case_data.get('usage', ''),
            "score": score,
            "full_data": case_data,
        })

    return {"success": True, "cases": cases, "total": len(cases)}


@router.post("/similar", summary="相似案例")
def similar_search(req: SimilarSearchRequest, user: UserContext = Depends(get_current_user)):
    """
    查找相似案例

    根据自然语言描述查找最相似的案例
    """
    system = get_system()

    # 使用混合搜索
    results = system.query.find_similar_cases_hybrid(
        query=req.query,
        report_type=req.report_type,
        top_k=req.top_k,
    )

    # 转换结果
    cases = []
    for case_data, score in results:
        cases.append({
            "case_id": case_data.get('case_id_full', ''),
            "address": case_data.get('address', {}).get('value', ''),
            "area": case_data.get('building_area', {}).get('value', 0),
            "price": case_data.get('transaction_price', {}).get('value', 0) or
                     case_data.get('rental_price', {}).get('value', 0),
            "district": case_data.get('district', ''),
            "usage": case_data.get('usage', ''),
            "score": score,
        })

    return {"success": True, "cases": cases}


@router.get("/cases/{case_id}", summary="案例详情")
def get_case_detail(case_id: str, user: UserContext = Depends(get_current_user)):
    """
    获取案例详细信息
    """
    system = get_system()

    case_data = system.query.get_case_by_id(case_id)

    if not case_data:
        return {"success": False, "error": "案例不存在"}

    return {"success": True, "case": case_data}


@router.get("/stats/price", summary="价格统计")
def get_price_stats(
    report_type: str = Query("", description="报告类型"),
    district: str = Query("", description="区域"),
    user: UserContext = Depends(get_current_user),
):
    """
    获取价格统计信息
    """
    system = get_system()

    stats = system.query.get_price_stats(
        report_type=report_type,
        district=district,
    )

    return {"success": True, **stats}


@router.get("/stats/area", summary="面积统计")
def get_area_stats(
    report_type: str = Query("", description="报告类型"),
    user: UserContext = Depends(get_current_user),
):
    """
    获取面积统计信息
    """
    system = get_system()

    stats = system.query.get_area_stats(report_type=report_type)

    return {"success": True, **stats}


@router.get("/filters", summary="获取筛选选项")
def get_filter_options(user: UserContext = Depends(get_current_user)):
    """
    获取搜索筛选选项

    返回：报告类型、区域、用途等可选值
    """
    system = get_system()

    options = system.query.get_filter_options()

    return {
        "success": True,
        "report_types": options.get('report_types', []),
        "districts": options.get('districts', []),
        "usages": options.get('usages', []),
    }
