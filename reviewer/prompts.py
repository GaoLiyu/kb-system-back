"""
LLM审查提示词
=============
针对房地产估价报告的语义审查
"""


def build_paragraph_review_prompt(paragraphs: list, report_type: str = "shezhi") -> str:
    """
    构建段落审查提示词（基于评审标准-外在质量部分）

    Args:
        paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
        report_type: 报告类型
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要依据《房地产估价规范》及评审标准，审查以下报告的文本段落质量。

【报告类型】
{report_type_desc}

【审查依据】
参照评审标准"四、附件及外在质量（10分）"中第28项"外在质量"标准：
- 专业术语规范，前后表述一致
- 报告各部分之间描述不应相互矛盾
- 报告各部分之间不应出现不必要的重复
- 文字表述通顺、逻辑性强、客观平实
- 不应存在病句、错别字、漏字、标点符号错误
- 序号使用规范、顺序正确

【审查重点】
1. **专业术语规范性**（参照《房地产估价规范》GB/T 50291-2015）
   - 估价术语使用是否正确（如"价值时点"、"估价对象"、"比较法"等）
   - 同一概念的表述是否前后一致
   - 是否存在自造术语或不规范表述

2. **逻辑合理性**
   - 段落内容是否前后一致、符合逻辑
   - 描述与结论是否匹配
   - 因果关系是否成立

3. **表述规范性**
   - 是否存在错别字、漏字
   - 是否存在病句、语病
   - 标点符号使用是否正确
   - 表述是否通顺、客观平实

4. **内容完整性**
   - 关键信息是否完整
   - 必要的说明是否充分

【审查规则】
- 只审查文本段落，表格数据不在审查范围
- 只报告你非常确定的问题，必须有明确依据
- 不要挑文风、格式、礼貌用语等主观偏好问题
- 每个问题必须指明具体段落（用paragraph_index标识）
- span必须是原文的精确子串

【待审查的段落】
{paragraphs_text}

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "paragraph_index": 段落索引号（整数）,
      "category": "TERMINOLOGY | LOGIC | EXPRESSION | COMPLETENESS | CONSISTENCY",
      "type": "具体问题类型（如'术语使用不当'、'错别字'、'逻辑矛盾'）",
      "severity": "minor | major | critical",
      "span": "问题所在的原文片段（精确子串）",
      "standard_reference": "违反的评审标准（如'评审标准第28项：专业术语规范'）",
      "comment": "问题详细说明",
      "suggestion": "具体修改建议"
    }}
  ],
  "summary": {{
    "total_errors": 错误总数,
    "terminology_errors": 术语问题数,
    "expression_errors": 表述问题数,
    "logic_errors": 逻辑问题数
  }}
}}

【错误类别说明】
- TERMINOLOGY：专业术语使用不当、自造术语、术语前后不一致
- LOGIC：逻辑问题（前后矛盾、因果关系不成立、描述与结论不符）
- EXPRESSION：表述问题（错别字、漏字、病句、语病、标点错误）
- COMPLETENESS：信息不完整（关键信息缺失、说明不充分）
- CONSISTENCY：前后不一致（同一概念表述不一致、不必要的重复）

【严重程度说明】
- critical：严重影响报告专业性或理解（如核心术语错误、严重逻辑矛盾）
- major：明显影响报告质量（如多处错别字、表述不清影响理解）
- minor：轻微问题，建议修改（如个别标点错误、表述可优化）

如果没有发现确定的问题，输出：
{{
  "errors": [],
  "summary": {{
    "total_errors": 0,
    "terminology_errors": 0,
    "expression_errors": 0,
    "logic_errors": 0
  }}
}}
'''

    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估），采用比较法',
        'zujin': '租金报告（租金评估），采用比较法',
        'biaozhunfang': '标准房报告（标准房价格评估），采用比较法',
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
    构建报告审查提示词（重点审查数据一致性和计算准确性）

    Args:
        report_text: 报告文本片段
        report_type: 报告类型
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查以下报告片段的数据一致性和逻辑合理性。

【报告类型】
{report_type_desc}

【审查重点】
1. **数值一致性**（critical级别）
   - 估价对象面积在不同位置是否一致
   - 可比实例价格在不同位置是否一致
   - 价值时点、实地查勘日期等关键日期是否一致
   - 估价结果在致函、结果报告、技术报告中是否一致
   - 参照评审标准：不一致属于严重问题

2. **计算准确性**（critical级别）
   - 修正系数相乘计算是否正确
   - 价格计算公式应用是否正确
   - 参照评审标准表1-1第7项：计算错误扣5-8分

3. **逻辑合理性**（major级别）
   - 描述与数值是否匹配
     * 例如：描述"位置较优"，但区位修正系数<1（矛盾）
     * 例如：描述"新旧程度相当"，但实物修正系数偏离1较大
   - 修正方向与因素描述是否一致
     * 可比实例优于估价对象→修正系数<1
     * 可比实例劣于估价对象→修正系数>1

4. **前后矛盾**（major级别）
   - 同一段落或相邻段落的表述是否矛盾
   - 假设条件与实际描述是否矛盾

5. **专业准确性**（major级别）
   - 估价术语使用是否符合《房地产估价规范》
   - 公式表达是否正确
   - 参数含义说明是否准确

【审查规则】
- 只报告你非常确定的问题，必须基于报告原文
- span必须是原文的精确子串（不能编造）
- 计算问题必须给出具体的计算过程说明
- 不要挑文风、礼貌用语等主观问题

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "category": "DATA_CONSISTENCY | CALCULATION | LOGIC | TERMINOLOGY | CONTRADICTION",
      "type": "具体问题类型（如'面积前后不一致'、'修正系数计算错误'）",
      "severity": "minor | major | critical",
      "span": "问题所在的原文片段（必须是原文精确子串）",
      "standard_reference": "违反的评审标准（如'表1-1第7项：计算错误'）",
      "comment": "问题详细说明（对于计算问题，需给出正确的计算过程）",
      "suggestion": "具体修改建议"
    }}
  ]
}}

【错误类别说明】
- DATA_CONSISTENCY：数值不一致（同一属性在不同位置数值不同）
- CALCULATION：计算错误（公式错误、计算过程错误、结果错误）
- LOGIC：逻辑不合理（描述与数值矛盾、修正方向与描述不符）
- TERMINOLOGY：术语使用不当
- CONTRADICTION：前后表述矛盾

【严重程度判定】
- critical：数据不一致、计算错误（影响估价结果准确性）
- major：逻辑矛盾、术语错误（显著影响报告质量）
- minor：轻微表述问题（建议优化）

【计算审查示例】
原文："交易情况修正=1.00，市场状况修正=1.05，区位修正=0.95，实物修正=1.02，权益修正=1.00，修正后价格=10000×1.00×1.05×0.95×1.02×1.00=10150元/㎡"

审查：1.00×1.05×0.95×1.02×1.00 = 1.01745
      10000×1.01745 = 10174.5元/㎡ ≠ 10150元/㎡

输出：
{{
  "category": "CALCULATION",
  "type": "修正系数计算错误",
  "severity": "critical",
  "span": "修正后价格=10000×1.00×1.05×0.95×1.02×1.00=10150元/㎡",
  "standard_reference": "评审标准表1-1第7项：计算错误",
  "comment": "修正系数连乘计算错误。正确计算：1.00×1.05×0.95×1.02×1.00=1.01745，修正后价格应为10000×1.01745=10174.5元/㎡，而非10150元/㎡",
  "suggestion": "修改为：修正后价格=10000×1.00×1.05×0.95×1.02×1.00=10175元/㎡（四舍五入）"
}}

如果没有发现问题，输出：{{"errors": []}}

【待审查的报告片段】
{report_text}
'''

    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估），采用比较法，价格单位通常为元/㎡',
        'zujin': '租金报告（租金评估），采用比较法，价格单位为元/㎡·年',
        'biaozhunfang': '标准房报告（标准房价格评估），采用比较法',
    }

    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        report_text=report_text
    )


def build_comparison_review_prompt(subject_data: dict, cases_data: list, report_type: str = "shezhi") -> str:
    """
    构建比较审查提示词（基于评审标准表1-1比较法评审标准）

    Args:
        subject_data: 估价对象数据
        cases_data: 可比实例数据列表
        report_type: 报告类型
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要依据评审标准表1-1"估价测算过程——比较法评审标准"，审查估价对象与可比实例之间的关系。

