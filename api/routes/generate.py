"""
生成辅助接口
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import get_current_user
from ..iam_client import UserContext
from ..config import settings


router = APIRouter(prefix="/generate", tags=["生成辅助"])


# ============================================================================
# 请求/响应模型
# ============================================================================

class SubjectInput(BaseModel):
    """估价对象输入"""
    address: str
    building_area: float
    usage: str = "住宅"
    report_type: str = "shezhi"
    appraisal_purpose: str = ""
    value_date: str = ""
    district: str = ""
    street: str = ""
    current_floor: int = 0
    total_floor: int = 0
    build_year: int = 0
    orientation: str = ""
    structure: str = ""
    decoration: str = ""


class SuggestCasesRequest(BaseModel):
    """推荐案例请求"""
    address: str
    area: float
    report_type: str = "shezhi"
    district: str = ""
    usage: str = ""
    count: int = 5


class ValidateInputRequest(BaseModel):
    """验证输入请求"""
    subject: SubjectInput


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

@router.post("/suggest-cases", summary="推荐可比实例")
def suggest_cases(req: SuggestCasesRequest, user: UserContext = Depends(get_current_user)):
    """
    根据估价对象推荐可比实例

    使用混合检索（向量+规则）找到最合适的案例
    """
    system = get_system()

    # 构建查询文本
    query_parts = [req.address]
    if req.district:
        query_parts.append(req.district)
    if req.usage:
        query_parts.append(req.usage)
    query = " ".join(query_parts)

    # 混合检索
    results = system.query.find_similar_cases_hybrid(
        query=query,
        area=req.area,
        district=req.district,
        usage=req.usage,
        report_type=req.report_type,
        top_k=req.count,
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


@router.get("/reference/{report_type}", summary="获取参考数据")
def get_reference(report_type: str, user: UserContext = Depends(get_current_user)):
    """
    获取指定类型报告的参考数据

    包含：价格范围、面积范围、修正系数统计等
    """
    system = get_system()

    return {
        "success": True,
        "price_range": system.query.get_price_range(report_type),
        "area_range": system.query.get_area_range(report_type),
        "correction_stats": system.query.get_correction_stats(report_type),
    }


@router.post("/validate-input", summary="验证输入")
def validate_input(req: ValidateInputRequest, user: UserContext = Depends(get_current_user)):
    """
    验证生成输入是否完整
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from generator import validate_subject_input, SubjectInput as SI

    # 转换为内部格式
    subject = SI(
        address=req.subject.address,
        building_area=req.subject.building_area,
        usage=req.subject.usage,
        report_type=req.subject.report_type,
        appraisal_purpose=req.subject.appraisal_purpose,
        value_date=req.subject.value_date,
        district=req.subject.district,
        street=req.subject.street,
        current_floor=req.subject.current_floor,
        total_floor=req.subject.total_floor,
        build_year=req.subject.build_year,
        orientation=req.subject.orientation,
        structure=req.subject.structure,
        decoration=req.subject.decoration,
    )

    errors = validate_subject_input(subject)

    return {
        "success": True,
        "valid": len(errors) == 0,
        "errors": errors,
    }


@router.get("/input-schema", summary="获取输入表单定义")
def get_input_schema(user: UserContext = Depends(get_current_user)):
    """
    获取输入表单字段定义

    用于前端动态生成表单
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from generator import get_field_descriptions

    return {
        "success": True,
        "fields": get_field_descriptions(),
    }


@router.get("/report-types", summary="获取报告类型")
def get_report_types(user: UserContext = Depends(get_current_user)):
    """
    获取支持的报告类型
    """
    return {
        "success": True,
        "types": [
            {"value": "shezhi", "label": "涉执报告", "description": "司法处置房产评估"},
            {"value": "zujin", "label": "租金报告", "description": "租金评估"},
            {"value": "biaozhunfang", "label": "标准房报告", "description": "标准房价格评估"},
        ],
    }
