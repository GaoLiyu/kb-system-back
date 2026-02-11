"""
统一任务管理路由
================

提供任务的创建、查询、管理等接口。
所有异步任务（审查、上传、导出等）统一在此管理。
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..auth import get_current_user
from ..iam_client import UserContext
from ..config import settings
from ..services.async_task_manager import TaskManager, TaskType, TaskStatus
from ..services.task_handlers import submit_task
from ..dependencies import get_system
from ..schemas import success_response, error_response

router = APIRouter(prefix="/tasks", tags=["任务管理"])


# ============================================================================
# 任务查询
# ============================================================================

@router.get("", summary="获取任务列表")
async def list_tasks(
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user),
):
    """获取任务列表（普通用户只能看到自己的）"""
    created_by = None
    if 'admin' not in user.roles:
        created_by = user.user_id

    tasks = TaskManager.list(
        task_type=task_type,
        status=status,
        created_by=created_by,
        limit=limit,
        offset=offset,
    )

    stats = TaskManager.get_stats(task_type=task_type, created_by=created_by)

    return success_response(data={
        "tasks": tasks,
        "total": stats['total'],
        "by_status": stats['by_status'],
    })


@router.get("/stats", summary="获取任务统计")
async def get_task_stats(
    task_type: Optional[str] = Query(None),
    user: UserContext = Depends(get_current_user),
):
    """获取任务统计信息"""
    created_by = None
    if 'admin' not in user.roles:
        created_by = user.user_id

    stats = TaskManager.get_stats(task_type=task_type, created_by=created_by)
    return success_response(data=stats)


@router.get("/{task_id}", summary="获取任务详情")
async def get_task(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """获取任务详细信息"""
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    return success_response(data=task)


# ============================================================================
# 审查任务
# ============================================================================

@router.post("/review", summary="创建审查任务")
async def create_review_task(
    file: UploadFile = File(..., description="要审查的报告文件"),
    review_mode: str = Form("full", description="审查模式: quick/full"),
    user: UserContext = Depends(get_current_user),
):
    """
    创建报告审查任务

    - quick: 快速审查，只返回问题列表
    - full: 完整审查，返回原文和问题标注
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    # 保存文件（保留原始文件名在路径中以便调试）
    upload_dir = os.path.join(settings.upload_dir, "review")
    os.makedirs(upload_dir, exist_ok=True)

    file_id = uuid.uuid4().hex[:8]
    safe_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(upload_dir, safe_filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 创建任务
    task_id = TaskManager.create(
        task_type=TaskType.REVIEW.value,
        name=file.filename,
        input_data={"review_mode": review_mode},
        file_path=file_path,
        file_name=file.filename,    # 原始文件名！
        file_size=len(content),
        created_by=user.user_id,
        org_id=user.org_id,
    )

    # 提交执行
    system = get_system()
    submit_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id},
        message="审查任务已创建",
    )


# ============================================================================
# 知识库上传任务
# ============================================================================

