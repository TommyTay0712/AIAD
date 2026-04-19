# AIAD (AI Advertising Discovery)

AIAD 是一个面向广告洞察与评论区软植入生成的实验项目，当前仓库包含：

- FastAPI 后端
- LangGraph 工作流编排
- Agent 2 视觉分析
- Agent 3 评论区语境分析
- Agent 4 RAG / Memory
- Agent 5 文案生成
- Vue 3 + Vite 前端

## 项目结构

```text
AIAD/
├─ app/                    # 后端应用
│  ├─ api/                 # API 路由
│  ├─ core/                # 配置与日志
│  ├─ models/              # Pydantic 数据模型
│  ├─ services/            # 各 Agent 与基础服务
│  └─ workflows/           # LangGraph 工作流
├─ assets/seeds/           # Agent 4 预置种子
├─ docs/                   # 协作文档
├─ frontend/               # Vue 3 + Vite 前端
├─ tests/                  # 测试
├─ vendor/MediaCrawler/    # 第三方爬虫
├─ data/raw/               # 原始抓取数据
├─ data/processed/         # 处理后结果
└─ scripts/                # 初始化与辅助脚本
```

## 克隆仓库

```bash
git clone --recurse-submodules https://github.com/TommyTay0712/AIAD.git
cd AIAD
```

如果已经克隆过主仓库：

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

## 后端启动

推荐先复制环境变量模板：

```bash
cp .env.example .env
```

安装依赖并启动后端：

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

接口文档：

- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 前端启动

```bash
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

前端页面：`http://127.0.0.1:5173/`

## Conda 环境

仓库提供统一环境文件：

```bash
conda env create -f environment.aiad.yml
conda activate aiad
```

环境已存在时可更新：

```bash
conda env update -f environment.aiad.yml --prune
conda activate aiad
```

## Agent 4 初始化

Windows PowerShell:

```powershell
.\scripts\bootstrap_agent4.ps1 -Python E:\AIAD\.conda\aiad\python.exe
```

验证 Agent 4 状态：

```bash
python -m app.services.memory.cli status
python -m app.services.memory.cli probe tests/memory/fixtures/mock_global_state_beach.json
```

## MediaCrawler 调试

建议使用项目内可写浏览器目录：

```bash
export PLAYWRIGHT_BROWSERS_PATH=.ms-playwright
```

二维码登录示例：

```bash
python3 main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path data/raw/xhs_real
```

## 联调文档

- 智能体接口与并行开发规范：`docs/智能体接口与并行开发规范.md`
- 项目分工与路线规划：`docs/项目分工与路线规划.md`

## 环境变量

复制 `.env.example` 后按需修改，主要包括：

- 基础路径：`MEDIA_CRAWLER_DIR`、`CRAWLER_OUTPUT_DIR`、`PROCESSED_OUTPUT_DIR`
- Python 与浏览器：`AIAD_PYTHON_EXE`、`MEDIACRAWLER_PYTHON_EXE`、`PLAYWRIGHT_BROWSERS_PATH`
- 日志与任务：`LOGS_DIR`、`LOG_LEVEL`、`TASK_STORE_FILE`
- LLM：`LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`
- Vision：`VISION_PROVIDER`、`VISION_MODEL`、`VISION_API_BASE`、`VISION_API_KEY`
- Agent 4：`AGENT4_PERSIST_DIR`、`AGENT4_SEED_DIR`、`AGENT4_EMBEDDING_MODEL`

## 常用接口

### 主流程

- `POST /api/ad-intel/run`
- `GET /api/ad-intel/task/{task_id}`
- `GET /api/ad-intel/task/{task_id}/meta`
- `GET /api/ad-intel/task/{task_id}/insights`

### Agent 联调

- `GET /api/ad-intel/agents/state-schema`
- `POST /api/ad-intel/agents/vision/run`
- `POST /api/ad-intel/agents/context/run`
- `POST /api/ad-intel/agents/rag/run`
- `POST /api/ad-intel/agents/copywriter/run`

## 本地校验

```bash
python -m pytest tests -q
python -m mypy app tests
```