【报告类型】
{report_type_desc}

【估价对象信息】
{subject_info}

【可比实例信息】
{cases_info}

【审查依据：评审标准表1-1比较法评审标准（40分）】

**1. 可比实例选取（9分）**
- 数量要求：不少于3个（缺少扣3分）
- 真实性：来源真实、价格内涵清晰（不清晰扣1-2分）
- 信息完备性：必要信息完备（不完整扣1-2分）
- 可比性：区位、成交日期等具有可比性（可比性不强扣1-2分）
- **虚构、编造可比实例属于不合格内容**

**2. 建立可比较基础（4分）**
- 应消除财产范围差异、统一付款方式、统一融资条件、统一税费负担、统一计价单位
- 每缺少一项标准化处理，扣1-3分

**3. 交易情况修正（2分）**
- 修正方法明确、方向正确、幅度合理
- 方向错误扣2分，幅度不合理扣0.5-2分

**4. 市场状况调整（4分）**
- 成交日期明确、调整方法正确、方向正确、幅度合理
- 方向错误扣1-3分，幅度不合理扣0.5-4分

**5. 区位状况调整（6分）**
- 比较因素选择恰当、说明清晰、权重合理
- **调整方向错误扣6分（critical）**
- 调整幅度不合理扣0.5-6分

