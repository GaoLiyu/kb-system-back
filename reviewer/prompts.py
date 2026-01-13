"""
LLM审查提示词
=============
针对房地产估价报告的语义审查
"""


def build_paragraph_review_prompt(paragraphs: list, report_type: str = "shezhi") -> str:
    """
    构建段落审查提示词（只审查文本段落，不审查表格）

    Args:
        paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
        report_type: 报告类型
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查以下报告的文本段落，识别其中的问题。

【报告类型】
{report_type_desc}

【审查重点】
1. 逻辑合理性：描述是否前后一致、符合逻辑
2. 专业准确性：估价术语使用是否正确
3. 表述规范性：是否存在错别字、语病、表述不清
4. 内容完整性：关键信息是否完整

【审查规则】
- 只审查文本段落，表格数据不在审查范围
- 只报告你非常确定的问题，宁缺毋滥
- 不要挑文风、格式等小问题
- 每个问题必须指明是哪个段落（用paragraph_index标识）

【待审查的段落】
{paragraphs_text}

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "paragraph_index": 段落索引号,
      "type": "LOGIC | TERMINOLOGY | EXPRESSION | INCOMPLETE",
      "severity": "minor | major | critical",
      "span": "问题所在的原文片段",
      "comment": "问题说明",
      "suggestion": "修改建议"
    }}
  ]
}}

【错误类型说明】
- LOGIC：逻辑问题（前后矛盾、不合理）
- TERMINOLOGY：术语使用不当
- EXPRESSION：表述问题（错别字、语病）
- INCOMPLETE：信息不完整

如果没有发现问题，输出：{{"errors": []}}
'''

    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估），使用比较法',
        'zujin': '租金报告（租金评估），使用比较法',
        'biaozhunfang': '标准房报告（标准房价格评估），使用比较法',
    }

    # 格式化段落
    paragraphs_text = "\n".join([
        f"[段落{p['index']}] {p['text']}"
        for p in paragraphs
    ])

    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        paragraphs_text=paragraphs_text
    )


def build_report_review_prompt(report_text: str, report_type: str = "shezhi") -> str:
    """
    构建报告审查提示词

    Args:
        report_text: 报告文本片段
        report_type: 报告类型
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查以下报告片段，识别其中的问题。

【报告类型】
{report_type_desc}

【审查重点】
1. 数值一致性：同一属性在不同位置的数值是否一致（如面积、价格）
2. 逻辑合理性：描述与数值是否匹配（如"位置较优"但区位修正系数<1）
3. 前后矛盾：同一段落内的前后表述是否矛盾
4. 专业准确性：估价术语使用是否正确
5. 计算准确性：如果涉及计算，结果是否正确

【审查规则】
- 只报告你非常确定的问题，宁缺毋滥
- 不要挑文风、礼貌用语等小问题
- 每个问题必须基于报告原文，不能编造
- span必须是原文的精确子串

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "type": "CONSISTENCY | LOGIC | CALCULATION | TERMINOLOGY | CONTRADICTION",
      "severity": "minor | major | critical",
      "span": "问题所在的原文片段（必须是原文子串）",
      "comment": "问题说明",
      "suggestion": "修改建议"
    }}
  ]
}}

【错误类型说明】
- CONSISTENCY：数值不一致（如面积在不同地方写的不同）
- LOGIC：逻辑不合理（如描述与数值矛盾）
- CALCULATION：计算错误（如修正系数相乘结果不对）
- TERMINOLOGY：术语使用不当
- CONTRADICTION：前后表述矛盾

如果没有发现问题，输出：{{"errors": []}}

