"""
工具函数
"""

import os
import subprocess
import hashlib
from datetime import datetime
from typing import Optional, Dict


def generate_id(prefix: str = "doc") -> str:
    """生成唯一ID"""
    hash_str = hashlib.md5(f"{prefix}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    return f"{prefix}_{hash_str}"


def get_timestamp() -> str:
    """获取时间戳"""
    return datetime.now().isoformat()


def convert_doc_to_docx(doc_path: str) -> str:
    """
    将doc转换为docx
    需要安装: sudo apt install libreoffice
    """
    if not doc_path.lower().endswith('.doc'):
        return doc_path
    
    # 检查是否已有docx
    docx_path = doc_path + 'x'
    if os.path.exists(docx_path):
        return docx_path
    
    # 转换
    output_dir = os.path.dirname(doc_path) or '.'
    try:
        subprocess.run([
            'libreoffice', '--headless', '--convert-to', 'docx',
            '--outdir', output_dir, doc_path
        ], check=True, capture_output=True)
        
        base_name = os.path.splitext(os.path.basename(doc_path))[0]
        converted_path = os.path.join(output_dir, f"{base_name}.docx")
        
        if os.path.exists(converted_path):
            print(f"   ✓ 已将 {os.path.basename(doc_path)} 转换为 docx")
            return converted_path
    except FileNotFoundError:
        print(f"   ⚠️ 未安装libreoffice，无法转换doc文件")
    except Exception as e:
        print(f"   ⚠️ doc转换失败: {e}")
    
    return doc_path


def detect_report_type(filename: str) -> str:
    """
    根据文件名检测报告类型

    支持的类型：
    - biaozhunfang: 税务标准房
    - zujin: 租金评估
    - shezhi: 涉执报告
    - sifa: 司法评估（使用shezhi提取器+偏移）
    - xianzhi: 市场价值-现状价值（批量评估）
    """
    filename = filename.lower()

    # 税务标准房
    if '标准房' in filename or 'biaozhunfang' in filename or '电梯多层' in filename or '税务' in filename:
        return 'biaozhunfang'

    # 租金评估
    elif '租金' in filename or 'zujin' in filename:
        return 'zujin'

    # 市场价值-现状价值（批量评估）
    elif '现值' in filename or '现状价值' in filename or '市场价值' in filename or 'xianzhi' in filename:
        return 'xianzhi'

    # 司法评估（人民法院）
    elif '司法' in filename or '人民法院' in filename or 'sifa' in filename:
        return 'sifa'

    # 涉执报告
    elif '涉执' in filename or 'shezhi' in filename:
        return 'shezhi'

    else:
        return 'biaozhunfang'  # 默认


def safe_float(value, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    if value is None:
        return default
    try:
        return float(value)
    except:
        return default


def safe_int(value, default: int = 0) -> int:
    """安全转换为整数"""
    if value is None:
        return default
    try:
        return int(value)
    except:
        return default


def normalize_factor(value: float) -> float:
    """
    标准化因素系数为小数形式

    - 输入 108 -> 输出 1.08 (百分比形式)
    - 输入 1.08 -> 输出 1.08 (已经是小数)
    - 输入 0.96 -> 输出 0.96 (已经是小数)

    判断逻辑：
    - 如果值 > 2，认为是百分比，需要除以100
    - 如果值 <= 2，认为已经是小数
    """
    if value is None:
        return 1.0

    if value > 2:  # 百分比形式 (如 96, 100, 108)
        return value / 100
    else:  # 已经是小数形式 (如 0.96, 1.00, 1.08)
        return value


def parse_ratio_to_float(val, *, precision=6) -> Optional[float]:
    """
    解析各种格式的修正系数

    支持格式：
    - 数字: 1.05, 105
    - 分数: '108/103'
    - 特殊值: '不修正' -> 1.0
    """
    if val is None:
        return None

    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s:
        return None

    # 特殊值处理
    if s in ('不修正', '无修正', '-', '—'):
        return 1.0

    # 分数格式: '108/103'
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            a = float(a.strip())
            b = float(b.strip())
            if b == 0:
                return None
            return round(a / b, precision)
        except ValueError:
            return None

    # 普通数字
    try:
        v = float(s)
        # 如果 > 10，可能是百分比形式
        if v > 10:
            return round(v / 100, precision)
        return v
    except ValueError:
        return None

def parse_floor_string(floor_str: str) -> Dict:
        """
        解析楼层字符串，支持复式格式

        支持格式：
        - '5' -> current: 5
        - '5/18' -> current: 5, total: 18
        - '1-2/2' -> current: '1-2', total: 2, is_duplex: True
        - '-1' -> current: -1 (地下室)
        """
        result = {
            'raw': floor_str,
            'current': None,
            'total': None,
            'is_duplex': False,
            'is_basement': False,
        }

        if not floor_str:
            return result

        floor_str = str(floor_str).strip()

        # 检查是否有总楼层信息 (current/total 格式)
        if '/' in floor_str:
            parts = floor_str.split('/')
            current_part = parts[0].strip()
            total_part = parts[1].strip() if len(parts) > 1 else ''

            # 解析总楼层
            try:
                result['total'] = int(total_part)
            except ValueError:
                pass
        else:
            current_part = floor_str

        # 解析当前楼层
        # 检查是否是复式 (如 '1-2')
        if '-' in current_part and not current_part.startswith('-'):
            # 复式楼层
            result['is_duplex'] = True
            result['current'] = current_part  # 保存原始字符串

            # 尝试解析复式的起始和结束楼层
            duplex_parts = current_part.split('-')
            try:
                result['duplex_start'] = int(duplex_parts[0].strip())
                result['duplex_end'] = int(duplex_parts[1].strip())
            except (ValueError, IndexError):
                pass
        else:
            # 普通楼层
            try:
                current_int = str(current_part)
                result['current'] = current_int
                result['is_basement'] = int(current_int) < 0
            except ValueError:
                result['current'] = current_part  # 无法解析，保留原始字符串

        return result


def format_p_value_display(val) -> str:
    """
    格式化 P 值用于展示

    输入: '108/103' -> 输出: '108/103 (≈1.0485)'
    输入: '不修正' -> 输出: '不修正 (=1.0)'
    输入: 1.05 -> 输出: '1.0500'
    """
    if val is None:
        return '-'

    s = str(val).strip()
    calculated = parse_ratio_to_float(val)

    if s in ('不修正', '无修正'):
        return f'{s} (=1.0)'
    elif '/' in s and calculated is not None:
        return f'{s} (≈{calculated:.4f})'
    elif calculated is not None:
        return f'{calculated:.4f}'
    else:
        return s