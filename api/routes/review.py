"""
审查接口
"""

import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Query
from fastapi.responses import FileResponse

from ..dependencies import (
    CurrentUser,
    RequireRoles,
    OrgScoped,
    RequirePermission,
)
from ..config import settings
from .kb import get_system
from ..iam_client import UserContext
from ..task_manager import ReviewTaskManager, submit_review_task

router = APIRouter(prefix="/review", tags=["审查"])


# ============================================================================
# 异步审查接口
# ============================================================================

@router.post("/submit", summary="提交审查任务")
async def submit_review(
    file: UploadFile = File(...),
    mode: str = Query("full", description="审查模式: quick/full"),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """
    提交异步审查任务

    Args:
        file: 报告文件
        mode: 审查模式 (quick=快速, full=完整带原文)

    Returns:
        task_id
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    # 保存文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_filename = f"review_{timestamp}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, save_filename)

    try:
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 创建任务
    task_id = ReviewTaskManager.create_task(
        filename=file.filename,
        file_path=save_path,
        review_mode=mode,
    )

    # 提交到线程池
    system = get_system()
    submit_review_task(task_id, system, settings)

    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已提交，请稍后查询结果",
    }


@router.post("/submit-batch", summary="批量提交审查任务")
async def submit_batch_review(
    files: List[UploadFile] = File(...),
    mode: str = Query("quick", description="审查模式: quick/full"),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """
    批量提交审查任务
    """
    task_ids = []
    system = get_system()

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.allowed_extensions:
            continue

        # 保存文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_filename = f"review_{timestamp}_{file.filename}"
        save_path = os.path.join(settings.upload_dir, save_filename)

        try:
            with open(save_path, "wb") as f:
                content = await file.read()
                f.write(content)

            # 创建任务
            task_id = ReviewTaskManager.create_task(
                filename=file.filename,
                file_path=save_path,
                review_mode=mode,
            )

            # 提交到线程池
            submit_review_task(task_id, system, settings)
            task_ids.append({"filename": file.filename, "task_id": task_id})

        except Exception as e:
            task_ids.append({"filename": file.filename, "task_id": None, "error": str(e)})

    return {
        "success": True,
        "count": len([t for t in task_ids if t.get("task_id")]),
        "tasks": task_ids,
    }


@router.get("/task/{task_id}", summary="查询任务状态")
async def get_task_status(
    task_id: str,
    user: UserContext = Depends(RequireRoles("viewer"))
):
    """
    查询审查任务状态和结果
    """
    task = ReviewTaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "success": True,
        **task,
    }


@router.get("/tasks", summary="任务列表")
async def list_tasks(
    status: str = Query(None, description="筛选状态: pending/running/completed/failed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(RequireRoles("viewer"))
):
    """
    获取审查任务列表
    """
    tasks = ReviewTaskManager.list_tasks(status=status, limit=limit, offset=offset)
    stats = ReviewTaskManager.get_stats()

    return {
        "success": True,
        "tasks": tasks,
        "stats": stats,
    }


@router.delete("/task/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """
    删除审查任务
    """
    success = ReviewTaskManager.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {"success": True, "message": "删除成功"}


@router.post("/task/{task_id}/export", summary="导出任务结果")
async def export_task_result(
    task_id: str,
    include_original: bool = False,
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """
    导出审查任务结果为 Word 文档
    """
    task = ReviewTaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    result = task.get("result")
    if not result:
        raise HTTPException(status_code=400, detail="无审查结果")

    # 组装导出数据
    from reviewer import create_review_report, create_review_report_with_original

    export_data = {
        "overall_risk": task["overall_risk"],
        "summary": f"发现 {task['validation_count']} 个校验问题，{task['llm_count']} 个语义问题",
        "document_content": result.get("document_content", {"filename": task["filename"]}),
        "validation_issues": result.get("validation_issues", []),
        "formula_checks": result.get("formula_checks", []),
        "llm_issues": result.get("llm_issues", []),
    }

    # 生成文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(task["filename"])[0]
    output_filename = f"{base_name}_审查报告_{timestamp}.docx"
    output_path = os.path.join(settings.upload_dir, output_filename)

    if include_original and result.get("document_content"):
        create_review_report_with_original(export_data, output_path)
    else:
        create_review_report(export_data, output_path)

    return FileResponse(
        path=output_path,
        filename=output_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ============================================================================
# 原有同步接口（保留兼容）
# ============================================================================

@router.post("/validate", summary="快速校验（同步）")
async def validate_report(
    file: UploadFile = File(...),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """快速校验，仅规则检查，不调用 LLM"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    upload_path = os.path.join(settings.upload_dir, f"validate_{file.filename}")
    try:
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)

        system = get_system()
        result = system.validate(upload_path, verbose=False)

        return {
            "success": True,
            "risk_level": result.risk_level,
            "summary": result.summary,
            "issues": [
                {"level": i.level, "category": i.category, "description": i.description}
                for i in result.issues
            ],
            "formula_checks": [
                {"case_id": f.case_id, "expected": f.expected, "actual": f.actual, "is_valid": f.is_valid}
                for f in result.formula_checks
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(upload_path):
            os.remove(upload_path)


@router.post("/extract", summary="仅提取（同步）")
async def extract_report(
    file: UploadFile = File(...),
    user: UserContext = Depends(RequireRoles("admin", "reviewer"))
):
    """仅提取报告内容，不做审查"""
    from extractors import extract_report as do_extract
    from utils import convert_doc_to_docx, detect_report_type

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

        report_type = detect_report_type(upload_path)
        result = do_extract(upload_path)

        return {
            "success": True,
            "report_type": report_type,
            "subject": {
                "address": result.subject.address.value if result.subject.address else None,
                "building_area": result.subject.building_area.value if result.subject.building_area else None,
            },
            "cases": [
                {
                    "case_id": c.case_id,
                    "address": c.address.value if c.address else None,
                    "area": c.building_area.value if c.building_area else None,
                }
                for c in result.cases
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(upload_path):
            os.remove(upload_path)