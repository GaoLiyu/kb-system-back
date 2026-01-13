"""
全局配置
"""

import os

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
KB_DIR = os.path.join(BASE_DIR, "knowledge_base", "storage")

# 报告类型
REPORT_TYPES = {
    'shezhi': {
        'name': '涉执报告',
        'keywords': ['涉执', 'shezhi'],
        'case_count': 3,
        'price_unit': '元/㎡',
    },
    'zujin': {
        'name': '租金报告',
        'keywords': ['租金', 'zujin'],
        'case_count': 3,
        'price_unit': '元/㎡·年',
    },
    'biaozhunfang': {
        'name': '标准房报告',
        'keywords': ['标准房', 'biaozhunfang'],
        'case_count': 4,
        'price_unit': '元/㎡',
    },
}

# 校验配置
VALIDATION_CONFIG = {
    'correction_range': (0.7, 1.3),      # 修正系数合理范围
    'formula_tolerance': 10,              # 公式误差容忍度
    'min_case_count': 3,                  # 最少可比实例数
}

# 知识库配置
KB_CONFIG = {
    'similarity_threshold': 0.8,          # 相似度阈值
    'max_similar_cases': 10,              # 最多返回相似案例数
}
