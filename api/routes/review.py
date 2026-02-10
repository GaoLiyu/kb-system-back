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
    get_system
)
from ..config import settings
from ..iam_client import UserContext
from ..task_manager import ReviewTaskManager, submit_review_task
from ..auth import get_current_user, get_data_scope, require_roles, DataScope
from utils import temp_manager, convert_doc_to_docx
from ..schemas import success_response, error_response, paginated_response


router = APIRouter(prefix="/review", tags=["审查"])


# ============================================================================
# 异步审查接口
# ============================================================================

@router.post("/submit", summary="提交审查任务")
async def submit_review(
    file: UploadFile = File(...),
    mode: str = Query("full", description="审查模式: quick/full"),
    user: UserContext = Depends(require_roles("reviewer"))
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
    save_path = temp_manager.create_temp_file(suffix=ext, prefix="review_")

    try:
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        temp_manager.cleanup(save_path) # 删除临时文件
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 创建任务
    task_id = ReviewTaskManager.create_task(
        filename=file.filename,
        file_path=save_path,
        review_mode=mode,
        user_id=user.user_id,
        org_id=user.org_id,
    )

    # 提交到线程池
    system = get_system()
    submit_review_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id},
        message="审查任务已提交",
    )


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
        save_path = temp_manager.create_temp_file(suffix=ext, prefix="review_")

        try:
            with open(save_path, "wb") as f:
                content = await file.read()
                f.write(content)

            # 创建任务
            task_id = ReviewTaskManager.create_task(
                filename=file.filename,
                file_path=save_path,
                review_mode=mode,
                user_id=user.user_id,
                org_id=user.org_id,
            )

            # 提交到线程池
            submit_review_task(task_id, system, settings)
            task_ids.append({"filename": file.filename, "task_id": task_id})

        except Exception as e:
            task_ids.append({"filename": file.filename, "task_id": None, "error": str(e)})

    return success_response(
        data={
            "total": len(files),
            "submitted": len(task_ids),
            "task_ids": task_ids,
        },
        message=f"已提交 {len(task_ids)} 个审查任务",
    )


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
        return error_response(message="任务不存在", error_code="NOT_FOUND")

    return success_response(data=task)


@router.get("/tasks", summary="任务列表")
async def list_tasks(
    status: str = Query(None, description="筛选状态: pending/running/completed/failed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scope: DataScope = Depends(get_data_scope),
):
    """
    获取审查任务列表
    """
    tasks = ReviewTaskManager.list_tasks(status=status, limit=limit, offset=offset, user_id=scope.user_id, org_id=scope.org_id, scope=scope.scope_type)
    stats = ReviewTaskManager.get_stats(user_id=scope.user_id, org_id=scope.org_id, scope=scope.scope_type)

    return success_response(
        data={"tasks": tasks, "stats": stats},
    )


@router.delete("/task/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    user: UserContext = Depends(get_current_user),
    scope: DataScope = Depends(get_data_scope),
):
    """
    删除审查任务
    """
    task = ReviewTaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if scope.scope_type == 'SELF':
        # 普通用户只能删除自己的任务
        if task.get('create_by') != user.user_id:
            raise HTTPException(status_code=403, detail="只能删除自己的任务")
    elif scope.scope_type == 'ORG':
        # 管理员只能删除本组织的任务
        if task.get('org_id') != user.org_id:
            raise HTTPException(status_code=403, detail="只能删除本组织的任务")

    success = ReviewTaskManager.delete_task(task_id)

    return success_response(message="任务已删除")


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

    with temp_manager.temp_file(suffix=ext, prefix="validate_") as upload_path:
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 处理文件
        if upload_path.lower().endswith('.doc'):
            upload_path = convert_doc_to_docx(upload_path)
            temp_manager.register(upload_path)  # 注册转换后的文件

        system = get_system()
        result = system.validate(upload_path, verbose=False, original_filename=file.filename)

        return success_response(
            data={
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
        )


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

        report_type = detect_report_type(file.filename)
        result = do_extract(upload_path, report_type, file.filename)

        return success_response(
            data={
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(upload_path):
            os.remove(upload_path)