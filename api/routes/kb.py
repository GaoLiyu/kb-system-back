"""
知识库接口
"""

import os
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Query

from ..auth import get_current_user, require_editor, require_viewer
from ..config import settings
from main import RealEstateKBSystem
from utils import detect_report_type
from ..dependencies import (
    CurrentUser,
    RequireRoles,
    OrgScoped,
    RequirePermission,
)
from ..iam_client import UserContext

router = APIRouter(prefix="/kb", tags=["知识库"])

_system = None

def get_system():
    global _system
    if _system is None:
        _system = RealEstateKBSystem(
            kb_path=settings.kb_path,
            enable_llm=settings.enable_llm,
            enable_vector=settings.enable_vector,
        )
    return _system


@router.get("/reports", summary="报告列表")
async def list_reports(
    report_type: str = Query(None, description="报告类型筛选"),
    keyword: str = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: UserContext = Depends(CurrentUser(required=False))
):
    """
    获取报告列表（分页）
    """
    system = get_system()

    # 获取全部报告
    all_reports = system.kb.list_reports(report_type)

    # 关键词筛选
    if keyword:
        keyword = keyword.lower()
        all_reports = [
            r for r in all_reports
            if keyword in (r.get('address', '') or '').lower()
            or keyword in (r.get('source_file', '') or '').lower()
        ]

    # 分页
    total = len(all_reports)
    start = (page - 1) * page_size
    end = start + page_size
    reports = all_reports[start:end]

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "reports": reports,
    }


@router.get("/cases", summary="案例列表")
async def list_cases(
    report_type: str = Query(None, description="报告类型"),
    district: str = Query(None, description="区域"),
    usage: str = Query(None, description="用途"),
    keyword: str = Query(None, description="关键词"),
    min_area: float = Query(None, description="最小面积"),
    max_area: float = Query(None, description="最大面积"),
    min_price: float = Query(None, description="最低价格"),
    max_price: float = Query(None, description="最高价格"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: UserContext = Depends(CurrentUser(required=False))
):
    """
    获取案例列表（分页+筛选）
    """
    system = get_system()

    # 获取全部案例
    all_cases = system.kb.list_cases(report_type)

    # 筛选
    filtered = []
    for c in all_cases:
        # 区域筛选
        if district and c.get('district') != district:
            continue

        # 用途筛选
        if usage and c.get('usage') != usage:
            continue

        # 面积筛选
        area = c.get('area') or 0
        if min_area and area < min_area:
            continue
        if max_area and area > max_area:
            continue

        # 价格筛选
        price = c.get('price') or 0
        if min_price and price < min_price:
            continue
        if max_price and price > max_price:
            continue

        # 关键词
        if keyword:
            keyword_lower = keyword.lower()
            address = (c.get('address') or '').lower()
            if keyword_lower not in address:
                continue

        filtered.append(c)

    # 分页
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    cases = filtered[start:end]

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "cases": cases,
    }


@router.get("/case/{case_id}", summary="案例详情")
async def get_case_detail(
    case_id: str,
    user: UserContext = Depends(CurrentUser(required=False))
):
    """
    获取案例详情
    """
    system = get_system()

    case = system.kb.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    return {
        "success": True,
        "case": case,
    }


@router.get("/report/{doc_id}", summary="报告详情")
async def get_report_detail(
    doc_id: str,
    user: UserContext = Depends(CurrentUser(required=False))
):
    """
    获取报告详情（包含所有案例）
    """
    system = get_system()

    report = system.kb.get_report(doc_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {
        "success": True,
        "report": report,
    }


@router.get("/filters", summary="获取筛选选项")
async def get_filter_options(
    user: UserContext = Depends(CurrentUser(required=False))
):
    """
    获取可用的筛选选项（区域、用途等）
    """
    system = get_system()
    all_cases = system.kb.list_cases()

    districts = set()
    usages = set()
    report_types = set()

    for c in all_cases:
        if c.get('district'):
            districts.add(c['district'])
        if c.get('usage'):
            usages.add(c['usage'])
        if c.get('report_type'):
            report_types.add(c['report_type'])

    return {
        "success": True,
        "districts": sorted(list(districts)),
        "usages": sorted(list(usages)),
        "report_types": sorted(list(report_types)),
    }


@router.post("/upload", summary="上传报告")
async def upload_report(
    file: UploadFile = File(...),
    report_type: str = None,
    user: UserContext = Depends(require_editor)
):
    """上传报告到知识库"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    upload_path = os.path.join(settings.upload_dir, f"kb_{file.filename}")
    try:
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)

        system = get_system()
        doc_id = system.add_report(upload_path, verbose=False)
        detected_type = report_type or detect_report_type(upload_path)

        return {
            "success": True,
            "doc_id": doc_id,
            "report_type": detected_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(upload_path):
            os.remove(upload_path)


@router.post("/batch-upload", summary="批量上传报告")
async def batch_upload_reports(
    files: List[UploadFile] = File(...),
    report_type: str = None,
    user: UserContext = Depends(require_editor)
):
    """批量上传报告到知识库"""
    results = []
    success_count = 0
    fail_count = 0

    system = get_system()

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()

        if ext not in settings.allowed_extensions:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": f"不支持的文件格式: {ext}",
            })
            fail_count += 1
            continue

        upload_path = os.path.join(settings.upload_dir, f"batch_{file.filename}")
        try:
            with open(upload_path, "wb") as f:
                content = await file.read()
                f.write(content)

            doc_id = system.add_report(upload_path, verbose=False)
            detected_type = report_type or detect_report_type(upload_path)

            results.append({
                "filename": file.filename,
                "success": True,
                "doc_id": doc_id,
                "report_type": detected_type,
            })
            success_count += 1

        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e),
            })
            fail_count += 1
        finally:
            if os.path.exists(upload_path):
                os.remove(upload_path)

    return {
        "success": True,
        "total": len(files),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }


@router.delete("/report/{doc_id}", summary="删除报告")
async def delete_report(
    doc_id: str,
    user: UserContext = Depends(require_editor)
):
    """删除报告及其案例"""
    system = get_system()

    success = system.kb.delete_report(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {"success": True, "message": "删除成功"}


@router.get("/stats", summary="统计信息")
async def get_stats(user: UserContext = Depends(require_viewer)):
    """获取知识库统计"""
    system = get_system()
    return {
        "success": True,
        **system.stats()
    }