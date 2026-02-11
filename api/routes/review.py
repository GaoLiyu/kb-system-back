"""
审查接口（同步）
================
保留快速校验和数据提取两个同步接口。
异步审查任务已迁移到 routes/tasks.py
"""

import os
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends

from ..dependencies import RequireRoles, get_system
from ..config import settings
from ..iam_client import UserContext
from utils import temp_manager, convert_doc_to_docx
from ..schemas import success_response


router = APIRouter(prefix="/review", tags=["审查"])


@router.post("/validate", summary="快速校验（同步）")
async def validate_report(
    file: UploadFile = File(...),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """快速校验，仅规则检查，不调用 LLM"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    with temp_manager.temp_file(suffix=ext, prefix="validate_") as upload_path:
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)

        if upload_path.lower().endswith('.doc'):
            upload_path = convert_doc_to_docx(upload_path)
            temp_manager.register(upload_path)

        system = get_system()
        result = system.validate(
            upload_path, verbose=False, original_filename=file.filename
        )

        return success_response(
            data={
                "risk_level": result.risk_level,
                "summary": result.summary,
                "issues": [
                    {
                        "level": i.level,
                        "category": i.category,
                        "description": i.description,
                    }
                    for i in result.issues
                ],
                "formula_checks": [
                    {
                        "case_id": f.case_id,
                        "expected": f.expected,
                        "actual": f.actual,
                        "is_valid": f.is_valid,
                    }
                    for f in result.formula_checks
                ],
            }
        )


@router.post("/extract", summary="仅提取（同步）")
async def extract_report(
    file: UploadFile = File(...),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """仅提取报告内容，不做审查"""
    from extractors import extract_report as do_extract
    from utils import detect_report_type

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    upload_path = os.path.join(settings.upload_dir, f"extract_{file.filename}")
    try:
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)

        if upload_path.lower().endswith('.doc'):
            upload_path = convert_doc_to_docx(upload_path)

        report_type = detect_report_type(file.filename)
        result = do_extract(
            upload_path, report_type, original_filename=file.filename
        )

        return success_response(
            data={
                "report_type": report_type,
                "subject": {
                    "address": (
                        result.subject.address.value
                        if result.subject.address else None
                    ),
                    "building_area": (
                        result.subject.building_area.value
                        if result.subject.building_area else None
                    ),
                },
                "cases": [
                    {
                        "case_id": c.case_id,
                        "address": c.address.value if c.address else None,
                        "area": (
                            c.building_area.value
                            if c.building_area else None
                        ),
                    }
                    for c in result.cases
                ],
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(upload_path):
            os.remove(upload_path)