"""
输入表单定义
============
定义生成报告所需的用户输入字段
"""

from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum


class ReportType(Enum):
    """报告类型"""
    SHEZHI = "shezhi"           # 涉执报告
    ZUJIN = "zujin"             # 租金报告
    BIAOZHUNFANG = "biaozhunfang"  # 标准房报告


class PropertyUsage(Enum):
    """物业用途"""
    RESIDENTIAL = "住宅"
    COMMERCIAL = "商业"
    OFFICE = "办公"
    INDUSTRIAL = "工业"
    OTHER = "其他"


class Orientation(Enum):
    """朝向"""
    SOUTH = "南"
    NORTH = "北"
    EAST = "东"
    WEST = "西"
    SOUTHEAST = "东南"
    SOUTHWEST = "西南"
    NORTHEAST = "东北"
    NORTHWEST = "西北"
    EAST_WEST = "东西"
    NORTH_SOUTH = "南北"


class Decoration(Enum):
    """装修状况"""
    ROUGH = "毛坯"
    SIMPLE = "简装"
    STANDARD = "精装"
    LUXURY = "豪装"


class Structure(Enum):
    """建筑结构"""
    STEEL_CONCRETE = "钢混"
    BRICK_CONCRETE = "砖混"
    STEEL = "钢结构"
    BRICK_WOOD = "砖木"
    OTHER = "其他"


@dataclass
class SubjectInput:
    """
    估价对象输入
    ===========
    用户必须填写的估价对象信息
    """
    
    # ========== 必填字段 ==========
    
    address: str = ""
    """估价对象地址（必填）- 例：常州市武进区XX路XX号XX室"""
    
    building_area: float = 0.0
    """建筑面积（必填）- 单位：㎡"""
    
    usage: str = "住宅"
    """用途（必填）- 住宅/商业/办公/工业/其他"""
    
    report_type: str = "shezhi"
    """报告类型（必填）- shezhi/zujin/biaozhunfang"""
    
    appraisal_purpose: str = ""
    """估价目的（必填）- 例：为人民法院确定财产处置参考价提供参考依据"""
    
    value_date: str = ""
    """价值时点（必填）- 格式：YYYY-MM-DD"""
    
    # ========== 重要字段（推荐填写）==========
    
    district: str = ""
    """区域（推荐）- 例：武进区、天宁区"""
    
    street: str = ""
    """街道/镇（推荐）- 例：湖塘镇、雪堰镇"""
    
    current_floor: int = 0
    """所在楼层（推荐）- 例：8"""
    
    total_floor: int = 0
    """总楼层（推荐）- 例：18"""
    
    build_year: int = 0
    """建成年份（推荐）- 例：2015"""
    
    orientation: str = ""
    """朝向（推荐）- 南/北/东/西/东南/西南/东北/西北"""
    
    # ========== 可选字段 ==========
    
    structure: str = ""
    """建筑结构（可选）- 钢混/砖混/钢结构/砖木"""
    
    decoration: str = ""
    """装修状况（可选）- 毛坯/简装/精装/豪装"""
    
    cert_no: str = ""
    """产权证号（可选）- 例：苏(2023)常州市不动产权第XXXX号"""
    
    owner: str = ""
    """权利人（可选）- 例：张三"""
    
    land_type: str = ""
    """土地类型（可选）- 出让/划拨"""
    
    land_end_date: str = ""
    """土地使用权终止日期（可选）- 格式：YYYY-MM-DD"""
    
    # ========== 估价结果（如已知）==========
    
    estimated_price: float = 0.0
    """预估单价（可选）- 如果有参考价格"""


@dataclass
class GenerateRequest:
    """
    生成请求
    ========
    包含估价对象信息和生成选项
    """
    
    subject: SubjectInput = field(default_factory=SubjectInput)
    """估价对象信息"""
    
    case_count: int = 3
    """可比实例数量 - 默认3个"""
    
    auto_select_cases: bool = True
    """是否自动从知识库选择可比实例"""
    
    selected_case_ids: List[str] = field(default_factory=list)
    """手动选择的可比实例ID（当auto_select_cases=False时使用）"""
    
    template_doc_id: str = ""
    """模板文档ID（可选）- 指定使用哪个文档作为格式模板"""


