"""工具模块"""

from .helpers import (
    generate_id,
    get_timestamp,
    convert_doc_to_docx,
    detect_report_type,
    safe_float,
    safe_int,
    normalize_factor,
    parse_ratio_to_float,
    parse_floor_string,
    format_p_value_display
)
from .llm_client import (
    LLMClient,
    get_llm_client,
)
from .temp_file import (
    temp_manager,
    create_temp_file,
    cleanup_temp_file,
    register_temp_file,
)

__all__ = [
    'generate_id',
    'get_timestamp', 
    'convert_doc_to_docx',
    'detect_report_type',
    'safe_float',
    'safe_int',
    'LLMClient',
    'get_llm_client',
    'normalize_factor',
    'parse_ratio_to_float',
    'parse_floor_string',
    'format_p_value_display',
    # 临时文件管理
    'temp_manager',
    'create_temp_file',
    'cleanup_temp_file',
    'register_temp_file',
]
