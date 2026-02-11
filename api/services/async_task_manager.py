"""
通用异步任务管理器
==================

提供统一的异步任务管理能力，支持多种任务类型。

任务类型:
- review: 报告审查
- upload: 知识库上传
- batch_upload: 批量上传
- vectorize: 向量化处理
- llm_process: LLM处理
- export: 导出任务

使用示例:
    from api.services import TaskManager, TaskType

    # 创建任务
    task_id = TaskManager.create(
        task_type=TaskType.REVIEW.value,
        name='报告审查',
        input_data={'review_mode': 'full'},
        file_path='/tmp/review_xxx.docx',
        file_name='租金报告004.docx',
        created_by='user_id'
    )

    # 提交执行
    from api.services import submit_task
    submit_task(task_id, system, settings)

    # 查询状态
    task = TaskManager.get(task_id)
"""

import os
import json
import uuid
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, List, Any, Callable
from enum import Enum

from knowledge_base.db_connection import pg_cursor


# ============================================================================
# 常量定义
# ============================================================================

class TaskType(str, Enum):
    """任务类型"""
    REVIEW = 'review'
    UPLOAD = 'upload'
    BATCH_UPLOAD = 'batch_upload'
    VECTORIZE = 'vectorize'
    LLM_PROCESS = 'llm_process'
    EXPORT = 'export'
    IMPORT = 'import'


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


# ============================================================================
# 线程池配置
# ============================================================================

_executor: Optional[ThreadPoolExecutor] = None