**6. 实物状况调整（6分）**
- 比较因素选择恰当、说明清晰、权重合理
- **调整方向错误扣6分（critical）**
- 调整幅度不合理扣0.5-6分

**7. 权益状况调整（4分）**
- 比较因素选择恰当、说明清晰
- 方向错误扣4分，幅度不合理扣0.5-4分

**8. 计算过程（5分）**
- 公式正确、过程完整、权重合理、计算准确
- **计算错误扣1-5分（critical）**

【审查重点】

1. **可比实例数量**（critical）
   - 必须不少于3个
   - 少于3个属于严重问题

2. **可比性审查**（major）
   - 用途是否一致或相近
   - 区位是否接近（同一区域、相似地段）
   - 规模是否可比（面积差异不宜过大）
   - 成交时间不宜过久（通常不超过1年）

3. **修正方向审查**（critical）
   - **核心规则**：
     * 可比实例某因素"优于"估价对象 → 该因素修正系数 < 1
     * 可比实例某因素"劣于"估价对象 → 该因素修正系数 > 1
     * 可比实例某因素"相当于"估价对象 → 该因素修正系数 = 1

   - 常见错误示例：
     * 实例A位置优于估价对象，但区位修正系数=1.05（应<1）
     * 实例B楼层劣于估价对象，但实物修正系数=0.95（应>1）

4. **修正幅度审查**（major）
   - 单项修正系数通常在0.8-1.2范围内
   - 超出此范围需有充分理由
   - 综合修正系数通常在0.7-1.3范围内

5. **修正后价格审查**（major）
   - 各实例修正后价格应较为接近
   - 差异过大（超过20%）可能存在问题
   - 修正后价格应在合理市场价格区间内

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "category": "CASE_SELECTION | COMPARABILITY | CORRECTION_DIRECTION | CORRECTION_RANGE | CALCULATION | PRICE_REASONABLENESS",
      "type": "具体问题类型",
      "severity": "minor | major | critical",
      "case_id": "涉及的实例ID（如'A'、'B'、'C'，或'ALL'表示整体问题）",
      "factor": "涉及的因素（如'区位状况'、'实物状况'、'权益状况'）",
      "standard_reference": "违反的评审标准（如'表1-1第5项：区位状况调整方向错误'）",
      "comment": "问题详细说明（需说明为何判定为优/劣/相当，以及为何修正方向错误）",
      "suggestion": "具体修改建议",
      "impact": "问题影响（如'影响估价结果准确性'）"
    }}
  ],
  "summary": {{
    "total_errors": 错误总数,
    "critical_count": 严重错误数,
    "major_count": 重要错误数,
    "case_count": 可比实例数量,
    "main_issues": ["主要问题列表"]
  }}
}}

【错误类别说明】
- CASE_SELECTION：可比实例选取问题（数量不足、来源不真实、信息不全）
- COMPARABILITY：可比性问题（用途、区位、规模等不具可比性）
- CORRECTION_DIRECTION：修正方向错误（与因素描述矛盾）
- CORRECTION_RANGE：修正幅度不合理（超出合理范围且无充分理由）
- CALCULATION：计算错误（修正系数连乘错误、价格计算错误）
- PRICE_REASONABLENESS：修正后价格不合理（各实例差异过大、偏离市场价格）

