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

### 0) 环境约定

- AIAD 主工程使用独立 Conda 前缀环境：`.conda/aiad`
- MediaCrawler 使用独立 Conda 前缀环境：`.conda/mediacrawler`
- Playwright 浏览器统一下载到项目目录：`.ms-playwright`
- macOS/Linux 默认解释器路径：
  - AIAD: `.conda/aiad/bin/python`
  - MediaCrawler: `.conda/mediacrawler/bin/python`
- Windows 默认解释器路径：
  - AIAD: `.conda/aiad/python.exe`
  - MediaCrawler: `.conda/mediacrawler/python.exe`

### 1) 克隆仓库（包含 vendor 子仓）

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

### 2) 初始化 Conda 环境

macOS/Linux 推荐直接执行：

```bash
bash scripts/setup_conda_envs.sh
```

如果当前机器还没有 `conda`，可以先安装 Miniforge：

```bash
brew install --cask miniforge
```

Windows 可继续使用项目内前缀环境，分别创建 `.conda/aiad` 与 `.conda/mediacrawler`。

### 3) AIAD 后端 + 前端（同一个服务）

说明：前端是 Vue 单页，由 FastAPI 静态托管，所以只需要启动一个服务。

启动服务：

```bash
./.conda/aiad/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问页面：

```text
http://127.0.0.1:8000/
```

### 4) MediaCrawler 独立环境（仅调试时手动运行）

安装 MediaCrawler 依赖：

```bash
./.conda/mediacrawler/bin/python -m pip install -r vendor/MediaCrawler/requirements.txt
```

二维码登录抓取示例：

```bash
cd vendor/MediaCrawler
PLAYWRIGHT_BROWSERS_PATH="$PWD/../../.ms-playwright" ../../.conda/mediacrawler/bin/python main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path "$PWD/../../data/raw/xhs_real"
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
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.ms-playwright"
```

非无头二维码登录示例：

```bash
cd vendor/MediaCrawler
../../.conda/mediacrawler/bin/python main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path "$PWD/../../data/raw/xhs_real"
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
