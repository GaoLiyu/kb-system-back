"""
统计接口
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List
from fastapi import APIRouter, Depends

from knowledge_base.db_connection import pg_cursor
from .kb import get_system
from ..auth import get_current_user, require_roles
from ..iam_client import UserContext
from ..config import settings

router = APIRouter(prefix="/stats", tags=["统计"])


@router.get("/overview", summary="总览统计")
async def get_overview_stats(user: UserContext = Depends(get_current_user)):
    """
    获取知识库总览统计
    """
    system = get_system()
    kb_stats = system.kb.stats()

    return {
        "success": True,
        "total_reports": kb_stats.get("total_reports", 0),
        "total_cases": kb_stats.get("total_cases", 0),
        "by_type": kb_stats.get("by_type", {}),
        "vector_index": kb_stats.get("vector_index", {}),
    }


@router.get("/reports", summary="报告统计")
async def get_report_stats(user: UserContext = Depends(get_current_user)):
    """
    获取报告详细统计
    """
    system = get_system()
    reports = system.kb.list_reports()

    # 按类型统计
    by_type = {}
    for r in reports:
        t = r.get("report_type", "未知")
        by_type[t] = by_type.get(t, 0) + 1

    # 按月统计（最近12个月）
    by_month = {}
    now = datetime.now()
    for i in range(12):
        month = (now - timedelta(days=30 * i)).strftime("%Y-%m")
        by_month[month] = 0

    for r in reports:
        create_time = r.get("create_time", "")
        if create_time:
            month = create_time[:7]  # YYYY-MM
            if month in by_month:
                by_month[month] += 1

    # 按月排序
    by_month_sorted = dict(sorted(by_month.items()))

    return {
        "success": True,
        "total": len(reports),
        "by_type": by_type,
        "by_month": by_month_sorted,
    }


@router.get("/cases", summary="案例统计")
async def get_case_stats(user: UserContext = Depends(get_current_user)):
    """
    获取案例详细统计
    """
    system = get_system()

    # 从数据库查询案例统计
    with pg_cursor(commit=False) as cursor:
        # 总数
        cursor.execute("SELECT COUNT(*) FROM cases")
        total = cursor.fetchone()[0]

        # 按类型统计
        cursor.execute("""
            SELECT report_type, COUNT(*) 
            FROM cases 
            GROUP BY report_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # 按区域统计
        cursor.execute("""
            SELECT district, COUNT(*) 
            FROM cases 
            WHERE district IS NOT NULL AND district != ''
            GROUP BY district
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)
        by_district = {row[0]: row[1] for row in cursor.fetchall()}

        # 价格分布
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN price < 5000 THEN '5000以下'
                    WHEN price < 10000 THEN '5000-10000'
                    WHEN price < 15000 THEN '10000-15000'
                    WHEN price < 20000 THEN '15000-20000'
                    WHEN price < 30000 THEN '20000-30000'
                    ELSE '30000以上'
                END as price_range,
                COUNT(*)
            FROM cases
            WHERE price > 0
            GROUP BY price_range
            ORDER BY MIN(price)
        """)
        price_distribution = {row[0]: row[1] for row in cursor.fetchall()}

    return {
        "success": True,
        "total": total,
        "by_type": by_type,
        "by_district": by_district,
        "price_distribution": price_distribution,
    }


@router.get("/review", summary="审查统计")
async def get_review_stats(user: UserContext = Depends(get_current_user)):
    """
    获取审查任务统计
    """
    with pg_cursor(commit=False) as cursor:
        # 总数
        cursor.execute("SELECT COUNT(*) FROM review_tasks")
        total = cursor.fetchone()[0]

        # 按状态统计
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM review_tasks 
            GROUP BY status
        """)
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # 按风险等级统计
        cursor.execute("""
            SELECT overall_risk, COUNT(*) 
            FROM review_tasks 
            WHERE overall_risk IS NOT NULL
            GROUP BY overall_risk
        """)
        by_risk = {row[0]: row[1] for row in cursor.fetchall()}

        # 最近7天趋势
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) 
            FROM review_tasks 
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        recent_trend = {str(row[0]): row[1] for row in cursor.fetchall()}

    return {
        "success": True,
        "total": total,
        "by_status": by_status,
        "by_risk": by_risk,
        "recent_trend": recent_trend,
    }


@router.get("/dashboard", summary="仪表盘数据")
async def get_dashboard_data(user: UserContext = Depends(get_current_user)):
    """
    获取仪表盘综合数据
    """
    system = get_system()
    kb_stats = system.kb.stats()

    # 审查任务统计
    with pg_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM review_tasks
        """)
        row = cursor.fetchone()
        review_stats = {
            "total": row[0],
            "pending": row[1],
            "completed": row[2],
            "failed": row[3],
        }

        # 今日新增
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM reports WHERE DATE(create_time) = CURRENT_DATE) as new_reports,
                (SELECT COUNT(*) FROM review_tasks WHERE DATE(created_at) = CURRENT_DATE) as new_tasks
        """)
        row = cursor.fetchone()
        today_stats = {
            "new_reports": row[0],
            "new_tasks": row[1],
        }

    return {
        "success": True,
        "kb": {
            "total_reports": kb_stats.get("total_reports", 0),
            "total_cases": kb_stats.get("total_cases", 0),
            "by_type": kb_stats.get("by_type", {}),
        },
        "review": review_stats,
        "today": today_stats,
        "vector_index": kb_stats.get("vector_index", {}),
    }
