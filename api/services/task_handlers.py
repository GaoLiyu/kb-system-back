"""
任务处理器实现
==============

包含各类任务的具体处理逻辑。
每个处理器继承 BaseTaskHandler，实现 process() 方法。

关键修复：
- 使用 task['file_name']（原始文件名）做报告类型检测，而不是临时路径
"""

import os
import traceback
from typing import Optional

from .async_task_manager import (
    TaskManager,
    BaseTaskHandler,
    TaskType,
    TaskStatus,
)


# ============================================================================
# 审查任务处理器
# ============================================================================

class ReviewTaskHandler(BaseTaskHandler):
    """
    报告审查任务处理器

    input_data:
    {
        "review_mode": "quick" | "full",
    }
    """

    def __init__(self, task_id: str, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        """执行审查任务"""
        file_path = self.task['file_path']
        file_name = self.task.get('file_name') or os.path.basename(file_path)
        input_data = self.task.get('input_data') or {}
        review_mode = input_data.get('review_mode', 'full')

        self.update_progress(5, "开始审查...")

        if review_mode == 'quick':
            self._process_quick(file_path, file_name)
        else:
            self._process_full(file_path, file_name)

    def _process_quick(self, file_path: str, file_name: str):
        """快速审查"""
        self.update_progress(20, "执行规则校验...")

        review_result = self.system.review(
            file_path, verbose=False, original_filename=file_name
        )

        self.update_progress(80, "整理结果...")

        validation_count = len(review_result.validation.issues) if review_result.validation else 0
        llm_count = len(review_result.llm_issues) if review_result.llm_issues else 0
        comparison_count = len([c for c in (review_result.comparisons or []) if c.is_abnormal])

        error_count = sum(
            1 for i in review_result.validation.issues
            if i.level in ['error', '错误']
        ) if review_result.validation else 0
        llm_major = sum(
            1 for i in review_result.llm_issues
            if i.severity in ['major', 'critical']
        ) if review_result.llm_issues else 0

        if error_count > 0 or llm_count >= 3 or comparison_count >= 3:
            overall_risk = "高风险"
        elif llm_major > 0 or validation_count > 2 or comparison_count >= 1:
            overall_risk = "中风险"
        else:
            overall_risk = "低风险"

        # 构建 comparisons
        comparisons_list = []
        for comp in (review_result.comparisons or []):
            comparisons_list.append({
                "item": comp.item,
                "current_value": comp.current_value,
                "kb_min": comp.kb_min,
                "kb_max": comp.kb_max,
                "kb_avg": comp.kb_avg,
                "is_abnormal": comp.is_abnormal,
                "description": comp.description,
            })

        result = {
            "validation_issues": [
                {"level": i.level, "category": i.category, "description": i.description}
                for i in (review_result.validation.issues if review_result.validation else [])
            ],
            "formula_checks": [
                {
                    "case_id": f.case_id, "formula_name": f.formula_name,
                    "expected": f.expected, "actual": f.actual, "is_valid": f.is_valid,
                    "inputs": getattr(f, 'inputs', None),
                }
                for f in (review_result.validation.formula_checks if review_result.validation else [])
            ],
            "llm_issues": [
                {
                    "type": i.type, "severity": i.severity,
                    "description": i.description, "suggestion": i.suggestion,
                    "span": getattr(i, 'span', None),
                    "paragraph_index": getattr(i, 'paragraph_index', None),
                }
                for i in (review_result.llm_issues or [])
            ],
            "comparisons": comparisons_list,
            "similar_cases": review_result.similar_cases or [],
            "recommendations": review_result.recommendations or [],
        }

        self.complete(output_data={
            "overall_risk": overall_risk,
            "issue_count": validation_count + llm_count + comparison_count,
            "validation_count": validation_count,
            "llm_count": llm_count,
            "comparison_count": comparison_count,
            "result": result,
        })

    def _process_full(self, file_path: str, file_name: str):
        """完整审查（带原文）"""
        from extractors import (
            extract_report, extract_document_content,
            content_to_dict, mark_issues
        )
        from validators import validate_report
        from utils import detect_report_type, convert_doc_to_docx
        from knowledge_base.kb_manager_db import result_to_dict

        self.update_progress(10, "提取文档内容...")

        # doc 转 docx
        if file_path.lower().endswith('.doc'):
            file_path = convert_doc_to_docx(file_path)

        # 提取原文
        doc_content = extract_document_content(file_path)

        # 过滤无意义段落
        doc_content.contents = [
            item for item in doc_content.contents
            if item.type != 'paragraph' or (
                item.text and
                len(item.text.strip()) > 5 and
                not item.text.strip().startswith('—')
            )
        ]
        for idx, item in enumerate(doc_content.contents):
            item.index = idx

        self.update_progress(30, "提取报告数据...")

        # 用原始文件名检测报告类型
        report_type = detect_report_type(file_name)
        extraction_result = extract_report(file_path, report_type, original_filename=file_name)

        self.update_progress(45, "执行规则校验...")

        validation_result = validate_report(extraction_result)

        self.update_progress(55, "执行语义审查...")

        # LLM 审查
        llm_issues = []
        if self.settings.enable_llm:
            try:
                if self.system.reviewer.enable_llm and self.system.reviewer.llm_reviewer:
                    if self.system.reviewer.llm_reviewer.is_available():
                        paragraphs = [
                            {'index': item.index, 'text': item.text}
                            for item in doc_content.contents
                            if item.type == 'paragraph' and item.text
                        ]

                        subject_data = result_to_dict(extraction_result).get('subject', {})
                        llm_result = self.system.reviewer.llm_reviewer.review_full_document(
                            paragraphs, report_type, subject_data
                        )
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
            except Exception as e:
                print(f"[ReviewTask] LLM审查异常: {e}")
                traceback.print_exc()

        self.update_progress(75, "知识库对比...")

        # 知识库对比
        comparisons = []
        similar_cases = []
        try:
            comparisons = self.system.reviewer._compare_with_kb(extraction_result, report_type)
            similar_cases = self.system.reviewer._find_similar(extraction_result, report_type)
        except Exception as e:
            print(f"[ReviewTask] 知识库对比异常: {e}")

        self.update_progress(85, "标记问题段落...")

        mark_issues(doc_content, llm_issues)

        # 统计
        validation_count = len(validation_result.issues) if validation_result else 0
        llm_count = len(llm_issues)
        comparison_count = len([c for c in comparisons if c.is_abnormal])

        error_count = sum(
            1 for i in validation_result.issues
            if i.level in ['error', '错误']
        ) if validation_result else 0
        llm_major = sum(
            1 for i in llm_issues
            if i.get('severity') in ['major', 'critical']
        )

        if error_count > 0 or llm_major >= 3 or comparison_count >= 3:
            overall_risk = "高风险"
        elif llm_major > 0 or validation_count > 2 or comparison_count >= 1:
            overall_risk = "中风险"
        else:
            overall_risk = "低风险"

        # comparisons 序列化
        comparisons_list = []
        for comp in comparisons:
            comparisons_list.append({
                "item": comp.item,
                "current_value": comp.current_value,
                "kb_min": comp.kb_min,
                "kb_max": comp.kb_max,
                "kb_avg": comp.kb_avg,
                "is_abnormal": comp.is_abnormal,
                "description": comp.description,
            })

        result = {
            "document_content": content_to_dict(doc_content),
            "validation_issues": [
                {"level": i.level, "category": i.category, "description": i.description}
                for i in (validation_result.issues if validation_result else [])
            ],
            "formula_checks": [
                {
                    "case_id": f.case_id, "formula_name": f.formula_name,
                    "expected": f.expected, "actual": f.actual, "is_valid": f.is_valid,
                    "inputs": getattr(f, 'inputs', None),
                }
                for f in (validation_result.formula_checks if validation_result else [])
            ],
            "llm_issues": llm_issues,
            "comparisons": comparisons_list,
            "similar_cases": similar_cases or [],
            "recommendations": [],
        }

        self.update_progress(95, "完成")

        self.complete(output_data={
            "overall_risk": overall_risk,
            "issue_count": validation_count + llm_count + comparison_count,
            "validation_count": validation_count,
            "llm_count": llm_count,
            "comparison_count": comparison_count,
            "result": result,
        })


# ============================================================================
# 知识库上传任务处理器
# ============================================================================

class UploadTaskHandler(BaseTaskHandler):
    """知识库上传任务处理器"""

    def __init__(self, task_id: str, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        file_path = self.task['file_path']
        file_name = self.task.get('file_name') or os.path.basename(file_path)
        input_data = self.task.get('input_data') or {}
        report_type = input_data.get('report_type')
        enable_vectorize = input_data.get('enable_vectorize', True)

        self.update_progress(10, "解析文档...")

        try:
            from utils import detect_report_type
            if not report_type:
                report_type = detect_report_type(file_name)

            self.update_progress(30, f"识别为{report_type}类型，提取数据...")

            doc_id = self.system.add_report(
                file_path, verbose=False, original_filename=file_name
            )

            self.update_progress(60, "数据入库完成")

            report_info = self.system.kb.get_report(doc_id)
            case_count = len(report_info.get('cases', [])) if report_info else 0
            address = report_info.get('address', '') if report_info else ''

            if enable_vectorize and self.settings.enable_vector:
                self.update_progress(70, "向量化处理中...")
                try:
                    self.system.kb.vectorize_document(doc_id)
                except Exception as e:
                    print(f"[Upload] 向量化失败: {e}")

            self.complete(
                output_data={
                    "doc_id": doc_id,
                    "report_type": report_type,
                    "case_count": case_count,
                    "address": address,
                },
                related_id=doc_id
            )

        except Exception as e:
            raise Exception(f"上传处理失败: {str(e)}")

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


# ============================================================================
# 批量上传任务处理器
# ============================================================================

class BatchUploadTaskHandler(BaseTaskHandler):
    """批量上传任务处理器"""

    def __init__(self, task_id: str, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        input_data = self.task.get('input_data') or {}
        files = input_data.get('files', [])
        report_type = input_data.get('report_type')

        if not files:
            self.fail("没有要上传的文件")
            return

        total = len(files)
        results = []
        success_count = 0
        fail_count = 0

        for idx, file_info in enumerate(files):
            file_path = file_info.get('file_path')
            file_name = file_info.get('file_name', os.path.basename(file_path))

            progress = int((idx / total) * 90) + 5
            self.update_progress(progress, f"处理 {file_name} ({idx + 1}/{total})")

            try:
                from utils import detect_report_type
                detected_type = report_type or detect_report_type(file_name)

                doc_id = self.system.add_report(
                    file_path, verbose=False, original_filename=file_name
                )

                results.append({
                    "file_name": file_name,
                    "success": True,
                    "doc_id": doc_id,
                    "report_type": detected_type,
                })
                success_count += 1

            except Exception as e:
                results.append({
                    "file_name": file_name,
                    "success": False,
                    "error": str(e),
                })
                fail_count += 1

            finally:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass

        self.complete(output_data={
            "total": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "results": results,
        })


# ============================================================================
# 导出任务处理器
# ============================================================================

class ExportTaskHandler(BaseTaskHandler):
    """导出任务处理器"""

    def __init__(self, task_id: str, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        input_data = self.task.get('input_data') or {}
        export_type = input_data.get('export_type', 'cases')
        export_format = input_data.get('format', 'xlsx')

        self.update_progress(10, f"准备导出 {export_type}...")

        if export_type == 'cases':
            result = self._export_cases(input_data, export_format)
        elif export_type == 'review_result':
            result = self._export_review_result(input_data)
        else:
            self.fail(f"不支持的导出类型: {export_type}")
            return

        self.complete(output_data=result)

    def _export_cases(self, input_data: dict, fmt: str) -> dict:
        filters = input_data.get('filters', {})
        self.update_progress(30, "查询案例数据...")

        cases = self.system.kb.list_cases(filters.get('report_type'))
        self.update_progress(60, f"导出 {len(cases)} 条案例...")

        import tempfile
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = 'xlsx' if fmt == 'xlsx' else 'csv'
        output_path = os.path.join(tempfile.gettempdir(), f"cases_export_{timestamp}.{ext}")

        if fmt == 'xlsx':
            self._to_xlsx(cases, output_path)
        else:
            self._to_csv(cases, output_path)

        return {
            "file_path": output_path,
            "file_name": os.path.basename(output_path),
            "record_count": len(cases),
        }

    def _export_review_result(self, input_data: dict) -> dict:
        review_task_id = input_data.get('task_id')
        include_original = input_data.get('include_original', False)

        if not review_task_id:
            raise ValueError("缺少审查任务ID")

        self.update_progress(30, "获取审查结果...")
        review_task = TaskManager.get(review_task_id)
        if not review_task:
            raise ValueError("审查任务不存在")
        if review_task['status'] != 'completed':
            raise ValueError("审查任务尚未完成")

        output_data = review_task.get('output_data') or {}
        result = output_data.get('result')
        if not result:
            raise ValueError("无审查结果")

        self.update_progress(60, "生成审查报告...")

        from reviewer import create_review_report, create_review_report_with_original
        import tempfile
        from datetime import datetime

        export_data = {
            "overall_risk": output_data.get("overall_risk"),
            "summary": f"发现 {output_data.get('validation_count', 0)} 个校验问题，"
                       f"{output_data.get('llm_count', 0)} 个语义问题",
            "document_content": result.get("document_content", {}),
            "validation_issues": result.get("validation_issues", []),
            "formula_checks": result.get("formula_checks", []),
            "llm_issues": result.get("llm_issues", []),
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(review_task.get("file_name", "report"))[0]
        output_filename = f"{base_name}_审查报告_{timestamp}.docx"
        output_path = os.path.join(tempfile.gettempdir(), output_filename)

        if include_original and result.get("document_content"):
            create_review_report_with_original(export_data, output_path)
        else:
            create_review_report(export_data, output_path)

        return {
            "file_path": output_path,
            "file_name": output_filename,
            "record_count": 1,
        }

    def _to_xlsx(self, data: list, path: str):
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            if data:
                headers = list(data[0].keys())
                ws.append(headers)
                for row in data:
                    ws.append([row.get(h, '') for h in headers])
            wb.save(path)
        except Exception as e:
            raise Exception(f"Excel导出失败: {e}")

    def _to_csv(self, data: list, path: str):
        import csv
        if not data:
            open(path, 'w').close()
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)


# ============================================================================
# 向量化任务处理器
# ============================================================================

class VectorizeTaskHandler(BaseTaskHandler):
    """向量化任务处理器"""

    def __init__(self, task_id, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        if not self.settings.enable_vector:
            self.fail("向量化功能未启用")
            return

        input_data = self.task.get('input_data') or {}
        report_type = input_data.get('report_type')

        self.update_progress(10, "获取案例数据...")

        # 获取所有案例
        all_cases = self.system.kb.list_cases(report_type)
        total = len(all_cases)

        if total == 0:
            self.complete(output_data={"total": 0, "message": "没有案例数据"})
            return

        self.update_progress(20, f"共 {total} 个案例，开始编码...")

        # 调用重建
        try:
            self.system.kb.rebuild_vector_index()
        except Exception as e:
            raise Exception(f"向量索引重建失败: {e}")

        self.complete(output_data={
            "total": total,
            "report_type": report_type or "全部",
        })


# ============================================================================
# LLM处理任务处理器
# ============================================================================

class LLMProcessTaskHandler(BaseTaskHandler):
    """LLM处理任务处理器"""

    def __init__(self, task_id, system, settings):
        super().__init__(task_id)
        self.system = system
        self.settings = settings

    def process(self):
        if not self.settings.enable_llm:
            self.fail("LLM功能未启用")
            return

        file_path = self.task['file_path']
        file_name = self.task.get('file_name', '')
        input_data = self.task.get('input_data') or {}
        process_type = input_data.get('process_type', 'extract')

        if process_type == 'extract':
            self._extract(file_path, file_name, input_data)
        elif process_type == 'summarize':
            self._summarize(input_data)
        elif process_type == 'classify':
            self._classify(input_data)
        else:
            self.fail(f"不支持的处理类型: {process_type}")

    def _extract(self, file_path, file_name, input_data):
        """从PDF/图片提取报告数据"""
        self.update_progress(10, "分析文件类型...")

        ext = os.path.splitext(file_name)[1].lower()
        report_type = input_data.get('report_type')
        add_to_kb = input_data.get('add_to_kb', True)

        self.update_progress(20, "LLM提取中...")

        # 根据文件类型分发
        # PDF → 先尝试文本提取，失败则 OCR
        # 图片 → OCR → LLM 结构化
        # 这里是你后续实现的核心逻辑

        # 伪代码示意：
        # if ext == '.pdf':
        #     text = extract_pdf_text(file_path)
        #     if not text:
        #         text = ocr_pdf(file_path)
        # elif ext in ('.png', '.jpg', ...):
        #     text = ocr_image(file_path)
        #
        # self.update_progress(50, "LLM结构化...")
        # structured_data = llm_extract(text, report_type)
        #
        # if add_to_kb:
        #     self.update_progress(80, "入库...")
        #     doc_id = self.system.kb.add_report_from_dict(structured_data)

        # 暂时返回未实现
        self.fail("LLM提取功能开发中", error_code="NOT_IMPLEMENTED")

    def _summarize(self, input_data):
        """对已入库报告生成摘要"""
        # doc_id = input_data.get('doc_id')
        # report = self.system.kb.get_report(doc_id)
        # summary = llm_summarize(report)
        # 更新到报告 metadata
        self.fail("摘要功能开发中", error_code="NOT_IMPLEMENTED")

    def _classify(self, input_data):
        """自动分类标签"""
        self.fail("分类功能开发中", error_code="NOT_IMPLEMENTED")

# ============================================================================
# 入口函数
# ============================================================================

def run_review_task(task_id: str, system, settings):
    """执行审查任务"""
    ReviewTaskHandler(task_id, system, settings).run()


def run_upload_task(task_id: str, system, settings):
    """执行上传任务"""
    UploadTaskHandler(task_id, system, settings).run()


def run_batch_upload_task(task_id: str, system, settings):
    """执行批量上传任务"""
    BatchUploadTaskHandler(task_id, system, settings).run()


def run_export_task(task_id: str, system, settings):
    """执行导出任务"""
    ExportTaskHandler(task_id, system, settings).run()


def run_vectorize_task(task_id, system, settings):
    """执行导出任务"""
    VectorizeTaskHandler(task_id, system, settings).run()

def run_llm_process_task(task_id, system, settings):
    """执行导出任务"""
    LLMProcessTaskHandler(task_id, system, settings).run()


def submit_task(task_id: str, system, settings):
    """提交任务到线程池（自动判断类型）"""
    task = TaskManager.get(task_id)
    if not task:
        return

    task_type = task['task_type']
    handler_map = {
        TaskType.REVIEW.value: run_review_task,
        TaskType.UPLOAD.value: run_upload_task,
        TaskType.BATCH_UPLOAD.value: run_batch_upload_task,
        TaskType.EXPORT.value: run_export_task,
        TaskType.VECTORIZE.value: run_vectorize_task,
        TaskType.LLM_PROCESS.value: run_llm_process_task,
    }

    handler = handler_map.get(task_type)
    if handler:
        TaskManager.submit(task_id, handler, system, settings)
    else:
        print(f"[Task] 未知任务类型: {task_type}")