# ============================================================================
# 字段验证
# ============================================================================

def validate_subject_input(subject: SubjectInput) -> List[str]:
    """
    验证输入字段
    
    Args:
        subject: 估价对象输入
    
    Returns:
        错误信息列表，空列表表示验证通过
    """
    errors = []
    
    # 必填字段验证
    if not subject.address:
        errors.append("地址不能为空")
    
    if subject.building_area <= 0:
        errors.append("建筑面积必须大于0")
    
    if not subject.usage:
        errors.append("用途不能为空")
    
    if not subject.report_type:
        errors.append("报告类型不能为空")
    elif subject.report_type not in ['shezhi', 'zujin', 'biaozhunfang']:
        errors.append(f"无效的报告类型: {subject.report_type}")
    
    if not subject.appraisal_purpose:
        errors.append("估价目的不能为空")
    
    if not subject.value_date:
        errors.append("价值时点不能为空")
    
    # 推荐字段提醒（不算错误，但返回警告）
    warnings = []
    if not subject.district:
        warnings.append("建议填写区域，有助于匹配更准确的可比实例")
    
    if subject.current_floor <= 0:
        warnings.append("建议填写楼层信息")
    
    if subject.build_year <= 0:
        warnings.append("建议填写建成年份")
    
    return errors


def get_field_descriptions() -> dict:
    """获取字段说明，用于前端展示"""
    return {
        'address': {
            'label': '估价对象地址',
            'required': True,
            'placeholder': '例：常州市武进区XX路XX号XX室',
            'help': '请填写完整的房产地址',
        },
        'building_area': {
            'label': '建筑面积(㎡)',
            'required': True,
            'placeholder': '例：126.71',
            'help': '以产权证载明的面积为准',
        },
        'usage': {
            'label': '用途',
            'required': True,
            'options': ['住宅', '商业', '办公', '工业', '其他'],
            'help': '房产的规划用途',
        },
        'report_type': {
            'label': '报告类型',
            'required': True,
            'options': [
                {'value': 'shezhi', 'label': '涉执报告（司法处置）'},
                {'value': 'zujin', 'label': '租金报告'},
                {'value': 'biaozhunfang', 'label': '标准房报告'},
            ],
        },
        'appraisal_purpose': {
            'label': '估价目的',
            'required': True,
            'placeholder': '例：为人民法院确定财产处置参考价提供参考依据',
        },
        'value_date': {
            'label': '价值时点',
            'required': True,
            'type': 'date',
            'help': '估价基准日期',
        },
        'district': {
            'label': '区域',
            'required': False,
            'placeholder': '例：武进区',
            'help': '所在区/县，用于匹配相似案例',
        },
        'street': {
            'label': '街道/镇',
            'required': False,
            'placeholder': '例：湖塘镇',
        },
        'current_floor': {
            'label': '所在楼层',
            'required': False,
            'type': 'number',
            'placeholder': '例：8',
        },
        'total_floor': {
            'label': '总楼层',
            'required': False,
            'type': 'number',
            'placeholder': '例：18',
        },
        'build_year': {
            'label': '建成年份',
            'required': False,
            'type': 'number',
            'placeholder': '例：2015',
        },
        'orientation': {
            'label': '朝向',
            'required': False,
            'options': ['南', '北', '东', '西', '东南', '西南', '东北', '西北', '南北', '东西'],
        },
        'structure': {
            'label': '建筑结构',
            'required': False,
            'options': ['钢混', '砖混', '钢结构', '砖木', '其他'],
        },
        'decoration': {
            'label': '装修状况',
            'required': False,
            'options': ['毛坯', '简装', '精装', '豪装'],
        },
        'cert_no': {
            'label': '产权证号',
            'required': False,
            'placeholder': '例：苏(2023)常州市不动产权第XXXX号',
        },
        'owner': {
            'label': '权利人',
            'required': False,
        },
        'land_end_date': {
            'label': '土地使用权终止日期',
            'required': False,
            'type': 'date',
        },
    }