def get_executor(max_workers: int = 3) -> ThreadPoolExecutor:
    """获取线程池"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max_workers)
    return _executor


def shutdown_executor():
    """关闭线程池"""
    global _executor
    if _executor:
        _executor.shutdown(wait=False)
        _executor = None


# ============================================================================
# 任务管理器
# ============================================================================

class TaskManager:
    """
    通用任务管理器

    负责任务的创建、状态管理、查询等操作。
    使用 async_tasks 表存储。
    """

    @staticmethod
    def create(
        task_type: str,
        name: str = None,
        description: str = None,
        input_data: dict = None,
        file_path: str = None,
        file_name: str = None,
        file_size: int = None,
        related_id: str = None,
        related_type: str = None,
        priority: int = 5,
        created_by: str = None,
        org_id: str = None,
        metadata: dict = None,
    ) -> str:
        """
        创建任务

        Args:
            task_type: 任务类型 (review/upload/batch_upload/export/...)
            name: 任务名称（通常是文件名）
            description: 任务描述
            input_data: 输入参数 (JSON)
            file_path: 文件路径（临时路径）
            file_name: 原始文件名（用于类型检测）
            file_size: 文件大小
            related_id: 关联业务ID
            related_type: 关联类型
            priority: 优先级 (1-10, 越小越高)
            created_by: 创建人ID
            org_id: 组织ID
            metadata: 额外元数据

        Returns:
            task_id
        """
        task_id = uuid.uuid4().hex[:16]

        with pg_cursor() as cursor:
            cursor.execute("""
                INSERT INTO async_tasks (
                    task_id, task_type, status, priority,
                    name, description, input_data,
                    file_path, file_name, file_size,
                    related_id, related_type,
                    created_by, org_id, metadata,
                    create_time
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s
                )
            """, (
                task_id, task_type, TaskStatus.PENDING.value, priority,
                name, description,
                json.dumps(input_data, ensure_ascii=False) if input_data else None,
                file_path, file_name, file_size,
                related_id, related_type,
                created_by, org_id,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
                datetime.now()
            ))

        return task_id

    @staticmethod
    def update(
        task_id: str,
        status: str = None,
        progress: int = None,
        progress_message: str = None,
        output_data: dict = None,
        error_code: str = None,
        error_message: str = None,
        related_id: str = None,
        metadata: dict = None,
    ):
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            progress: 进度 (0-100)
            progress_message: 进度消息（SSE 会推送此消息）
            output_data: 输出数据
            error_code: 错误代码
            error_message: 错误消息
            related_id: 关联ID
            metadata: 元数据（合并到现有）
        """
        fields = []
        values = []

        if status:
            fields.append("status = %s")
            values.append(status)

            if status == TaskStatus.RUNNING.value:
                fields.append("start_time = %s")
                values.append(datetime.now())
            elif status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                fields.append("end_time = %s")
                values.append(datetime.now())
                if status == TaskStatus.COMPLETED.value:
                    fields.append("progress = 100")

        if progress is not None:
            fields.append("progress = %s")
            values.append(min(100, max(0, progress)))

        if progress_message is not None:
            fields.append("progress_message = %s")
            values.append(progress_message[:500] if progress_message else None)

        if output_data is not None:
            fields.append("output_data = %s")
            values.append(json.dumps(output_data, ensure_ascii=False))

        if error_code is not None:
            fields.append("error_code = %s")
            values.append(error_code)

        if error_message is not None:
            fields.append("error_message = %s")
            values.append(error_message)

        if related_id is not None:
            fields.append("related_id = %s")
            values.append(related_id)

        if metadata is not None:
            fields.append("metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb")
            values.append(json.dumps(metadata, ensure_ascii=False))

        if not fields:
            return

        values.append(task_id)

        with pg_cursor() as cursor:
            cursor.execute(f"""
                UPDATE async_tasks
                SET {', '.join(fields)}
                WHERE task_id = %s
            """, values)

    @staticmethod
    def get(task_id: str) -> Optional[Dict]:
        """获取任务详情"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT 
                    task_id, task_type, status, priority,
                    name, description, input_data, output_data,
                    progress, progress_message,
                    error_code, error_message,
                    related_id, related_type,
                    file_path, file_name, file_size,
                    created_by, org_id,
                    create_time, start_time, end_time,
                    metadata
                FROM async_tasks
                WHERE task_id = %s
            """, (task_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'task_id': row[0],
                'task_type': row[1],
                'status': row[2],
                'priority': row[3],
                'name': row[4],
                'description': row[5],
                'input_data': row[6],
                'output_data': row[7],
                'progress': row[8] or 0,
                'progress_message': row[9],
                'error_code': row[10],
                'error_message': row[11],
                'related_id': row[12],
                'related_type': row[13],
                'file_path': row[14],
                'file_name': row[15],
                'file_size': row[16],
                'created_by': row[17],
                'org_id': row[18],
                'create_time': row[19].isoformat() if row[19] else None,
                'start_time': row[20].isoformat() if row[20] else None,
                'end_time': row[21].isoformat() if row[21] else None,
                'metadata': row[22],
            }

    @staticmethod
    def get_progress(task_id: str) -> Optional[Dict]:
        """
        获取任务进度（轻量查询，供SSE使用）

        只查 status, progress, progress_message, error_message
        """
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT status, progress, progress_message, error_message
                FROM async_tasks
                WHERE task_id = %s
            """, (task_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                'status': row[0],
                'progress': row[1] or 0,
                'progress_message': row[2] or '',
                'error_message': row[3],
            }

    @staticmethod
    def list(
        task_type: str = None,
        status: str = None,
        created_by: str = None,
        org_id: str = None,
        related_id: str = None,
        related_type: str = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = 'create_time DESC',
    ) -> List[Dict]:
        """查询任务列表"""
        conditions = []
        params = []

        if task_type:
            conditions.append("task_type = %s")
            params.append(task_type)
        if status:
            conditions.append("status = %s")
            params.append(status)
        if created_by:
            conditions.append("created_by = %s")
            params.append(created_by)
        if org_id:
            conditions.append("org_id = %s")
            params.append(org_id)
        if related_id:
            conditions.append("related_id = %s")
            params.append(related_id)
        if related_type:
            conditions.append("related_type = %s")
            params.append(related_type)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        allowed_orders = ['create_time DESC', 'create_time ASC', 'priority ASC', 'priority DESC']
        if order_by not in allowed_orders:
            order_by = 'create_time DESC'

        params.extend([limit, offset])

        with pg_cursor(commit=False) as cursor:
            cursor.execute(f"""
                SELECT 
                    task_id, task_type, status, priority,
                    name, progress, progress_message,
                    error_message, related_id,
                    file_name, created_by,
                    create_time, start_time, end_time
                FROM async_tasks
                {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params)

            rows = cursor.fetchall()
            return [
                {
                    'task_id': row[0],
                    'task_type': row[1],
                    'status': row[2],
                    'priority': row[3],
                    'name': row[4],
                    'progress': row[5] or 0,
                    'progress_message': row[6],
                    'error_message': row[7],
                    'related_id': row[8],
                    'file_name': row[9],
                    'created_by': row[10],
                    'create_time': row[11].isoformat() if row[11] else None,
                    'start_time': row[12].isoformat() if row[12] else None,
                    'end_time': row[13].isoformat() if row[13] else None,
                }
                for row in rows
            ]

    @staticmethod
    def get_stats(
        task_type: str = None,
        created_by: str = None,
        org_id: str = None,
    ) -> Dict:
        """获取任务统计"""
        conditions = []
        params = []

        if task_type:
            conditions.append("task_type = %s")
            params.append(task_type)
        if created_by:
            conditions.append("created_by = %s")
            params.append(created_by)
        if org_id:
            conditions.append("org_id = %s")
            params.append(org_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        with pg_cursor(commit=False) as cursor:
            cursor.execute(f"""
                SELECT status, COUNT(*) 
                FROM async_tasks {where_clause}
                GROUP BY status
            """, params)
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(f"""
                SELECT task_type, COUNT(*) 
                FROM async_tasks {where_clause}
                GROUP BY task_type
            """, params)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(f"SELECT COUNT(*) FROM async_tasks {where_clause}", params)
            total = cursor.fetchone()[0]

            return {
                'total': total,
                'by_status': by_status,
                'by_type': by_type,
            }

    @staticmethod
    def delete(task_id: str) -> bool:
        """删除任务"""
        with pg_cursor() as cursor:
            cursor.execute("SELECT file_path FROM async_tasks WHERE task_id = %s", (task_id,))
            row = cursor.fetchone()

            if row and row[0] and os.path.exists(row[0]):
                try:
                    os.remove(row[0])
                except Exception:
                    pass

            cursor.execute("DELETE FROM async_tasks WHERE task_id = %s", (task_id,))
            return cursor.rowcount > 0

    @staticmethod
    def cancel(task_id: str) -> bool:
        """取消任务（仅限等待中的任务）"""
        with pg_cursor() as cursor:
            cursor.execute("""
                UPDATE async_tasks 
                SET status = %s, end_time = %s
                WHERE task_id = %s AND status = %s
            """, (TaskStatus.CANCELLED.value, datetime.now(), task_id, TaskStatus.PENDING.value))
            return cursor.rowcount > 0

    @staticmethod
    def cleanup(days: int = 30, status: str = None) -> int:
        """清理旧任务"""
        with pg_cursor() as cursor:
            if status:
                cursor.execute("""
                    DELETE FROM async_tasks 
                    WHERE create_time < NOW() - INTERVAL '%s days'
                    AND status = %s
                """, (days, status))
            else:
                cursor.execute("""
                    DELETE FROM async_tasks 
                    WHERE create_time < NOW() - INTERVAL '%s days'
                """, (days,))
            return cursor.rowcount

    @staticmethod
    def submit(task_id: str, handler_func: Callable, *args, **kwargs):
        """提交任务到线程池执行"""
        executor = get_executor()
        executor.submit(handler_func, task_id, *args, **kwargs)


# ============================================================================
# 任务处理器基类
# ============================================================================

class BaseTaskHandler:
    """
    任务处理器基类

    子类需要实现 process() 方法
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task = None

    def load_task(self) -> bool:
        """加载任务信息"""
        self.task = TaskManager.get(self.task_id)
        return self.task is not None

    def update_progress(self, progress: int, message: str = None):
        """更新进度"""
        TaskManager.update(
            self.task_id,
            progress=progress,
            progress_message=message
        )

    def complete(self, output_data: dict = None, related_id: str = None):
        """标记完成"""
        TaskManager.update(
            self.task_id,
            status=TaskStatus.COMPLETED.value,
            output_data=output_data,
            related_id=related_id
        )

    def fail(self, error_message: str, error_code: str = None):
        """标记失败"""
        TaskManager.update(
            self.task_id,
            status=TaskStatus.FAILED.value,
            error_message=error_message,
            error_code=error_code
        )

    def run(self):
        """执行任务（模板方法）"""
        if not self.load_task():
            print(f"[Task {self.task_id}] 任务不存在")
            return

        TaskManager.update(self.task_id, status=TaskStatus.RUNNING.value)

        try:
            self.process()
        except Exception as e:
            traceback.print_exc()
            self.fail(str(e))

    def process(self):
        """处理任务（子类实现）"""
        raise NotImplementedError("子类必须实现 process() 方法")