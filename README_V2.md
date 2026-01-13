# 房地产估价知识库系统 V2

基于比较法的房地产估价报告知识库系统，支持报告提取、知识库管理、审查校验和生成辅助。

## 目录

- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [命令行使用](#命令行使用)
- [Python API](#python-api)
- [HTTP API](#http-api)
- [输入表单说明](#输入表单说明)
- [配置说明](#配置说明)

---

## 系统架构

```
real_estate_kb_system_v2/
├── main.py                 # 入口文件（CLI + API）
├── config.py               # 全局配置
├── extractors/             # 提取器（从Word提取结构化数据）
│   ├── shezhi_extractor.py      # 涉执报告
│   ├── zujin_extractor.py       # 租金报告
│   └── biaozhunfang_extractor.py # 标准房报告
├── validators/             # 校验器（规则校验）
│   └── report_validator.py
├── knowledge_base/         # 知识库（存储和检索）
│   ├── kb_manager.py            # 存储管理
│   ├── kb_query.py              # 查询检索
│   └── vector_store.py          # FAISS向量存储
├── reviewer/               # 审查器（知识库对比 + LLM语义审查）
│   ├── report_reviewer.py       # 综合审查
│   ├── llm_reviewer.py          # LLM语义审查
│   └── prompts.py               # 审查提示词
├── generator/              # 生成器（辅助生成）
│   ├── report_generator.py      # 生成辅助
│   └── input_schema.py          # 输入表单定义
├── api/                    # HTTP API（FastAPI）
│   ├── app.py                   # 应用入口
│   ├── auth.py                  # 鉴权
│   ├── config.py                # API配置
│   └── routes/                  # 路由
│       ├── kb.py                # 知识库接口
│       ├── search.py            # 搜索接口
│       ├── review.py            # 审查接口
│       └── generate.py          # 生成接口
├── web/                    # Web前端（Vue3 + TypeScript）
│   ├── src/
│   │   ├── views/               # 页面
│   │   │   ├── KBManage.vue     # 知识库管理
│   │   │   └── SearchCase.vue   # 案例搜索
│   │   ├── api/                 # API封装
│   │   ├── types/               # 类型定义
│   │   └── router/              # 路由
│   └── package.json
└── utils/                  # 工具
    ├── helpers.py
    └── llm_client.py            # LLM客户端
```

### 数据流

```
Word文档 → 提取器 → 结构化数据 → 知识库
                         ↓
新文档 → 提取 → 校验 → 知识库对比 → LLM审查 → 审查报告
                                              ↓
用户输入 → 知识库检索 → 推荐案例 → (LLM生成) → 报告
```

---

## 快速开始

### 安装依赖

```bash
# 核心依赖
pip install python-docx

# HTTP API（可选）
pip install fastapi uvicorn pydantic-settings python-multipart

# 向量检索（可选，推荐）
pip install faiss-cpu sentence-transformers

# LLM审查（可选）
pip install openai
```

### 基本使用

```python
from main import RealEstateKBSystem

# 初始化系统
system = RealEstateKBSystem()

# 1. 构建知识库（从文档目录）
system.build_from_directory("./data/docs")

# 2. 审查新报告
result = system.review("新报告.docx")
print(f"风险等级: {result.overall_risk}")
print(f"摘要: {result.summary}")

# 3. 搜索相似案例
cases = system.search_cases(district="武进区", usage="住宅", min_area=100)
```

---

## 命令行使用

### 构建知识库

```bash
# 从目录批量导入
python main.py build -d ./data/docs

# 添加单个文件
python main.py add -f 报告.docx
```

### 审查报告

```bash
# 完整审查（规则校验 + 知识库对比 + LLM语义审查）
python main.py review -f 待审报告.docx

# 仅规则校验（不使用知识库和LLM）
python main.py validate -f 报告.docx
```

### 搜索案例

```bash
# 按关键词搜索
python main.py search -k 湖塘

# 按报告类型搜索
python main.py search -t shezhi

# 组合搜索（需要用Python API）
```

### 查看统计

```bash
# 知识库统计
python main.py stats

# 列出所有报告
python main.py list
```

### 演示

```bash
python main.py demo
```

---

## Python API

### 初始化

```python
from main import RealEstateKBSystem

# 默认配置
system = RealEstateKBSystem()

# 自定义知识库路径
system = RealEstateKBSystem(kb_path="./my_kb")

# 禁用LLM审查（无需配置API）
system = RealEstateKBSystem(enable_llm=False)
```

### 知识库管理

```python
# 构建知识库
system.build_from_directory("./docs")

# 添加单个报告
doc_id = system.add_report("报告.docx")

# 查看统计
stats = system.stats()
print(f"报告数: {stats['report_count']}")
print(f"案例数: {stats['case_count']}")

# 清空知识库
system.kb.clear()
```

### 审查报告

```python
# 完整审查
result = system.review("报告.docx")

# 访问审查结果
print(f"风险等级: {result.overall_risk}")  # low/medium/high
print(f"摘要: {result.summary}")

# 基础校验问题
for issue in result.validation.issues:
    print(f"[{issue.level}] {issue.category}: {issue.description}")

# 公式验证
for fc in result.validation.formula_checks:
    print(f"实例{fc.case_id}: 期望{fc.expected:.0f} 实际{fc.actual:.0f} {'✓' if fc.is_valid else '✗'}")

# 知识库对比异常
for comp in result.comparisons:
    if comp.is_abnormal:
        print(f"{comp.item}: {comp.current_value} (范围: {comp.kb_min}~{comp.kb_max})")

# LLM语义问题
for issue in result.llm_issues:
    print(f"[{issue.type}] {issue.description}")

# 相似案例
for case in result.similar_cases:
    print(f"{case['address']['value']}: {case['price']}元/㎡")

# 建议
for rec in result.recommendations:
    print(f"• {rec}")
```

### 搜索案例

```python
from knowledge_base import KnowledgeBaseQuery

query = KnowledgeBaseQuery(system.kb)

# 基础搜索
cases = query.search_cases(
    keyword="湖塘",           # 地址关键词
    report_type="shezhi",    # 报告类型
    min_price=20000,         # 最低价格
    max_price=30000,         # 最高价格
    min_area=80,             # 最小面积
    max_area=150,            # 最大面积
)

# 扩展搜索（新增）
cases = query.search_cases(
    district="武进区",        # 区域
    usage="住宅",             # 用途
    min_floor=5,             # 最低楼层
    max_floor=20,            # 最高楼层
    min_build_year=2010,     # 最早建成年份
    max_build_year=2020,     # 最晚建成年份
)

# 向量检索（语义相似）
similar = query.find_similar_cases_by_vector(
    query="武进区湖塘镇交通便利近地铁的住宅",
    report_type="shezhi",
    top_k=10,
)

# 混合检索（向量 + 规则）
similar = query.find_similar_cases_hybrid(
    query="交通便利 学区房 精装修",  # 语义查询
    area=120,                      # 面积约束
    district="武进区",              # 区域约束
    usage="住宅",                   # 用途约束
    top_k=10,
    vector_weight=0.6,             # 向量权重60%，规则权重40%
)

# 规则匹配（多维度权重）
similar = query.find_similar_cases(
    address="常州市武进区XX路",
    area=120,
    price=25000,
    report_type="shezhi",
    district="武进区",
    usage="住宅",
    floor=8,
    build_year=2015,
    top_k=5,
)

for case, score in similar:
    print(f"{case['address']['value']}: 相似度{score:.2f}")
```

---

## HTTP API

### 启动服务

```bash
# 安装依赖
pip install fastapi uvicorn pydantic-settings python-multipart

# 启动服务
uvicorn api.app:app --host 0.0.0.0 --port 8000

# 开发模式（自动重载）
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：
- API文档：http://localhost:8000/docs
- ReDoc：http://localhost:8000/redoc

### 认证

所有接口需要Bearer Token认证：

```bash
# 设置Token（.env文件或环境变量）
KB_API_TOKEN=your-secret-token

# 请求时带上Header
curl -H "Authorization: Bearer your-secret-token" http://localhost:8000/api/kb/stats
```

### 接口列表

#### 知识库管理 `/api/kb`

| 方法 | 路径 | 说明 |
|-----|------|------|
| GET | /api/kb/stats | 知识库统计 |
| GET | /api/kb/reports | 报告列表 |
| GET | /api/kb/reports/{doc_id} | 报告详情 |
| POST | /api/kb/upload | 上传报告 |
| DELETE | /api/kb/reports/{doc_id} | 删除报告 |
| POST | /api/kb/rebuild-vector | 重建向量索引 |
| POST | /api/kb/clear | 清空知识库 |

#### 搜索 `/api/search`

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | /api/search/cases | 字段搜索 |
| POST | /api/search/similar | 语义搜索（向量） |
| POST | /api/search/hybrid | 混合搜索 |
| GET | /api/search/cases/{case_id} | 案例详情 |
| GET | /api/search/stats/price | 价格统计 |
| GET | /api/search/stats/area | 面积统计 |

#### 审查 `/api/review`

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | /api/review/full | 完整审查 |
| POST | /api/review/validate | 快速校验 |
| POST | /api/review/extract | 提取数据 |

#### 生成辅助 `/api/generate`

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | /api/generate/suggest-cases | 推荐可比实例 |
| GET | /api/generate/reference/{type} | 获取参考数据 |
| POST | /api/generate/validate-input | 验证输入 |
| GET | /api/generate/input-schema | 获取表单定义 |

### 请求示例

**上传报告：**

```bash
curl -X POST "http://localhost:8000/api/kb/upload" \
  -H "Authorization: Bearer your-token" \
  -F "file=@报告.docx"
```

**语义搜索：**

```bash
curl -X POST "http://localhost:8000/api/search/similar" \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "武进区交通便利近地铁住宅",
    "report_type": "shezhi",
    "top_k": 10
  }'
```

**完整审查：**

```bash
curl -X POST "http://localhost:8000/api/review/full" \
  -H "Authorization: Bearer your-token" \
  -F "file=@待审报告.docx"
```

**推荐案例：**

```bash
curl -X POST "http://localhost:8000/api/generate/suggest-cases" \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "address": "常州市武进区湖塘镇XX路",
    "area": 120,
    "report_type": "shezhi",
    "district": "武进区",
    "count": 5
  }'
```

---

## Web前端

### 启动前端

```bash
cd web

# 安装依赖
npm install

# 开发模式（需要先启动后端）
npm run dev

# 构建生产版本
npm run build
```

访问 http://localhost:3000

### 页面功能

**知识库管理** `/kb`
- 统计概览（报告数、案例数、向量数）
- 上传报告（支持 .doc/.docx）
- 报告列表（查看、删除）
- 重建向量索引

**案例搜索** `/search`
- 混合搜索（向量 + 规则）
- 语义搜索（纯向量）
- 字段搜索（精确匹配）
- 案例详情（修正系数、因素描述）

### 技术栈

- Vue 3.4 + TypeScript
- Element Plus
- Vue Router
- Axios
- Vite

### 生成辅助

```python
# 推荐可比实例
cases = system.suggest_cases(
    address="常州市武进区湖塘镇XX路XX号",
    area=120.5,
    report_type="shezhi",
    count=5,
)

# 获取参考数据
ref = system.get_reference("shezhi")
print(f"价格范围: {ref['price_range']}")
print(f"面积范围: {ref['area_range']}")
print(f"修正系数统计: {ref['correction_reference']}")
```

---

## 输入表单说明

用于生成报告时的用户输入定义。

### 必填字段

| 字段 | 说明 | 示例 |
|-----|------|------|
| `address` | 估价对象地址 | 常州市武进区XX路XX号XX室 |
| `building_area` | 建筑面积(㎡) | 126.71 |
| `usage` | 用途 | 住宅/商业/办公/工业 |
| `report_type` | 报告类型 | shezhi/zujin/biaozhunfang |
| `appraisal_purpose` | 估价目的 | 为人民法院确定财产处置参考价... |
| `value_date` | 价值时点 | 2025-01-01 |

### 推荐字段

| 字段 | 说明 | 示例 |
|-----|------|------|
| `district` | 区域 | 武进区 |
| `street` | 街道/镇 | 湖塘镇 |
| `current_floor` | 所在楼层 | 8 |
| `total_floor` | 总楼层 | 18 |
| `build_year` | 建成年份 | 2015 |
| `orientation` | 朝向 | 南/北/东南等 |

### 可选字段

| 字段 | 说明 |
|-----|------|
| `structure` | 建筑结构（钢混/砖混等） |
| `decoration` | 装修状况（毛坯/简装/精装） |
| `cert_no` | 产权证号 |
| `owner` | 权利人 |
| `land_end_date` | 土地使用权终止日期 |

### 使用示例

```python
from generator import SubjectInput, validate_subject_input, GenerateRequest

# 创建输入
subject = SubjectInput(
    address="常州市武进区湖塘镇XX路XX号XX室",
    building_area=126.71,
    usage="住宅",
    report_type="shezhi",
    appraisal_purpose="为人民法院确定财产处置参考价提供参考依据",
    value_date="2025-01-01",
    district="武进区",
    street="湖塘镇",
    current_floor=8,
    total_floor=18,
    build_year=2015,
    orientation="南",
)

# 验证输入
errors = validate_subject_input(subject)
if errors:
    print("输入有误:")
    for e in errors:
        print(f"  - {e}")
else:
    print("输入验证通过")

# 创建生成请求
request = GenerateRequest(
    subject=subject,
    case_count=3,
    auto_select_cases=True,
)

# 获取字段说明（用于前端）
from generator import get_field_descriptions
fields = get_field_descriptions()
print(fields['address'])
# {'label': '估价对象地址', 'required': True, 'placeholder': '例：常州市武进区XX路XX号XX室', ...}
```

---

## 配置说明

### API配置

API通过环境变量配置，可以在 `.env` 文件中设置：

```bash
# 服务配置
KB_HOST=0.0.0.0
KB_PORT=8000
KB_DEBUG=false

# 鉴权（务必修改！）
KB_API_TOKEN=your-secret-token-here

# 知识库
KB_KB_PATH=./knowledge_base/storage
KB_ENABLE_VECTOR=true
KB_ENABLE_LLM=true

# 上传
KB_UPLOAD_DIR=./uploads
KB_MAX_UPLOAD_SIZE=52428800  # 50MB
```

### 向量检索配置（推荐）

向量检索需要安装依赖和配置模型路径：

```bash
# 安装依赖
pip install faiss-cpu sentence-transformers
```

默认使用 `/opt/models/bge-large-zh-v1.5` 模型，可以修改：

```python
from knowledge_base.vector_store import VectorStoreConfig

config = VectorStoreConfig(
    model_path="/your/path/to/bge-large-zh-v1.5",
    dimension=1024,
)
```

**向量索引管理：**

```python
# 手动重建向量索引
system.kb.rebuild_vector_index()

# 查看向量索引状态
stats = system.kb.stats()
print(stats['vector_index'])
# {'total_vectors': 100, 'dimension': 1024, 'is_dirty': False}

# 禁用向量检索
system = RealEstateKBSystem(kb_path="./kb", enable_vector=False)
```

### LLM配置（用于语义审查）

复制 `.env.example` 为 `.env`：

```bash
# API密钥
LLM_API_KEY=your_api_key_here

# API地址（兼容OpenAI格式）
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 模型名称
LLM_MODEL=qwen-plus
```

支持的API：
- 阿里云通义千问
- OpenAI
- 其他兼容OpenAI格式的API

### 不使用LLM

如果不需要LLM语义审查，可以禁用：

```python
system = RealEstateKBSystem(enable_llm=False)
```

此时审查只包含：
- 规则校验（完整性、公式验证）
- 知识库对比（价格范围、相似案例）

---

## 知识库索引字段

### 报告索引

```json
{
  "doc_id": "doc_xxx",
  "report_type": "shezhi",
  "source_file": "报告.docx",
  "address": "XX路XX号",
  "area": 126.71,
  "case_count": 3,
  "district": "武进区",
  "street": "湖塘镇",
  "usage": "住宅",
  "build_year": 2015,
  "total_floor": 18,
  "current_floor": 8,
  "structure": "钢混",
  "value_date": "2025-01-01",
  "appraisal_purpose": "..."
}
```

### 案例索引

```json
{
  "case_id": "doc_xxx_case_A",
  "from_doc": "doc_xxx",
  "report_type": "shezhi",
  "address": "XX路XX号",
  "area": 64.73,
  "price": 25372,
  "district": "武进区",
  "street": "湖塘镇",
  "usage": "住宅",
  "build_year": 2010,
  "total_floor": 20,
  "current_floor": 12,
  "structure": "钢混",
  "orientation": "南",
  "decoration": "精装",
  "transaction_date": "2025.4"
}
```

---

## 报告类型

| 类型 | 代码 | 说明 |
|-----|------|------|
| 涉执报告 | `shezhi` | 司法处置房产评估 |
| 租金报告 | `zujin` | 租金评估，价格单位元/㎡·年 |
| 标准房报告 | `biaozhunfang` | 标准房价格评估 |

---

## 相似度匹配权重

查找相似案例时的匹配权重：

| 维度 | 权重 | 说明 |
|-----|------|------|
| 区域 | 0.25 | 同区域优先 |
| 面积 | 0.20 | 面积接近 |
| 用途 | 0.15 | 用途相同 |
| 价格 | 0.15 | 价格接近 |
| 楼层 | 0.10 | 楼层接近 |
| 建成年份 | 0.10 | 房龄接近 |
| 地址关键词 | 0.05 | 地址包含相同关键词 |

---

## 常见问题

### Q: 如何处理.doc文件？

系统会自动调用LibreOffice转换，需要安装：

```bash
# Ubuntu/Debian
apt-get install libreoffice

# macOS
brew install libreoffice
```

### Q: LLM审查失败怎么办？

1. 检查 `.env` 配置是否正确
2. 检查API密钥是否有效
3. 可以禁用LLM继续使用规则校验：`enable_llm=False`

### Q: 如何扩展新的报告类型？

1. 在 `extractors/` 下创建新提取器
2. 在 `extractors/__init__.py` 中注册
3. 在 `config.py` 中添加类型配置

---

## 更新日志

### V2.4 (当前版本)

- 新增Web前端（Vue3 + TypeScript）
- 知识库管理页面
- 案例搜索页面
- Element Plus UI

### V2.3

- 新增HTTP API（FastAPI）
- Token鉴权
- 完整的RESTful接口
- Swagger文档支持

### V2.2

- 新增FAISS向量检索
- 支持语义相似搜索
- 混合检索（向量 + 规则）
- 批量重建索引策略

### V2.1

- 扩展提取字段：区域、楼层、建成年份、价值时点等
- 扩展知识库索引
- 增强相似案例匹配（多维度权重）
- 新增输入表单定义
- 新增LLM语义审查

### V2.0

- 模块化重构
- 分离提取器/校验器/知识库/审查器/生成器
- 支持CLI和Python API
