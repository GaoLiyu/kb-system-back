# 房地产估价知识库系统 V3.0

智能房地产估价报告管理、审查与知识库系统。

## 功能特性

- **知识库管理**：报告入库、案例提取、向量索引
- **智能审查**：规则校验 + LLM语义审查，支持异步批量处理
- **案例搜索**：多条件筛选、向量相似检索
- **统计面板**：数据可视化、审查统计
- **报告导出**：审查结果导出为Word文档

## 系统架构
```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Vue3 + Element Plus)              │
│                       http://localhost:80                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Nginx 反向代理                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (:8000)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  报告提取   │  │  规则校验   │  │  LLM审查    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│  ┌─────────────────────────────────────────────┐            │
│  │         ThreadPoolExecutor (异步任务)        │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ PostgreSQL  │      │   Milvus    │      │ LLM API     │
│  (元数据)    │      │  (向量库)    │      │ (语义审查)   │
│   :54321    │      │   :19530    │      │             │
└─────────────┘      └─────────────┘      └─────────────┘
```

## 快速开始

### 1. 部署数据库

#### PostgreSQL
```bash
docker run -d \
  --name postgres \
  --restart always \
  -e POSTGRES_USER=kb_admin \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=real_estate_kb \
  -v /data/postgres:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:15
```

#### Milvus
```bash
mkdir -p /data/milvus && cd /data/milvus
wget https://github.com/milvus-io/milvus/releases/download/v2.3.4/milvus-standalone-docker-compose.yml -O docker-compose.yml
docker compose up -d
```

### 2. 部署应用
```bash
# 拉取代码
./deploy.sh pull

# 安装部署
sudo PG_PASSWORD=your_password bash ./deploy.sh install

# 初始化数据库
cd /data/python/real-estate-kb
source venv/bin/activate
python scripts/init_db.py
```

### 3. 访问系统

- 前端界面：http://localhost
- API文档：http://localhost:8000/docs

## 配置说明

### 环境变量 (.env)
```bash
# 服务配置
KB_HOST=0.0.0.0
KB_PORT=8000
KB_DEBUG=false
KB_API_TOKEN=your_token

# 功能开关
KB_ENABLE_VECTOR=true
KB_ENABLE_LLM=true
KB_USE_DATABASE=true

# PostgreSQL
PG_HOST=127.0.0.1
PG_PORT=5432
PG_USER=kb_admin
PG_PASSWORD=your_password
PG_DATABASE=real_estate_kb

# Milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=case_vectors

# LLM
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-R1-Distill-Qwen-32B

# 嵌入模型
KB_EMBEDDING_MODEL_PATH=/data/models/bge-large-zh-v1.5
```

## 数据库表结构

### documents（报告表）

| 字段 | 类型 | 说明 |
|------|------|------|
| doc_id | VARCHAR(64) | 文档ID，主键 |
| filename | VARCHAR(255) | 文件名 |
| report_type | VARCHAR(50) | 报告类型 |
| address | TEXT | 估价对象地址 |
| case_count | INT | 案例数量 |
| metadata | JSONB | 扩展元数据 |

### cases（案例表）

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | VARCHAR(64) | 案例ID，主键 |
| doc_id | VARCHAR(64) | 关联文档ID |
| address | TEXT | 案例地址 |
| district | VARCHAR(100) | 区域 |
| area | FLOAT | 面积 |
| price | FLOAT | 单价 |
| usage | VARCHAR(50) | 用途 |
| case_data | JSONB | 完整案例数据 |

### review_tasks（审查任务表）

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | VARCHAR(64) | 任务ID，主键 |
| filename | VARCHAR(255) | 文件名 |
| status | VARCHAR(20) | 状态：pending/running/completed/failed |
| overall_risk | VARCHAR(20) | 风险等级 |
| issue_count | INT | 问题总数 |
| result | JSONB | 完整审查结果 |
| create_time | TIMESTAMP | 创建时间 |

## API 接口

### 知识库管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/kb/upload` | POST | 上传报告入库 |
| `/api/kb/batch-upload` | POST | 批量上传 |
| `/api/kb/reports` | GET | 报告列表 |
| `/api/kb/cases` | GET | 案例列表 |
| `/api/kb/stats` | GET | 统计信息 |

### 审查任务

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/review/submit` | POST | 提交审查任务 |
| `/api/review/submit-batch` | POST | 批量提交任务 |
| `/api/review/tasks` | GET | 任务列表 |
| `/api/review/task/{id}` | GET | 任务详情 |
| `/api/review/task/{id}/export` | POST | 导出结果 |

### 搜索

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/search/cases` | POST | 条件搜索 |
| `/api/search/similar` | POST | 相似案例 |
| `/api/search/vector` | POST | 向量搜索 |

### 统计

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stats/overview` | GET | 总览统计 |
| `/api/stats/reports` | GET | 报告统计 |
| `/api/stats/cases` | GET | 案例统计 |
| `/api/stats/review` | GET | 审查统计 |

## 目录结构
```
/data/python/real-estate-kb/
├── api/                        # FastAPI 接口
│   ├── routes/                 # 路由
│   │   ├── kb.py               # 知识库接口
│   │   ├── review.py           # 审查接口
│   │   ├── search.py           # 搜索接口
│   │   └── stats.py            # 统计接口
│   ├── task_manager.py         # 异步任务管理
│   ├── config.py               # 配置
│   └── app.py                  # 应用入口
├── extractors/                 # 报告提取器
│   ├── shezhi_extractor.py     # 涉执报告
│   ├── zujin_extractor.py      # 租金报告
│   ├── biaozhunfang_extractor.py # 标准房报告
│   └── content_extractor.py    # 原文提取
├── knowledge_base/             # 知识库管理
│   ├── kb_manager.py           # 文件版
│   ├── kb_manager_db.py        # 数据库版
│   ├── vector_store.py         # FAISS
│   ├── vector_store_milvus.py  # Milvus
│   └── db_connection.py        # 数据库连接
├── reviewer/                   # 审查模块
│   ├── report_reviewer.py      # 综合审查
│   ├── llm_reviewer.py         # LLM审查
│   └── report_exporter.py      # 导出
├── validators/                 # 校验器
├── scripts/                    # 脚本
│   ├── init_db.py              # 初始化数据库
│   └── migrate_data.py         # 数据迁移
├── web/                        # 前端源码
├── static/                     # 前端构建产物
├── logs/                       # 日志
├── uploads/                    # 上传文件
├── main.py                     # 主程序
├── deploy.sh                   # 部署脚本
└── .env                        # 配置文件
```

## 常用命令
```bash
# 服务管理
sudo systemctl start real-estate-kb
sudo systemctl stop real-estate-kb
sudo systemctl restart real-estate-kb
sudo systemctl status real-estate-kb

# 查看日志
tail -f /data/python/real-estate-kb/logs/api.log
tail -f /data/python/real-estate-kb/logs/api.error.log

# 数据库
docker exec -it postgres psql -U kb_admin -d real_estate_kb

# 前端构建
cd /data/python/real-estate-kb/web
npm run build
cp -r dist/* ../static/
```

## 更新日志

### V3.0 (2024-12)

- 新增异步审查任务（线程池）
- 新增审查任务管理页面
- 新增审查日志和统计
- 优化段落过滤（减少无意义内容）
- 支持审查报告导出

### V2.5

- 新增 PostgreSQL + Milvus 数据库支持
- 新增审查详情页（原文高亮）
- 新增批量上传/审查
- 新增统计面板

### V2.0

- 基础知识库管理
- 报告提取和校验
- LLM语义审查
- 案例搜索