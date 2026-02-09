"""
文本处理工具
============
标准化、数值解析、关键词匹配
"""

import re
from typing import Optional, Tuple, List


def normalize_text(text: str) -> str:
    """
    标准化文本（去除空格、换行、全角字符等）

    用于关键词匹配前的预处理
    """
    if not text:
        return ""

    # 1. 去除各种空白字符
    text = text.replace('\u3000', '')  # 全角空格
    text = text.replace(' ', '')
    text = text.replace('\n', '')
    text = text.replace('\t', '')
    text = text.replace('\r', '')
    text = text.replace('　', '')  # 另一种全角空格

    # 2. 统一下标字符
    subscript_map = {'₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
                     '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9'}
    for sub, num in subscript_map.items():
        text = text.replace(sub, num)

    # 3. 统一括号
    text = text.replace('（', '(').replace('）', ')')
    text = text.replace('【', '[').replace('】', ']')

    return text


def normalize_label(text: str) -> str:
    """
    标准化标签（更激进的处理，用于行/列标签匹配）
    """
    text = normalize_text(text)

    # 去除括号及其内容：结构修正系数（%） -> 结构修正系数
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\[[^\]]*\]', '', text)

    # 去除常见后缀
    text = re.sub(r'[：:]+$', '', text)

    return text


def parse_number(text: str, *,
                 allow_none: bool = True,
                 default: float = None,
                 is_percentage: bool = False) -> Optional[float]:
    """
    智能解析数值

    Args:
        text: 输入文本
        allow_none: 是否允许返回None
        default: 解析失败时的默认值
        is_percentage: 是否是百分比形式（>2的值会除以100）

    支持格式：
    - "12000" -> 12000.0
    - "12,000" -> 12000.0
    - "12000.50" -> 12000.5
    - "约12000" -> 12000.0
    - "12000元/㎡" -> 12000.0
    - "126.71㎡" -> 126.71
    - "/" "-" "无" "N/A" -> None
    - "不修正" -> 1.0
    - "108/103" -> 1.0485...
    """
    if text is None:
        return default if not allow_none else None

    if isinstance(text, (int, float)):
        result = float(text)
        if is_percentage and result > 2:
            result = result / 100
        return result

    text = str(text).strip()

    # 空值表示
    empty_values = ['/', '-', '无', 'N/A', '', '—', '——', '---', 'None', 'null', '－']
    if text in empty_values:
        return default if not allow_none else None

    # 特殊值：不修正
    if text == '不修正':
        return 1.0

    # 分数形式：108/103
    if '/' in text and text.count('/') == 1:
        parts = text.split('/')
        try:
            numerator = float(re.sub(r'[^\d.\-]', '', parts[0]))
            denominator = float(re.sub(r'[^\d.\-]', '', parts[1]))
            if denominator != 0:
                return numerator / denominator
        except (ValueError, IndexError):
            pass

    # 清理文本：去除非数字字符（保留小数点和负号）
    cleaned = re.sub(r'[^\d.\-]', '', text)

    # 处理多个小数点的情况（如 "12.000.00"）
    if cleaned.count('.') > 1:
        parts = cleaned.split('.')
        cleaned = parts[0] + '.' + ''.join(parts[1:])

    if cleaned and cleaned not in ['.', '-', '-.']:
        try:
            result = float(cleaned)
            if is_percentage and result > 2:
                result = result / 100
            return result
        except ValueError:
            pass

    return default if not allow_none else None

def parse_area(text: str) -> Tuple[Optional[float], str]:
    """
    解析面积文本，统一转换为平方米

    Returns:
        (数值_平方米, 原始单位)
        原始单位: 'sqm' | 'mu' | 'unknown'

    示例:
        "137.33㎡" → (137.33, 'sqm')
        "56.2亩" → (37466.95, 'mu')
        "137.33" → (137.33, 'sqm')
    """
    if not text:
        return None, 'unknown'

    text = str(text).strip()

    # 检测亩
    mu_match = re.search(r'([\d,.]+)\s*亩', text)
    if mu_match:
        value = float(mu_match.group(1).replace(',', ''))
        return round(value * 666.67, 2), 'mu'

    # 检测平方米/㎡
    sqm_match = re.search(r'([\d,.]+)\s*(?:㎡|平方米|m²|M²|平米)', text)
    if sqm_match:
        value = float(sqm_match.group(1).replace(',', ''))
        return value, 'sqm'

    # 纯数字，默认平方米
    value = parse_number(text)
    if value is not None:
        return value, 'sqm'

    return None, 'unknown'