【严重程度判定】
- critical：修正方向错误、计算错误、虚构实例、可比实例数量不足（对应扣分≥5分）
- major：可比性差、修正幅度不合理、价格差异过大（对应扣分2-4分）
- minor：轻微的参数取值问题（对应扣分≤1分）

【修正方向审查示例】

示例1：方向正确
- 可比实例A：位于主干道，估价对象：位于支路
- 判断：实例A区位优于估价对象
- 修正系数：0.95（<1，方向正确）

示例2：方向错误（critical）
- 可比实例B：6层，估价对象：2层（低层更优）
- 判断：实例B楼层劣于估价对象
- 修正系数：0.98（<1，方向错误，应>1）
- 输出：
{{
  "category": "CORRECTION_DIRECTION",
  "severity": "critical",
  "case_id": "B",
  "factor": "实物状况-楼层",
  "standard_reference": "表1-1第6项：实物状况调整方向错误",
  "comment": "实例B位于6层，估价对象位于2层。对于住宅而言，低层通常优于高层（出入方便、无电梯依赖）。因此实例B楼层劣于估价对象，修正系数应>1，但实际给出0.98<1，方向错误。",
  "suggestion": "修改楼层修正系数为1.05-1.10，反映实例B楼层劣于估价对象的情况",
  "impact": "修正方向错误将导致估价结果偏离真实价值"
}}

如果没有发现问题，输出：
{{
  "errors": [],
  "summary": {{
    "total_errors": 0,
    "critical_count": 0,
    "major_count": 0,
    "case_count": {case_count},
    "main_issues": []
  }}
}}
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
区位特征：{subject_data.get('location_desc', '未描述')}
实物特征：{subject_data.get('physical_desc', '未描述')}
"""

    # 格式化可比实例信息
    cases_info_parts = []
    for case in cases_data:
        case_str = f"""
【实例{case.get('case_id', '?')}】
地址：{case.get('address', '未知')}
面积：{case.get('area', '未知')}㎡
用途：{case.get('usage', '未知')}
成交时间：{case.get('transaction_date', '未知')}
成交价格：{case.get('price', '未知')}

修正系数：
- 交易情况修正：{case.get('transaction_correction', '未知')}
- 市场状况调整：{case.get('market_correction', '未知')}
- 区位状况调整：{case.get('location_correction', '未知')}
- 实物状况调整：{case.get('physical_correction', '未知')}
- 权益状况调整：{case.get('rights_correction', '未知')}
- 综合修正系数：{case.get('total_correction', '未知')}

