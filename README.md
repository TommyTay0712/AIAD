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

## 启动方式（Conda）

### 0) 克隆仓库（包含 vendor 子仓）

首次克隆请使用：

```bash
git clone --recurse-submodules https://github.com/TommyTay0712/AIAD.git
```

如果已经克隆过主仓库，请执行一次：

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

后续更新主仓库后，也建议执行：

```bash
git pull --rebase
git submodule update --init --recursive
```

### 1) AIAD 后端 + 前端（同一个服务）

说明：前端是 Vue 单页，由 FastAPI 静态托管，所以只需要启动一个服务。

安装依赖：

```bash
E:\AIAD\.conda\aiad\python.exe -m pip install -r requirements.txt
```

启动服务：

```bash
E:\AIAD\.conda\aiad\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

```

访问页面：

```text
http://127.0.0.1:8000/
```

### 1.1) AIAD 环境初始化（Conda）

如需在本地或 CI 中复用统一的 AIAD 环境，可直接使用根目录的 `environment.aiad.yml`：

```bash
conda env create -f environment.aiad.yml
conda activate aiad
```

如果环境已存在，可执行：

```bash
conda env update -f environment.aiad.yml --prune
conda activate aiad
```

### 1.2) 本地校验命令

激活 `aiad` 环境后，执行：

```bash
python -m pytest tests -q
python -m mypy app tests
```

### 2) MediaCrawler 独立环境（仅调试时手动运行）

安装 MediaCrawler 依赖：

```bash
E:\AIAD\.conda\mediacrawler\python.exe -m pip install -r requirements.txt
```

二维码登录抓取示例：

```bash
set PLAYWRIGHT_BROWSERS_PATH=E:\AIAD\.ms-playwright
E:\AIAD\.conda\mediacrawler\python.exe main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path E:\AIAD\data\raw\xhs_real
```

## 开发框架

- 后端：FastAPI
- 工作流：LangGraph（当前仅编排数据整理节点，不启用AI分析）
- 数据库：ChromaDB（先用于高并发写入与特征数据检索验证）
- 前端：Vue 3（CDN 版本，单页）

## 环境变量说明

复制 `.env.example` 为 `.env` 后按需调整：

- `MEDIA_CRAWLER_DIR`：MediaCrawler 路径
- `CRAWLER_OUTPUT_DIR`：原始数据目录
- `PROCESSED_OUTPUT_DIR`：处理结果目录
- `CHROMA_PERSIST_DIR`：ChromaDB 持久化目录
- `MEDIACRAWLER_PYTHON_EXE`：MediaCrawler Python 解释器路径
- `PLAYWRIGHT_BROWSERS_PATH`：Playwright 浏览器目录
- `LOGS_DIR`：日志目录
- `TASK_STORE_FILE`：任务状态文件

## MediaCrawler 运行说明

建议使用项目内可写浏览器目录：

```bash
set PLAYWRIGHT_BROWSERS_PATH=E:\AIAD\.ms-playwright
```

非无头二维码登录示例：

```bash
E:\AIAD\.conda\mediacrawler\python.exe main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path E:\AIAD\data\raw\xhs_real
```

## 接口说明

### POST `/api/ad-intel/run`

请求体：

```json
{
  "ad_type": "",
  "keywords": [],
  "platform": "xhs",
  "limit": 20,
  "max_comments_per_note": 10,
  "enable_media_download": false,
  "time_range": ""
}
```

返回：

```json
{"task_id":"...","status":"running","message":"任务已提交，正在抓取并整理数据"}
```

失败时返回：

```json
{"detail":{"error_code":"LOGIN_REQUIRED","message":"..."}}
```

### GET `/api/ad-intel/task/{task_id}`

- 任务成功：返回 machine-readable JSON，包含 `summary/content_table/comment_table/feature_table`
- 任务运行中或失败：返回任务状态与错误码