def parse_floor(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析楼层信息

    支持格式：
    - "5" -> ("5", None)
    - "1-2" -> ("1-2", None) 复式
    - "1-2/18" -> ("1-2", "18")
    - "5/18" -> ("5", "18")
    - "5层/共18层" -> ("5", "18")
    - "地下1层" -> ("-1", None)
    - "B1" -> ("-1", None)

    Returns:
        (current_floor, total_floor) 都是字符串，便于存储特殊格式
    """
    if not text:
        return (None, None)

    text = str(text).strip()

    # 统一处理
    text = text.replace('Ｆ', 'F').replace('／', '/').replace('\\', '/')
    text = text.replace('层', '').replace('楼', '').replace('共', '')
    text = text.replace('F', '').replace('f', '').strip()

    # 格式: 1-2/18 (复式/总层)
    match = re.match(r'^(\d+)\s*[-~]\s*(\d+)\s*/\s*(\d+)$', text)
    if match:
        return (f"{match.group(1)}-{match.group(2)}", match.group(3))

    # 格式: 1-2 (复式，无总层)
    match = re.match(r'^(\d+)\s*[-~]\s*(\d+)$', text)
    if match:
        return (f"{match.group(1)}-{match.group(2)}", None)

    # 格式: 5/18 (当前层/总层)
    match = re.match(r'^(-?\d+)\s*/\s*(\d+)$', text)
    if match:
        return (match.group(1), match.group(2))

    # 格式: 地下1、B1、负1
    if re.search(r'(地下|负|[Bb])', text):
        m = re.search(r'(\d+)', text)
        if m:
            return (f"-{m.group(1)}", None)

    # 格式: 纯数字
    match = re.match(r'^(-?\d+)$', text)
    if match:
        return (match.group(1), None)

    # 无法解析，返回原文
    return (text, None)


def infer_floors_from_rooms(text: str) -> List[int]:
    """
    从房号推断楼层

    "101室" → [1]
    "808室" → [8]
    "101室和301室" → [1, 3]
    "101室、301室" → [1, 3]
    "北大街96号808室" → [8]

    规则：3位及以上数字房号，去掉最后两位是楼层
    """
    floors = []
    # 匹配所有房号
    room_numbers = re.findall(r'(\d{3,})\s*室', text)
    for room_no in room_numbers:
        # 去掉最后两位（单元内房间号），剩余部分是楼层
        floor_part = room_no[:-2]
        if floor_part:
            try:
                floor = int(floor_part)
                if 0 < floor < 100:
                    floors.append(floor)
            except ValueError:
                pass
    return sorted(set(floors))

# ============================================================================
# 关键词匹配
# ============================================================================

# 字段同义词映射
FIELD_SYNONYMS = {
    # 基本信息
    'address': ['地址', '坐落', '房屋坐落', '估价对象坐落'],
    'building_area': ['建筑面积', '面积', '房屋面积'],
    'transaction_price': ['交易价格', '成交价格', '交易单价', '成交单价', '成交基价'],
    'rental_price': ['租赁价格', '租金', '租金单价', '月租金', '租金价格'],
    'usage': ['用途', '房屋用途', '规划用途'],
    'structure': ['结构', '建筑结构', '房屋结构'],
    'floor': ['层次', '楼层', '所在层'],
    'orientation': ['朝向', '房屋朝向'],
    'build_year': ['建成时间', '建成年份', '建成年代', '竣工时间'],
    'data_source': ['来源', '数据来源', '案例来源'],

    # 修正系数（涉执/租金）
    'transaction_correction': ['交易情况修正', '交易情况', '交易修正'],
    'market_correction': ['市场状况修正', '市场状况', '市场修正', '市场状况调整'],
    'location_correction': ['区位状况修正', '区位状况', '区位修正', '区位状况调整'],
    'physical_correction': ['实物状况修正', '实物状况', '实物修正', '实物状况调整'],
    'rights_correction': ['权益状况修正', '权益状况', '权益修正', '权益状况调整'],
    'adjusted_price': ['修正后单价', '调整后单价', '比准价格', '修正后价格'],

    # 修正系数（标准房）
    'structure_factor': ['结构修正', '结构系数', '建筑结构修正', '结构修正系数'],
    'floor_factor': ['层次修正', '楼层修正', '楼层系数', '层次系数', '层次修正系数'],
    'orientation_factor': ['朝向修正', '朝向系数', '朝向修正系数'],
    'age_factor': ['成新修正', '新旧程度', '成新系数', '成新修正系数'],
    'east_west_factor': ['东西至修正', '东西至', '东西至修正系数'],
    'physical_composite': ['实体状况综合', '实体状况系数综合', '实体综合', 'P3实体'],

    # P系数
    'p1': ['P1', 'P1交易', '交易情况修正结果'],
    'p2': ['P2', 'P2交易日期', '交易日期修正结果', '交易日期修正'],
    'p3': ['P3', 'P3实体', '实体状况修正结果', '实体状况修正'],
    'p4': ['P4', 'P4区位', '区位状况修正结果', '区位状况修正'],

    # 其他
    'decoration_price': ['装修价格', '装修重置价', '装修档次', '装修'],
    'attachment_price': ['附属物价格', '附属物单价', '附属物'],
    'final_price': ['比准价格', '最终价格', '评估单价'],
    'composite_result': ['综合结果', 'P1×P2×P3×P4', '综合修正'],
    'vs_result': ['Vs×', 'Vs结果', 'Vs×结果'],
    'avg_listing_price': ['二手房挂牌均价', '挂牌均价', '二手房均价'],

    # 表头
    'subject': ['估价对象', '待估对象', '评估对象'],
    'case_a': ['可比实例A', '实例A', '案例A'],
    'case_b': ['可比实例B', '实例B', '案例B'],
    'case_c': ['可比实例C', '实例C', '案例C'],
    'case_d': ['可比实例D', '实例D', '案例D'],

    # 因素类别
    'location_status': ['区位状况', '区位因素'],
    'physical_status': ['实物状况', '实物因素'],
    'rights_status': ['权益状况', '权益因素'],
}


def match_field(text: str, field_name: str) -> bool:
    """
    检查文本是否匹配指定字段

    Args:
        text: 待匹配文本
        field_name: 字段名（FIELD_SYNONYMS的key）

    Returns:
        是否匹配
    """
    normalized = normalize_label(text)
    synonyms = FIELD_SYNONYMS.get(field_name, [field_name])
    return any(syn in normalized for syn in synonyms)


def find_matching_field(text: str, candidates: List[str] = None) -> Optional[str]:
    """
    查找文本匹配的字段名

    Args:
        text: 待匹配文本
        candidates: 候选字段名列表，None表示搜索全部

    Returns:
        匹配的字段名，未找到返回None
    """
    normalized = normalize_label(text)
    search_fields = candidates if candidates else FIELD_SYNONYMS.keys()

    for field_name in search_fields:
        synonyms = FIELD_SYNONYMS.get(field_name, [field_name])
        if any(syn in normalized for syn in synonyms):
            return field_name

    return None


def extract_year(text: str) -> Optional[int]:
    """
    从文本中提取年份

    支持格式：
    - "2015年" -> 2015
    - "2015.6" -> 2015
    - "2015-06" -> 2015
    - "2015年6月" -> 2015
    """
    if not text:
        return None

    # 尝试匹配4位数年份
    match = re.search(r'(19|20)\d{2}', text)
    if match:
        return int(match.group(0))

    return None


def extract_date(text: str) -> Optional[str]:
    """
    从文本中提取日期

    返回格式统一为 YYYY-MM-DD 或 YYYY-MM 或 YYYY
    """
    if not text:
        return None

    text = str(text).strip()

    # 格式: 2025年1月1日
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

    # 格式: 2025年1月
    match = re.search(r'(\d{4})年(\d{1,2})月', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}"

    # 格式: 2025-01-01 或 2025/01/01
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

    # 格式: 2025-01 或 2025/01
    match = re.search(r'(\d{4})[-/](\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}"

    # 格式: 2025.1 或 2025.01
    match = re.search(r'(\d{4})\.(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}"

    # 格式: 纯年份
    match = re.search(r'(19|20)\d{2}', text)
    if match:
        return match.group(0)

    return None