修正后价格：{case.get('adjusted_price', '未知')}
"""
        # 添加因素描述
        if case.get('location_factors'):
            case_str += f"\n区位因素描述：{case.get('location_factors')}"
        if case.get('physical_factors'):
            case_str += f"\n实物因素描述：{case.get('physical_factors')}"
        if case.get('rights_factors'):
            case_str += f"\n权益因素描述：{case.get('rights_factors')}"

        cases_info_parts.append(case_str)

    case_count = len(cases_data)

    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        subject_info=subject_info,
        cases_info="\n".join(cases_info_parts),
        case_count=case_count
    )


def build_factor_review_prompt(factors_data: list) -> str:
    """
    构建因素审查提示词（审查因素等级与指数/系数是否匹配）

    Args:
        factors_data: 因素数据列表
            [{
                'case_id': 'A',
                'factor_name': '交通便捷度',
                'level': '优',  # 等级描述
                'index': 105,   # 指数值（100为基准）或
                'coefficient': 1.05  # 修正系数（1.00为基准）
            }]
    """

    prompt = '''你是一个专业的房地产估价报告审核专家，需要审查因素等级描述与修正指数/系数是否匹配。

【审查依据】
参照评审标准表1-1"比较法评审标准"第5、6、7项：
- 区位状况调整：**调整方向错误扣6分（critical）**
- 实物状况调整：**调整方向错误扣6分（critical）**
- 权益状况调整：方向错误扣4分（major）

【核心审查规则】

1. **指数与基准的关系**（用于因素条件说明表）
   - 指数 = 100：与基准相当、相同、一般
   - 指数 > 100：优于基准、较好、较优
   - 指数 < 100：劣于基准、较差

2. **修正系数的逻辑**（用于修正系数表）
   - 系数 = 1.00：可比实例与估价对象相当
   - 系数 < 1.00：可比实例优于估价对象（需向下修正）
   - 系数 > 1.00：可比实例劣于估价对象（需向上修正）

3. **等级描述与数值的对应**
   - "优"、"较优"、"好"、"较好" → 指数>100 或 实例优于对象时系数<1
   - "一般"、"相当"、"中等"、"相近" → 指数≈100（95-105）或 系数≈1.00（0.95-1.05）
   - "差"、"较差"、"劣" → 指数<100 或 实例劣于对象时系数>1

4. **常见错误类型**
   - 等级与指数/系数方向相反（critical）
   - 等级与指数/系数幅度不匹配（major）
   - 相同等级但指数/系数差异过大（minor）

【待审查的因素数据】
{factors_info}

【必须输出的JSON格式】
{{
  "errors": [
    {{
      "case_id": "实例ID",
      "factor_name": "因素名称",
      "level": "等级描述",
      "value": 指数值或修正系数值,
      "value_type": "index | coefficient",
      "category": "DIRECTION_MISMATCH | MAGNITUDE_MISMATCH | INCONSISTENCY",
      "severity": "minor | major | critical",
      "standard_reference": "违反的评审标准",
      "comment": "问题详细说明（需说明预期的数值范围）",
      "suggestion": "具体修改建议"
    }}
  ]
}}

【错误类别说明】
- DIRECTION_MISMATCH：方向不匹配（等级与指数/系数方向相反，critical）
- MAGNITUDE_MISMATCH：幅度不匹配（等级与指数/系数幅度不符，major）
- INCONSISTENCY：不一致（相同等级但数值差异大，minor）

【审查示例】

示例1：方向不匹配（critical）
输入：{{"case_id": "A", "factor_name": "交通便捷度", "level": "优", "index": 95, "value_type": "index"}}
问题：等级为"优"（应>100），但指数=95（<100），方向相反
输出：
{{
  "case_id": "A",
  "factor_name": "交通便捷度",
  "level": "优",
  "value": 95,
  "value_type": "index",
  "category": "DIRECTION_MISMATCH",
  "severity": "critical",
  "standard_reference": "表1-1第5项：区位状况调整方向错误",
  "comment": "交通便捷度等级标注为'优'，表示优于基准，指数应>100，但实际指数为95<100，方向相反",
  "suggestion": "修改指数为105-110，或修改等级描述为'较差'"
}}

示例2：幅度不匹配（major）
输入：{{"case_id": "B", "factor_name": "装修程度", "level": "较优", "coefficient": 0.98, "value_type": "coefficient"}}
问题：等级为"较优"（实例优于对象，系数应<1），但0.98接近1.00，幅度过小
输出：
{{
  "case_id": "B",
  "factor_name": "装修程度",
  "level": "较优",
  "value": 0.98,
  "value_type": "coefficient",
  "category": "MAGNITUDE_MISMATCH",
  "severity": "major",
  "comment": "实例B装修程度'较优'于估价对象，修正系数应明显<1（建议0.90-0.95），但实际为0.98，幅度过小，未充分反映优劣差异",
  "suggestion": "修改修正系数为0.92-0.95，或修改等级描述为'基本相当'"
}}

示例3：正常情况
输入：{{"case_id": "C", "factor_name": "建筑结构", "level": "相同", "coefficient": 1.00, "value_type": "coefficient"}}
分析：等级"相同"，系数1.00，匹配正确
输出：无错误

如果没有发现问题，输出：{{"errors": []}}
'''

    # 格式化因素信息
    factors_info_parts = []
    for item in factors_data:
        value = item.get('index') or item.get('coefficient')
        value_type = 'index' if 'index' in item else 'coefficient'
        factors_info_parts.append(
            f"实例{item['case_id']} - {item['factor_name']}："
            f"等级=\"{item['level']}\"，"
            f"{value_type}={value}"
        )

    return prompt.format(factors_info="\n".join(factors_info_parts))


def build_full_document_review_prompt(paragraphs: list, report_type: str = "shezhi") -> str:
    """
    构建全文审查提示词（基于房地产估价报告评审标准）

    Args:
        paragraphs: 段落列表 [{'index': 0, 'text': '...'}, ...]
        report_type: 报告类型
    """

    prompt = '''你是一位资深房地产估价报告审查专家，请依据《房地产估价规范》GB/T 50291-2015、《涉执房地产处置司法评估专业技术评审方法（试行）》及相关评审标准，对以下完整报告进行全面审查。

【报告类型】
{report_type_desc}

【关键审查原则】
1. **上下文连贯性**：段落之间存在逻辑关联，标题段落后的内容通常是解释说明，不应孤立审查
2. **数据一致性**：同一属性在全文不同位置必须保持一致（面积、价格、日期等）
3. **逻辑自洽性**：估价假设、计算过程、估价结论应前后呼应、逻辑严密
4. **专业规范性**：术语、方法、公式使用应符合《房地产估价规范》要求
5. **完整性要求**：关键要素不应缺失（参照评审标准28项必备内容）

【一、报告结构与要素完整性审查】
根据评审标准，检查以下必备要素是否存在：

1. 封面要素（估价报告名称、编号、委托人、估价机构、估价师姓名及注册号、出具日期）
2. 致估价委托人函（估价目的、估价对象、价值时点、价值类型、估价方法、估价结果、机构盖章）
3. 目录结构（声明、假设和限制条件、估价结果报告、估价技术报告、附件）
4. 估价师声明（职业道德、专业能力承诺）
5. 估价假设和限制条件（一般假设、未定事项假设、背离事实假设、不相一致假设、依据不足假设）
6. 估价结果报告基本内容（委托人、估价机构、估价目的、估价对象、价值时点、价值类型、估价原则、估价依据、估价方法、估价结果、估价师签名、实地查勘期、估价作业期）
7. 估价技术报告核心内容（估价对象描述与分析、市场背景描述与分析、最高最佳利用分析、估价方法适用性分析、估价测算过程、估价结果确定）

【二、估价对象描述审查】
1. 实物状况：土地（面积、形状、地形、地势、开发程度）、建筑物（规模、结构、设施、装修、新旧程度）
2. 权益状况：用途、规划条件、权属、共有情况、用益物权、担保物权、租赁占用、查封等
3. 区位状况：位置、交通、周围环境、外部配套设施
4. **数值一致性**：面积、用途等关键属性在不同章节必须一致

【三、估价方法审查（重点）】

**如采用比较法，检查：**
1. 可比实例选取（不少于3个、来源真实、价格内涵清晰、可比性强）
2. 建立比较基础（统一财产范围、付款方式、融资条件、税费负担、计价单位）
3. 交易情况修正（是否存在非正常交易因素）
4. 市场状况调整（期日修正、价格指数变化）
5. 区位状况调整（位置、交通、环境等因素修正）
6. 实物状况调整（面积、结构、装修、新旧等因素修正）
7. 权益状况调整（用途、使用期限等）
8. **计算准确性**：各项修正系数相乘计算过程是否正确
9. **结果合理性**：修正后价格是否在合理范围内

**如采用收益法，检查：**
1. 租金水平确定（依据充分、内涵清晰）
2. 空置率和租金损失（合理性）
3. 运营费用构成（完整性、取值依据）
4. 净收益计算（前后一致）
5. 报酬率/资本化率确定（方法正确、依据充分）
6. 收益期限确定（依据充分）

**如采用成本法，检查：**
1. 土地取得成本（途径明确、构成完整）
2. 建设成本（建安工程费、基础设施费、配套设施费、期间税费）
3. 管理费用、销售费用、投资利息、销售税费
4. 开发利润（利润率内涵清楚、取值合理）
5. 折旧分析（维护使用状况描述、成新率确定）

【四、逻辑与计算审查】
1. **前后一致性**：估价假设、估价方法选用、计算过程、估价结果在不同章节的表述是否一致
2. **计算准确性**：公式选用是否正确、计算过程是否完整、计算结果是否准确
3. **参数合理性**：修正系数、折现率、成新率等参数取值是否有依据、是否合理
4. **结论支撑性**：估价结论是否有充分的论证支撑，是否存在跳跃性结论

【五、市场状况分析审查】
1. 当地经济社会发展状况描述
2. 房地产市场总体状况分析
3. 同类房地产市场详细分析（供需、价格走势）
4. 分析与估价参数取值的一致性

【六、专业表述审查】
1. 术语规范性（估价术语是否符合《房地产估价规范》）
2. 表述准确性（是否存在错别字、语病、表述不清）
3. 逻辑性（段落之间逻辑关系是否清晰）
4. 简洁性（是否存在不必要的重复）

【不应报告的情况】
- 标题段落后紧跟的解释性内容（这是正常结构，除非解释与标题不符）
- 纯格式问题（缩进、空行、字体等）
- 主观文风偏好（在不影响专业性的前提下）
- 不确定的问题（宁缺毋滥，必须有明确依据）
- 轻微的表述优化建议（除非影响理解或专业性）

【严重问题判定标准】
参照评审标准，以下情况属于critical级别：
1. 虚构、编造估价对象状况、可比实例、估价基础数据
2. 估价目的严重错误、未对应相应行为
3. 价值时点确定错误
4. 估价方法选用错误、运用错误
5. 计算公式选用错误、计算结果错误
6. 关键数据前后矛盾（如面积、价格在不同位置不一致）
7. 估价结果不合理偏高或偏低

【报告全文】
{document_text}

【输出JSON格式】
{{
  "errors": [
    {{
      "paragraph_index": 问题主要所在的段落索引号（整数）,
      "related_paragraphs": [相关段落索引号列表（如问题涉及多个段落的对比）],
      "category": "COMPLETENESS | DATA_CONSISTENCY | CALCULATION | METHOD_APPLICATION | LOGIC | TERMINOLOGY | EXPRESSION",
      "type": "具体问题类型（如'可比实例不足'、'面积前后不一致'、'修正系数计算错误'）",
      "severity": "minor | major | critical",
      "span": "问题所在的原文片段（尽可能精确定位）",
      "standard_reference": "违反的评审标准条款（如'表1-1第1项：可比实例不少于3个'）",
      "comment": "问题详细说明（结合上下文说明为何构成问题）",
      "suggestion": "具体修改建议",
      "impact": "问题影响（如'影响估价结果准确性'、'违反规范要求'）"
    }}
  ],
  "summary": {{
    "total_errors": 错误总数,
    "critical_count": 严重错误数量,
    "major_count": 重要错误数量,
    "minor_count": 轻微错误数量,
    "main_issues": ["主要问题类别列表"],
    "overall_assessment": "整体评价（一句话）",
    "compliance_score": "合规性评估（high/medium/low）"
  }}
}}

【错误类别说明】
- COMPLETENESS：要素缺失（关键内容、必备章节缺失）
- DATA_CONSISTENCY：数据不一致（同一属性在不同位置数值不同）
- CALCULATION：计算错误（公式错误、计算过程错误、结果错误）
- METHOD_APPLICATION：方法运用问题（方法选择不当、参数取值不合理、步骤缺失）
- LOGIC：逻辑问题（前后矛盾、因果关系不成立、结论缺乏支撑）
- TERMINOLOGY：术语问题（专业术语使用不当、定义错误）
- EXPRESSION：表述问题（错别字、严重语病、表述不清影响理解）

【严重程度说明】
- critical：严重错误，导致报告不合格或估价结果严重偏离（扣分≥5分或属于定性评审不合格项）
- major：重要问题，显著影响报告质量（扣分2-4分）
- minor：轻微问题，建议修改以提升质量（扣分≤1分）

如果未发现确定的问题，输出：
{{
  "errors": [],
  "summary": {{
    "total_errors": 0,
    "critical_count": 0,
    "major_count": 0,
    "minor_count": 0,
    "main_issues": [],
    "overall_assessment": "未发现明显问题，报告基本符合规范要求",
    "compliance_score": "high"
  }}
}}
'''

    type_desc = {
        'shezhi': '涉执报告（司法处置房产评估）\n- 估价目的：为人民法院确定财产处置参考价\n- 评审重点：比较法应用规范性、可比实例真实性、市场状况调整合理性、估价结果客观性',
        'zujin': '租金报告（租金评估）\n- 估价目的：确定房地产租金水平\n- 评审重点：收益法或比较法应用、租金市场分析、租赁案例可比性、价格单位（元/㎡·年）',
        'biaozhunfang': '标准房报告（标准房价格评估）\n- 估价目的：建立批量评估基准\n- 评审重点：比较法规范性、市场代表性、参数标准化',
    }

    # 格式化段落，带编号便于定位
    document_text = "\n".join([
        f"[段落{p['index']}] {p['text']}"
        for p in paragraphs
    ])

    return prompt.format(
        report_type_desc=type_desc.get(report_type, '房地产估价报告'),
        document_text=document_text
    )