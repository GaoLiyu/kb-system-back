"""
SSE (Server-Sent Events) 实时推送
==================================

为任务进度提供实时推送，替代前端轮询。

前端使用方式:
    const es = new EventSource('/api/sse/tasks/{taskId}/stream');

    es.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('进度:', data.progress, data.progress_message);

        if (data.status === 'completed' || data.status === 'failed') {
            es.close();
        }
    };

    es.onerror = () => {
        es.close();
    };
"""

import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..iam_client import UserContext
from ..services.async_task_manager import TaskManager

router = APIRouter(prefix="/sse", tags=["实时推送"])


async def _task_event_generator(task_id: str, interval: float = 1.0):
    """
    任务进度事件生成器

    每隔 interval 秒查询一次任务进度，推送给客户端。
    当任务完成/失败/取消时，发送最终事件并结束。

    SSE 格式:
        data: {"status": "running", "progress": 45, "progress_message": "执行校验..."}

    最终事件（任务完成时附带 output_data）:
        data: {"status": "completed", "progress": 100, "output_data": {...}}
    """
    # 先确认任务存在
    task = TaskManager.get(task_id)
    if not task:
        yield f"data: {json.dumps({'error': '任务不存在'}, ensure_ascii=False)}\n\n"
        return

    # 如果任务已经结束，直接返回最终状态
    if task['status'] in ('completed', 'failed', 'cancelled'):
        event_data = {
            'status': task['status'],
            'progress': task.get('progress', 0),
            'progress_message': task.get('progress_message', ''),
        }
        if task['status'] == 'completed':
            output = task.get('output_data') or {}
            event_data['overall_risk'] = output.get('overall_risk')
            event_data['issue_count'] = output.get('issue_count', 0)
        elif task['status'] == 'failed':
            event_data['error_message'] = task.get('error_message', '')

        yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        return

    # 循环推送进度
    last_progress = -1
    last_message = ""
    max_wait = 600  # 最多等10分钟
    waited = 0

    while waited < max_wait:
        progress_info = TaskManager.get_progress(task_id)
        if not progress_info:
            yield f"data: {json.dumps({'error': '任务不存在'}, ensure_ascii=False)}\n\n"
            return

        status = progress_info['status']
        progress = progress_info['progress']
        message = progress_info['progress_message']

        # 只在有变化时推送（或者每10秒心跳一次）
        if progress != last_progress or message != last_message or waited % 10 == 0:
            event_data = {
                'status': status,
                'progress': progress,
                'progress_message': message,
            }

            # 终态
            if status in ('completed', 'failed', 'cancelled'):
                if status == 'completed':
                    full_task = TaskManager.get(task_id)
                    if full_task:
                        output = full_task.get('output_data') or {}
                        event_data['overall_risk'] = output.get('overall_risk')
                        event_data['issue_count'] = output.get('issue_count', 0)
                        event_data['validation_count'] = output.get('validation_count', 0)
                        event_data['llm_count'] = output.get('llm_count', 0)
                elif status == 'failed':
                    event_data['error_message'] = progress_info.get('error_message', '')

                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            last_progress = progress
            last_message = message

        await asyncio.sleep(interval)
        waited += interval

    # 超时
    yield f"data: {json.dumps({'error': '连接超时', 'status': 'timeout'}, ensure_ascii=False)}\n\n"


@router.get("/tasks/{task_id}/stream", summary="任务进度SSE流")
async def task_progress_stream(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """
    获取任务进度的 SSE 流

    - 前端通过 EventSource 连接此接口
    - 服务端每秒推送一次进度（有变化时）
    - 任务完成/失败时自动关闭

    Returns:
        SSE 事件流
    """
    # 权限检查
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    return StreamingResponse(
        _task_event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.get("/tasks/{task_id}/progress", summary="任务进度（单次查询）")
async def task_progress(
    task_id: str,
    user: UserContext = Depends(get_current_user),
):
    """
    获取任务当前进度（单次请求，非流式）

    兼容不支持 SSE 的场景
    """
    task = TaskManager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if 'admin' not in user.roles and task.get('created_by') != user.user_id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    return {
        "success": True,
        "task_id": task_id,
        "status": task['status'],
        "progress": task.get('progress', 0),
        "progress_message": task.get('progress_message', ''),
    }