@router.post("/upload", summary="创建上传任务")
async def create_upload_task(
    file: UploadFile = File(...),
    report_type: Optional[str] = Form(None, description="报告类型，不填则自动检测"),
    enable_vectorize: bool = Form(True),
    user: UserContext = Depends(get_current_user),
):
    """创建知识库上传任务"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    upload_dir = os.path.join(settings.upload_dir, "kb")
    os.makedirs(upload_dir, exist_ok=True)

    file_id = uuid.uuid4().hex[:8]
    safe_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(upload_dir, safe_filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    task_id = TaskManager.create(
        task_type=TaskType.UPLOAD.value,
        name=file.filename,
        input_data={
            "report_type": report_type,
            "enable_vectorize": enable_vectorize,
        },
        file_path=file_path,
        file_name=file.filename,
        file_size=len(content),
        created_by=user.user_id,
        org_id=user.org_id,
    )

    system = get_system()
    submit_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id},
        message="上传任务已创建",
    )


@router.post("/batch-upload", summary="创建批量上传任务")
async def create_batch_upload_task(
    files: List[UploadFile] = File(...),
    report_type: Optional[str] = Form(None),
    user: UserContext = Depends(get_current_user),
):
    """创建批量上传任务"""
    if not files:
        raise HTTPException(status_code=400, detail="没有上传文件")

    upload_dir = os.path.join(settings.upload_dir, "batch")
    os.makedirs(upload_dir, exist_ok=True)

    file_infos = []
    total_size = 0

    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in settings.allowed_extensions:
            continue

        file_id = uuid.uuid4().hex[:8]
        safe_filename = f"{file_id}_{f.filename}"
        file_path = os.path.join(upload_dir, safe_filename)

        content = await f.read()
        with open(file_path, "wb") as fp:
            fp.write(content)

        file_infos.append({
            "file_path": file_path,
            "file_name": f.filename,
        })
        total_size += len(content)

    if not file_infos:
        raise HTTPException(status_code=400, detail="没有有效的文件")

    task_id = TaskManager.create(
        task_type=TaskType.BATCH_UPLOAD.value,
        name=f"批量上传 ({len(file_infos)} 个文件)",
        input_data={
            "files": file_infos,
            "report_type": report_type,
        },
        file_size=total_size,
        created_by=user.user_id,
        org_id=user.org_id,
    )

    system = get_system()
    submit_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id, "file_count": len(file_infos)},
        message=f"批量上传任务已创建 ({len(file_infos)} 个文件)",
    )


# ============================================================================
# 导出任务
# ============================================================================

@router.post("/export/cases", summary="创建案例导出任务")
async def create_export_cases_task(
    report_type: Optional[str] = Form(None),
    format: str = Form("xlsx"),
    user: UserContext = Depends(get_current_user),
):
    """创建案例导出任务"""
    task_id = TaskManager.create(
        task_type=TaskType.EXPORT.value,
        name="导出案例数据",
        input_data={
            "export_type": "cases",
            "format": format,
            "filters": {"report_type": report_type},
        },
        created_by=user.user_id,
        org_id=user.org_id,
    )

    system = get_system()
    submit_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id},
        message="导出任务已创建",
    )


@router.post("/export/review/{review_task_id}", summary="导出审查结果")
async def create_export_review_task(
    review_task_id: str,
    include_original: bool = Form(False),
    user: UserContext = Depends(get_current_user),
):
    """将审查结果导出为Word文档"""
    review_task = TaskManager.get(review_task_id)
    if not review_task:
        raise HTTPException(status_code=404, detail="审查任务不存在")
    if review_task['status'] != TaskStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="审查任务尚未完成")

    task_id = TaskManager.create(
        task_type=TaskType.EXPORT.value,
        name=f"导出审查报告: {review_task.get('file_name', '')}",
        input_data={
            "export_type": "review_result",
            "task_id": review_task_id,
            "include_original": include_original,
        },
        related_id=review_task_id,
        related_type="review_task",
        created_by=user.user_id,
        org_id=user.org_id,
    )

    system = get_system()
    submit_task(task_id, system, settings)

    return success_response(
        data={"task_id": task_id},
        message="导出任务已创建",
    )


@router.get("/{task_id}/download", summary="下载任务结果文件")
async def download_task_result(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """下载已完成任务的结果文件"""
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    if task['status'] != TaskStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="任务尚未完成")

    output_data = task.get('output_data') or {}
    file_path = output_data.get('file_path')
    file_name = output_data.get('file_name')

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type="application/octet-stream",
    )


# ============================================================================
# 任务管理
# ============================================================================

@router.post("/{task_id}/cancel", summary="取消任务")
async def cancel_task(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """取消等待中的任务"""
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权操作此任务")

    if task['status'] != TaskStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="只能取消等待中的任务")

    success = TaskManager.cancel(task_id)
    return success_response(message="任务已取消" if success else "取消失败")


@router.delete("/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """删除任务记录"""
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权操作此任务")

    if task['status'] == TaskStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="不能删除运行中的任务")

    TaskManager.delete(task_id)
    return success_response(message="任务已删除")


@router.post("/cleanup", summary="清理旧任务")
async def cleanup_tasks(
    days: int = Query(30, ge=1, le=365),
    status: Optional[str] = Query(None),
    user: UserContext = Depends(get_current_user),
):
    """清理旧任务（仅管理员）"""
    if 'admin' not in user.roles:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    count = TaskManager.cleanup(days=days, status=status)
    return success_response(
        data={"cleaned_count": count},
        message=f"已清理 {count} 条任务记录",
    )


# ============================================================================
# 兼容旧审查接口
# ============================================================================

@router.get("/review/{task_id}", summary="获取审查任务详情（兼容旧接口）")
async def get_review_task_compat(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """兼容旧的审查任务查询接口，返回格式与旧接口一致"""
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    output = task.get('output_data') or {}

    return success_response(data={
        "task_id": task['task_id'],
        "filename": task.get('file_name'),
        "status": task['status'],
        "progress": task.get('progress', 0),
        "progress_message": task.get('progress_message'),
        "overall_risk": output.get('overall_risk'),
        "issue_count": output.get('issue_count', 0),
        "validation_count": output.get('validation_count', 0),
        "llm_count": output.get('llm_count', 0),
        "result": output.get('result'),
        "error": task.get('error_message'),
        "create_time": task.get('create_time'),
        "start_time": task.get('start_time'),
        "end_time": task.get('end_time'),
    })


@router.post("/llm-process", summary="LLM智能处理")
async def create_llm_process_task(
    file: UploadFile = File(...),
    process_type: str = Form("extract", description="处理类型: extract/summarize/classify"),
    report_type: Optional[str] = Form(None),
    add_to_kb: bool = Form(True, description="处理后是否入库"),
    user: UserContext = Depends(get_current_user),
):
    """
    LLM智能处理任务
    - extract: 从PDF/图片提取报告数据
    - summarize: 对已入库报告生成摘要
    - classify: 自动分类标签
    """
    allowed_exts = ('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.doc', '.docx')
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持: {ext}")

    # 保存文件
    upload_dir = os.path.join(settings.upload_dir, "llm")
    os.makedirs(upload_dir, exist_ok=True)
    file_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(upload_dir, f"{file_id}_{file.filename}")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    task_id = TaskManager.create(
        task_type=TaskType.LLM_PROCESS.value,
        name=file.filename,
        input_data={
            "process_type": process_type,
            "report_type": report_type,
            "add_to_kb": add_to_kb,
        },
        file_path=file_path,
        file_name=file.filename,
        file_size=len(content),
        created_by=user.user_id,
        org_id=user.org_id,
    )

    system = get_system()
    submit_task(task_id, system, settings)
    return success_response(data={"task_id": task_id}, message="LLM处理任务已创建")