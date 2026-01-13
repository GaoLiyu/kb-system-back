"""
房地产估价报告知识库系统
========================

使用方式：
    # 构建知识库
    python main.py build -d ./data/docs
    
    # 审查新报告
    python main.py review -f 新报告.docx
    
    # 查看统计
    python main.py stats
    
    # 搜索案例
    python main.py search -k 关键词
"""

import os
import sys
import argparse

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractors import extract_report
from validators import validate_report
from knowledge_base import KnowledgeBaseManager, KnowledgeBaseQuery
from reviewer import ReportReviewer, review_report
from generator import ReportGenerator
from utils import convert_doc_to_docx, detect_report_type
from config import KB_DIR


class RealEstateKBSystem:
    """房地产估价知识库系统"""
    
    def __init__(self, kb_path: str = None, enable_llm: bool = True, enable_vector: bool = True):
        """
        初始化系统

        Args:
            kb_path: 知识库路径
            enable_llm: 是否启用LLM语义审查
            enable_vector: 是否启用向量检索
        """
        self.kb_path = kb_path or KB_DIR
        self.kb = KnowledgeBaseManager(self.kb_path, enable_vector=enable_vector)
        self.query = KnowledgeBaseQuery(self.kb)
        self.reviewer = ReportReviewer(self.kb, enable_llm=enable_llm)
        self.generator = ReportGenerator(self.kb)

    # ========================================================================
    # 知识库构建
    # ========================================================================

    def add_report(self, doc_path: str, verbose: bool = True):
        """
        添加报告到知识库

        Args:
            doc_path: 文档路径
            verbose: 是否打印详情
        """
        if verbose:
            print(f"\n📥 添加: {os.path.basename(doc_path)}")

        # 转换doc
        if doc_path.lower().endswith('.doc'):
            doc_path = convert_doc_to_docx(doc_path)

        # 检测类型
        report_type = detect_report_type(doc_path)

        # 提取
        result = extract_report(doc_path)

        # 存入知识库
        doc_id = self.kb.add_report(result, report_type)

        if verbose:
            print(f"   ✓ 类型: {report_type}")
            print(f"   ✓ 地址: {result.subject.address.value}")
            print(f"   ✓ 案例: {len(result.cases)} 个")
            print(f"   ✓ ID: {doc_id}")

        return doc_id

    def build_from_directory(self, docs_dir: str):
        """
        从目录批量构建知识库

        Args:
            docs_dir: 文档目录
        """
        print(f"\n{'='*60}")
        print(f"📦 构建知识库")
        print(f"{'='*60}")
        print(f"目录: {docs_dir}")

        success = []
        failed = []

        for filename in sorted(os.listdir(docs_dir)):
            if not filename.lower().endswith(('.doc', '.docx')):
                continue

            filepath = os.path.join(docs_dir, filename)
            try:
                self.add_report(filepath)
                success.append(filename)
            except Exception as e:
                print(f"   ❌ 失败: {filename} - {e}")
                failed.append({'file': filename, 'error': str(e)})

        # 批量导入后重建向量索引
        if self.kb.enable_vector and success:
            print(f"\n📐 重建向量索引...")
            try:
                self.kb.rebuild_vector_index()
            except Exception as e:
                print(f"   ⚠️ 向量索引构建失败: {e}")

        print(f"\n{'='*60}")
        print(f"✓ 构建完成")
        print(f"  成功: {len(success)} 个")
        print(f"  失败: {len(failed)} 个")
        print(f"  知识库: {self.kb.stats()}")

        return {'success': success, 'failed': failed}

    # ========================================================================
    # 审查功能
    # ========================================================================

    def review(self, doc_path: str, verbose: bool = True):
        """
        审查报告（基于知识库）

        Args:
            doc_path: 文档路径
            verbose: 是否打印详情
        """
        return self.reviewer.review(doc_path, verbose)

    def validate(self, doc_path: str, verbose: bool = True):
        """
        仅做基础校验（不对比知识库）

        Args:
            doc_path: 文档路径
            verbose: 是否打印详情
        """
        if verbose:
            print(f"\n🔍 校验: {os.path.basename(doc_path)}")

        # 转换doc
        if doc_path.lower().endswith('.doc'):
            doc_path = convert_doc_to_docx(doc_path)

        # 提取
        result = extract_report(doc_path)

        # 校验
        validation = validate_report(result)

        if verbose:
            print(f"   风险: {validation.risk_level}")
            print(f"   {validation.summary}")

            if validation.issues:
                for issue in validation.issues:
                    icon = "❌" if issue.level == 'error' else "⚠️"
                    print(f"   {icon} {issue.description}")

        return validation

    # ========================================================================
    # 生成辅助
    # ========================================================================

    def suggest_cases(self, address: str, area: float, report_type: str, count: int = 5):
        """
        推荐可比实例
        """
        return self.generator.suggest_cases(address, area, report_type, count)

    def get_reference(self, report_type: str):
        """
        获取参考数据
        """
        return self.generator.get_template_data(report_type)

    # ========================================================================
    # 检索
    # ========================================================================

    def search(self, keyword: str = None, report_type: str = None, limit: int = 20):
        """
        搜索案例（字段匹配）
        """
        return self.query.search_cases(keyword=keyword, report_type=report_type, limit=limit)

    def search_similar(self, query: str, report_type: str = None, top_k: int = 10):
        """
        语义相似搜索（向量检索）

        Args:
            query: 查询文本（地址、描述等）
            report_type: 报告类型过滤
            top_k: 返回数量
        """
        return self.query.find_similar_cases_by_vector(
            query=query,
            report_type=report_type,
            top_k=top_k
        )

    def search_hybrid(self, query: str = None, area: float = None,
                      district: str = None, usage: str = None,
                      report_type: str = None, top_k: int = 10):
        """
        混合搜索（向量 + 规则）
        """
        return self.query.find_similar_cases_hybrid(
            query=query,
            area=area,
            district=district,
            usage=usage,
            report_type=report_type,
            top_k=top_k
        )

    def rebuild_vector_index(self):
        """重建向量索引"""
        self.kb.rebuild_vector_index()

    def stats(self):
        """
        统计信息
        """
        return self.kb.stats()

    def list_reports(self, report_type: str = None):
        """
        列出报告
        """
        return self.kb.list_reports(report_type)


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='房地产估价报告知识库系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 构建知识库
  python main.py build -d ./data/docs
  
  # 审查新报告（对比知识库）
  python main.py review -f 新报告.docx
  
  # 仅做基础校验
  python main.py validate -f 报告.docx
  
  # 搜索案例
  python main.py search -k 武进区
  
  # 查看统计
  python main.py stats
        """
    )

    parser.add_argument('command',
                        choices=['build', 'add', 'review', 'validate', 'search', 'stats', 'list', 'demo', 'clear'],
                        help='命令')
    parser.add_argument('-f', '--file', help='文件路径')
    parser.add_argument('-d', '--dir', help='目录路径')
    parser.add_argument('-k', '--keyword', help='搜索关键词')
    parser.add_argument('-t', '--type', help='报告类型 (shezhi/zujin/biaozhunfang)')
    parser.add_argument('--kb', default=None, help='知识库路径')

    args = parser.parse_args()

    # 初始化系统
    system = RealEstateKBSystem(kb_path=args.kb)

    if args.command == 'build':
        if args.dir:
            system.build_from_directory(args.dir)
        else:
            print("请指定目录: -d ./data/docs")

    elif args.command == 'add':
        if args.file:
            system.add_report(args.file)
        else:
            print("请指定文件: -f 报告.docx")

    elif args.command == 'review':
        if args.file:
            system.review(args.file)
        else:
            print("请指定文件: -f 报告.docx")

    elif args.command == 'validate':
        if args.file:
            system.validate(args.file)
        else:
            print("请指定文件: -f 报告.docx")

    elif args.command == 'search':
        results = system.search(keyword=args.keyword, report_type=args.type)
        print(f"\n找到 {len(results)} 个案例:")
        for r in results[:10]:
            addr = r.get('address', {}).get('value', '未知')
            price = r.get('transaction_price', {}).get('value') or \
                    r.get('rental_price', {}).get('value') or \
                    r.get('final_price', {}).get('value') or 0
            print(f"  - {addr}: {price:.0f}元/㎡")

    elif args.command == 'stats':
        print(f"\n知识库统计: {system.stats()}")

    elif args.command == 'list':
        reports = system.list_reports(report_type=args.type)
        print(f"\n报告列表 ({len(reports)} 个):")
        for r in reports:
            print(f"  [{r['report_type']}] {r['address']} ({r['case_count']}案例)")

    elif args.command == 'demo':
        print("\n" + "="*60)
        print("演示模式")
        print("="*60)

        # 构建知识库
        docs_dir = "./data/docs"
        if os.path.exists(docs_dir):
            system.build_from_directory(docs_dir)

            # 审查每个文档
            print("\n" + "="*60)
            print("审查所有文档")
            print("="*60)
            for filename in sorted(os.listdir(docs_dir)):
                if filename.endswith('.docx'):
                    system.review(os.path.join(docs_dir, filename))

    elif args.command == 'clear':
        print("\n" + "="*60)
        print("清空知识库")
        print("="*60)
        system.kb.clear()


if __name__ == "__main__":
    main()
