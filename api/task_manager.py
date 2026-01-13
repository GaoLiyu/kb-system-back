"""
异步任务管理器
=============
使用线程池处理审查任务
"""

import os
import uuid
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, List, Any

from knowledge_base.db_connection import pg_cursor


# 线程池(3个任务)
executor = ThreadPoolExecutor(max_workers=3)


class ReviewTaskManager:
    """审查任务管理器"""

    @staticmethod
    def create_task(filename: str, file_path: str, review_mode: str = "full") -> str:
        """
        创建审查任务

        Args:
            filename: 文件名
            file_path: 文件保存路径
            review_mode: 审查模式 (quick/full/detail)

        Returns:
            task_id
        """
        task_id = uuid.uuid4().hex[:16]

        with pg_cursor() as cursor:
            cursor.execute("""
                INSERT INTO review_tasks (task_id, filename, file_path, review_mode, status, create_time)
                VALUES (%s, %s, %s, %s, 'pending', %s)
            """, (task_id, filename, file_path, review_mode, datetime.now()))

        return task_id

    @staticmethod
    def update_status(task_id: str, status: str, **kwargs):
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 状态 (pending/running/completed/failed)
            **kwargs: 其他字段 (overall_risk, issue_count, result, error, etc.)
        """
        fields = ["status = %s"]
        values = [status]

        if status == "running":
            fields.append("start_time = %s")
            values.append(datetime.now())
        elif status in ("completed", "failed"):
            fields.append("end_time = %s")
            values.append(datetime.now())

        for key, value in kwargs.items():
            if key in ("overall_risk", "issue_count", "validation_count", "llm_count", "result", "error"):
                fields.append(f"{key} = %s")
                if key == "result":
                    import json
                    values.append(json.dumps(value, ensure_ascii=False) if value else None)
                else:
                    values.append(value)

        values.append(task_id)

        with pg_cursor() as cursor:
            cursor.execute(f"""
                UPDATE review_tasks
                SET {', '.join(fields)}
                WHERE task_id = %s
            """, values)

    @staticmethod
    def get_task(task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        with pg_cursor(commit=False) as cursor:
            cursor.execute("""
                           SELECT task_id, filename, file_path, review_mode, status,
                                  overall_risk, issue_count, validation_count, llm_count,
                                  result, error, create_time, start_time, end_time
                           FROM review_tasks
                           WHERE task_id = %s
                           """, (task_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "task_id": row[0],
                "filename": row[1],
                "file_path": row[2],
                "review_mode": row[3],
                "status": row[4],
                "overall_risk": row[5],
                "issue_count": row[6],
                "validation_count": row[7],
                "llm_count": row[8],
                "result": row[9],
                "error": row[10],
                "create_time": row[11].isoformat() if row[11] else None,
                "start_time": row[12].isoformat() if row[12] else None,
                "end_time": row[13].isoformat() if row[13] else None,
            }

    @staticmethod
    def list_tasks(status: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """获取任务列表"""
        with pg_cursor(commit=False) as cursor:
            if status:
                cursor.execute("""
                               SELECT task_id, filename, review_mode, status,
                                      overall_risk, issue_count, error, create_time, end_time
                               FROM review_tasks
                               WHERE status = %s
                               ORDER BY create_time DESC
                               LIMIT %s OFFSET %s
                               """, (status, limit, offset))
            else:
                cursor.execute("""
                               SELECT task_id, filename, review_mode, status,
                                      overall_risk, issue_count, error, create_time, end_time
                               FROM review_tasks
                               ORDER BY create_time DESC
                               LIMIT %s OFFSET %s
                               """, (limit, offset))

            rows = cursor.fetchall()
            return [
                {
                    "task_id": row[0],
                    "filename": row[1],
                    "review_mode": row[2],
                    "status": row[3],
                    "overall_risk": row[4],
                    "issue_count": row[5],
                    "error": row[6],
                    "create_time": row[7].isoformat() if row[7] else None,
                    "end_time": row[8].isoformat() if row[8] else None,
                }
                for row in rows
            ]

    @staticmethod
    def get_stats() -> Dict:
        """获取任务统计"""
        with pg_cursor(commit=False) as cursor:
            # 按状态统计
            cursor.execute("""
                           SELECT status, COUNT(*) FROM review_tasks GROUP BY status
                           """)
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            # 按风险统计（已完成的）
            cursor.execute("""
                           SELECT overall_risk, COUNT(*) FROM review_tasks
                           WHERE status = 'completed' AND overall_risk IS NOT NULL
                           GROUP BY overall_risk
                           """)
            by_risk = {row[0]: row[1] for row in cursor.fetchall()}

            # 总数
            cursor.execute("SELECT COUNT(*) FROM review_tasks")
            total = cursor.fetchone()[0]

            return {
                "total": total,
                "by_status": by_status,
                "by_risk": by_risk,
            }

    @staticmethod
    def delete_task(task_id: str) -> bool:
        """删除任务"""
        with pg_cursor() as cursor:
            # 获取文件路径
            cursor.execute("SELECT file_path FROM review_tasks WHERE task_id = %s", (task_id,))
            row = cursor.fetchone()

            if row and row[0] and os.path.exists(row[0]):
                try:
                    os.remove(row[0])
                except:
                    pass

            cursor.execute("DELETE FROM review_tasks WHERE task_id = %s", (task_id,))
            return cursor.rowcount > 0

    @staticmethod
    def cleanup_old_tasks(days: int = 30):
        """清理旧任务"""
        with pg_cursor() as cursor:
            cursor.execute("""
                        DELETE FROM review_tasks
                        WHERE create_time < NOW() - INTERVAL '%s days'
                    """, (days,))
            return cursor.rowcount


def run_review_task(task_id: str, system, settings):
    """
    执行审查任务（在线程池中运行）

    Args:
        task_id: 任务ID
        system: RealEstateKBSystem 实例
        settings: API 配置
    """
    task = ReviewTaskManager.get_task(task_id)
    if not task:
        return

    file_path = task["file_path"]
    review_mode = task["review_mode"]

    # 更新为运行中
    ReviewTaskManager.update_status(task_id, "running")

    try:
        if review_mode == 'quick':
            # 快速审查
            review_result = system.review(file_path, verbose=False)

            validation_count = len(review_result.validation.issues) if review_result.validation else 0
            llm_count = len(review_result.llm_issues) if review_result.llm_issues else 0

            # 计算风险
            error_count = sum(1 for i in review_result.validation.issues if i.level in ['error', '错误']) if review_result.validation else 0
            llm_major = sum(1 for i in review_result.llm_issues if i.severity in ['major', 'critical']) if review_result.llm_issues else 0

            if error_count > 0 or llm_count >= 3:
                overall_risk = "高风险"
            elif llm_major > 0 or validation_count > 2:
                overall_risk = "中风险"
            else:
                overall_risk = "低风险"

            result = {
                "extraction": {
                    "subject": {
                        "address": review_result.extraction.subject.address.value if review_result.extraction else None,
                    },
                    "case_count": len(review_result.extraction.cases) if review_result.extraction else 0,
                },
                "validation_issues": [
                    {"level": i.level, "category": i.category, "description": i.description}
                    for i in (review_result.validation.issues if review_result.validation else [])
                ],
                "llm_issues": [
                    {"type": i.type, "severity": i.severity, "description": i.description, "suggestion": i.suggestion}
                    for i in (review_result.llm_issues or [])
                ],
            }

        else:
            # 完整审查（带原文）
            from extractors import (
                extract_document_content,
                content_to_dict,
                get_filtered_paragraphs_for_review,
                mark_issues
            )
            from utils import detect_report_type
            from reviewer.llm_reviewer import LLMReviewer

            # 提取原文
            doc_content = extract_document_content(file_path)
            paragraphs = get_filtered_paragraphs_for_review(doc_content, max_count=100)

            # 规则校验
            validation_result = system.validate(file_path, verbose=False)

            # LLM 段落审查
            report_type = detect_report_type(file_path)
            llm_issues = []

            if settings.enable_llm and paragraphs:
                reviewer = LLMReviewer()
                if reviewer.is_available():
                    llm_result = reviewer.review_paragraphs(paragraphs, report_type)
                    llm_issues = [
                        {
                            "type": issue.type,
                            "severity": issue.severity,
                            "description": issue.description,
                            "span": issue.span,
                            "suggestion": issue.suggestion,
                            "paragraph_index": issue.paragraph_index,
                        }
                        for issue in llm_result.issues
                        if issue.paragraph_index is not None
                    ]

            # 标记问题段落
            mark_issues(doc_content, llm_issues)

            validation_count = len(validation_result.issues) if validation_result else 0
            llm_count = len(llm_issues)

            # 计算风险
            error_count = sum(
                1 for i in validation_result.issues if i.level in ['error', '错误']) if validation_result else 0
            llm_major = sum(1 for i in llm_issues if i.get('severity') in ['major', 'critical'])

            if error_count > 0 or llm_major >= 3:
                overall_risk = "高风险"
            elif llm_major > 0 or validation_count > 2:
                overall_risk = "中风险"
            else:
                overall_risk = "低风险"

            result = {
                "document_content": content_to_dict(doc_content),
                "validation_issues": [
                    {"level": i.level, "category": i.category, "description": i.description}
                    for i in (validation_result.issues if validation_result else [])
                ],
                "formula_checks": [
                    {"case_id": f.case_id, "expected": f.expected, "actual": f.actual, "is_valid": f.is_valid}
                    for f in (validation_result.formula_checks if validation_result else [])
                ],
                "llm_issues": llm_issues,
            }

        # 更新为完成
        ReviewTaskManager.update_status(
            task_id,
            "completed",
            overall_risk=overall_risk,
            issue_count=validation_count + llm_count,
            validation_count=validation_count,
            llm_count=llm_count,
            result=result
        )

    except Exception as e:
        traceback.print_exc()
        ReviewTaskManager.update_status(
            task_id,
            "failed",
            error=str(e)
        )

    finally:
        # 清理临时文件
        pass


def submit_review_task(task_id: str, system, settings):
    """提交任务到线程池"""
    executor.submit(run_review_task, task_id, system, settings)