【待审查的报告片段】
{report_text}
'''

    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估），使用比较法，包含估价对象和3个可比实例',
        'zujin': '租金报告（租金评估），使用比较法，包含估价对象和3个可比实例，价格单位为元/㎡·年',
        'biaozhunfang': '标准房报告（标准房价格评估），使用比较法，包含标准房和4个可比实例',
    }

    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        report_text=report_text
    )


def build_comparison_review_prompt(subject_data: dict, cases_data: list, report_type: str = "shezhi") -> str:
    """
    构建比较审查提示词（审查估价对象与可比实例的关系）
    
    Args:
        subject_data: 估价对象数据
        cases_data: 可比实例数据列表
        report_type: 报告类型
    """
    
    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查估价对象与可比实例之间的关系是否合理。

【报告类型】
{report_type_desc}

【估价对象信息】
{subject_info}

【可比实例信息】
{cases_info}

【审查重点】
1. 可比性：可比实例与估价对象是否具有可比性（用途、区位、规模等）
2. 修正合理性：修正系数方向与因素描述是否一致
   - 如果可比实例某因素"优于"估价对象，该因素修正系数应<1
   - 如果可比实例某因素"劣于"估价对象，该因素修正系数应>1
3. 修正幅度：修正系数是否在合理范围（通常0.8-1.2）
4. 最终价格：各实例修正后价格是否在合理范围内

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "type": "COMPARABILITY | CORRECTION_DIRECTION | CORRECTION_RANGE | PRICE_RANGE",
      "severity": "minor | major | critical",
      "case_id": "涉及的实例ID（如A、B、C）",
      "factor": "涉及的因素（如区位状况、实物状况）",
      "comment": "问题说明",
      "suggestion": "修改建议"
    }}
  ]
}}

如果没有发现问题，输出：{{"errors": []}}
'''
    
    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估）',
        'zujin': '租金报告（租金评估），价格单位为元/㎡·年',
        'biaozhunfang': '标准房报告（标准房价格评估）',
    }
    
    # 格式化估价对象信息
    subject_info = f"""
地址：{subject_data.get('address', '未知')}
面积：{subject_data.get('area', '未知')}㎡
用途：{subject_data.get('usage', '未知')}
"""
    
    # 格式化可比实例信息
    cases_info_parts = []
    for case in cases_data:
        case_str = f"""
【实例{case.get('case_id', '?')}】
地址：{case.get('address', '未知')}
面积：{case.get('area', '未知')}㎡
价格：{case.get('price', '未知')}
交易情况修正：{case.get('transaction_correction', '未知')}
市场状况修正：{case.get('market_correction', '未知')}
区位状况修正：{case.get('location_correction', '未知')}
实物状况修正：{case.get('physical_correction', '未知')}
权益状况修正：{case.get('rights_correction', '未知')}
修正后价格：{case.get('adjusted_price', '未知')}
"""
        # 添加因素描述
        if case.get('location_factors'):
            case_str += "区位因素：" + str(case.get('location_factors')) + "\n"
        if case.get('physical_factors'):
            case_str += "实物因素：" + str(case.get('physical_factors')) + "\n"
        
        cases_info_parts.append(case_str)
    
    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        subject_info=subject_info,
        cases_info="\n".join(cases_info_parts)
    )


def build_factor_review_prompt(factors_data: list) -> str:
    """
    构建因素审查提示词（审查因素等级与指数是否匹配）
    
    Args:
        factors_data: 因素数据列表
    """
    
    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查因素等级与指数是否匹配。

【审查规则】
在比较法中，因素指数反映该因素相对于基准的优劣程度：
- 指数=100：与基准相当
- 指数>100：优于基准
- 指数<100：劣于基准

等级与指数的对应关系：
- "优"或"较优"：指数应>100
- "一般"或"中等"：指数应≈100（95-105）
- "差"或"较差"：指数应<100

【待审查的因素数据】
{factors_info}

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "case_id": "实例ID",
      "factor_name": "因素名称",
      "level": "等级描述",
      "index": 指数值,
      "comment": "问题说明",
      "suggestion": "修改建议"
    }}
  ]
}}

如果没有发现问题，输出：{{"errors": []}}
'''
    
    factors_info_parts = []
    for item in factors_data:
        factors_info_parts.append(
            f"实例{item['case_id']} - {item['factor_name']}：等级=\"{item['level']}\"，指数={item['index']}"
        )
    
    return prompt.format(factors_info="\n".join(factors_info_parts))
