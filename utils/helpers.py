"""
工具函数
"""

import os
import subprocess
import hashlib
from datetime import datetime
from typing import Optional


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
    """根据文件名检测报告类型"""
    filename = filename.lower()
    
    if '涉执' in filename or 'shezhi' in filename:
        return 'shezhi'
    elif '租金' in filename or 'zujin' in filename:
        return 'zujin'
    elif '标准房' in filename or 'biaozhunfang' in filename:
        return 'biaozhunfang'
    else:
        return 'shezhi'  # 默认


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
