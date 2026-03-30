# AIAD (AI Advertising Discovery)

## 项目结构

```text
AIAD/
├─ app/
│  ├─ api/                 # 接口层
│  ├─ core/                # 配置与日志
│  ├─ models/              # 数据模型
│  ├─ services/            # 爬虫调用与数据清洗
│  └─ workflows/           # LangGraph 工作流编排（当前仅数据整理）
├─ frontend/               # 最小前端页面
├─ tests/                  # 最小测试
├─ vendor/MediaCrawler/    # 第三方爬虫副本（隔离）
├─ data/raw/               # 爬虫原始输出收口目录
├─ data/processed/         # 数据整理结果目录
└─ scripts/dev.ps1         # 一键开发启动脚本
```

## 启动方式

1. 安装依赖：

```bash
python -m pip install -r requirements.txt
```

2. 启动服务：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

3. 打开页面：

```text
http://127.0.0.1:8000/
```

## 开发框架

- 后端：FastAPI
- 工作流：LangGraph（当前仅编排数据整理节点，不启用AI分析）
- 前端：原生 HTML + JS（最小可用页面）

## 环境变量说明

复制 `.env.example` 为 `.env` 后按需调整：

- `MEDIA_CRAWLER_DIR`：MediaCrawler 路径
- `CRAWLER_OUTPUT_DIR`：原始数据目录
- `PROCESSED_OUTPUT_DIR`：处理结果目录
- `LOGS_DIR`：日志目录
- `TASK_STORE_FILE`：任务状态文件

## 接口说明

### POST `/api/ad-intel/run`

请求体：

```json
{"ad_type":"","keywords":[],"platform":"xhs","limit":20,"time_range":""}
```

返回：

```json
{"task_id":"...","status":"success","message":"data/processed/...json"}
```

失败时返回：

```json
{"detail":{"error_code":"LOGIN_REQUIRED","message":"..."}}
```

### GET `/api/ad-intel/task/{task_id}`

- 任务成功：返回 machine-readable JSON，包含 `summary/content_table/comment_table/feature_table`
- 任务运行中或失败：返回任务状态与错误码
