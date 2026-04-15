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

## 启动方式（Linux / Conda）

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

建议优先使用当前 Conda 环境中的 Python：

```bash
python3 -m pip install -r requirements.txt
```

启动服务：

```bash
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问页面：

```text
http://127.0.0.1:8000/
```

运行测试：

```bash
python3 -m pytest -q
```

### 2) MediaCrawler 独立环境（仅调试时手动运行）

安装 MediaCrawler 依赖：

```bash
python3 -m pip install -r requirements.txt
```

二维码登录抓取示例：

```bash
export PLAYWRIGHT_BROWSERS_PATH=.ms-playwright
python3 main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path data/raw/xhs_real
```

## 开发框架

- 后端：FastAPI
- 工作流：LangGraph（当前已包含 Agent2 视觉分析节点，默认支持 Mock 回退）
- 数据库：ChromaDB（先用于高并发写入与特征数据检索验证）
- 前端：Vue 3（CDN 版本，单页）

## 环境变量说明

复制 `.env.example` 为 `.env` 后按需调整：

- `MEDIA_CRAWLER_DIR`：MediaCrawler 路径
- `CRAWLER_OUTPUT_DIR`：原始数据目录
- `PROCESSED_OUTPUT_DIR`：处理结果目录
- `CHROMA_PERSIST_DIR`：ChromaDB 持久化目录
- `AIAD_PYTHON_EXE`：主工程 Python 解释器路径
- `MEDIACRAWLER_PYTHON_EXE`：MediaCrawler Python 解释器路径
- `PLAYWRIGHT_BROWSERS_PATH`：Playwright 浏览器目录
- `LOGS_DIR`：日志目录
- `TASK_STORE_FILE`：任务状态文件
- `VISION_PROVIDER`：视觉模型提供方，`mock` 表示仅启用本地回退
- `VISION_MODEL`：视觉模型名称，默认示例为 `Qwen/Qwen3.5-397B-A17B`
- `VISION_API_BASE`：OpenAI-compatible 视觉接口地址，默认示例为 `https://api-inference.modelscope.cn/v1`
- `VISION_API_KEY`：视觉模型 API Key
- `VISION_ENABLE_MOCK_FALLBACK`：远程失败时是否回退到 Mock
- `VISION_MAX_MEDIA_COUNT`：单次任务最多分析的媒体数

## MediaCrawler 运行说明

建议使用项目内可写浏览器目录：

```bash
export PLAYWRIGHT_BROWSERS_PATH=.ms-playwright
```

非无头二维码登录示例：

```bash
python3 main.py --platform xhs --lt qrcode --type search --keywords 美食 --headless false --save_data_option jsonl --save_data_path data/raw/xhs_real
```

## Agent 联调接口

### GET `/api/ad-intel/agents/state-schema`

返回 1-5 号 Agent 联调使用的全局状态模板，字段包括：

- `request_info`
- `raw_data`
- `vision_analysis`
- `nlp_analysis`
- `rag_references`
- `final_ads`
- `review_score`

这个接口的作用是给各 Agent 同学一个统一的 `mock_state` 契约。

### POST `/api/ad-intel/agents/vision/run`

单独执行 Agent2。

请求体：

```json
{
  "media_paths": ["data/raw/example/media/0.jpg", "data/raw/example/media/1.jpg"]
}
```

返回体：

```json
{
  "scene": "海边/沙滩",
  "vibe": "轻松夏日",
  "detected_items": ["草帽", "墨镜"],
  "people_emotions": ["放松"],
  "visual_highlights": ["真实场景感强"],
  "risk_flags": [],
  "source_media_count": 2,
  "model_provider": "modelscope",
  "model_name": "Qwen/Qwen3.5-397B-A17B"
}
```

### POST `/api/ad-intel/agents/context/run`

单独执行 Agent3，当前提供可联调的启发式版本。

请求体：

```json
{
  "comments": [
    {"user": "A", "content": "求链接，这个真的好用吗？", "likes": 12},
    {"user": "B", "content": "敏感肌也能用吗", "likes": 3}
  ],
  "product_info": "敏感肌防晒霜"
}
```

返回体字段：

- `main_emotion`
- `pain_points`
- `language_style`
- `ad_angles`
- `keyword_summary`

### POST `/api/ad-intel/agents/rag/run`

单独执行 Agent4，当前提供可联调的最小检索接口。

请求体：

```json
{
  "vision_analysis": {
    "scene": "海边/沙滩",
    "vibe": "轻松夏日",
    "detected_items": ["草帽"]
  },
  "nlp_analysis": {
    "main_emotion": "高兴趣，带明显购买/求购意图",
    "pain_points": ["用户关注防晒效果与场景适配"],
    "language_style": "提问型互动明显",
    "ad_angles": ["从真实使用体验切入，再顺带给出购买建议"],
    "keyword_summary": ["求链接", "防晒"]
  },
  "top_k": 3
}
```

返回体：

```json
[
  "这个海边/沙滩的氛围真的很适合做自然种草，顺着轻松夏日的感觉补一句体验就很顺。",
  "评论区现在是“高兴趣，带明显购买/求购意图”的语境，建议不要硬推，先回应顾虑再带产品。",
  "如果围绕从真实使用体验切入，再顺带给出购买建议来写，广告感会比直接报产品卖点弱很多。"
]
```

### POST `/api/ad-intel/agents/copywriter/run`

单独执行 Agent5，当前提供可联调的最小文案生成接口。

请求体：

```json
{
  "request_info": {
    "product_info": "敏感肌防晒霜",
    "target_style": "测评风"
  },
  "vision_analysis": {
    "scene": "海边/沙滩",
    "vibe": "轻松夏日"
  },
  "nlp_analysis": {
    "main_emotion": "高兴趣，带明显购买/求购意图",
    "pain_points": ["用户关注防晒效果与场景适配"],
    "language_style": "提问型互动明显",
    "ad_angles": ["从真实使用体验切入，再顺带给出购买建议"],
    "keyword_summary": ["求链接", "防晒"]
  },
  "rag_references": ["高转化文案通常先像普通用户分享，再自然补一句为什么会回购。"],
  "styles": ["测评风", "科普风"]
}
```

返回体：

```json
[
  {"style": "测评风", "content": "..."},
  {"style": "科普风", "content": "..."}
]
```

## 主流程接口

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

- 任务成功：返回 machine-readable JSON，包含 `summary/content_table/comment_table/feature_table/vision_analysis`
- 任务运行中或失败：返回任务状态与错误码

### 设计说明

- 主流程接口面向前端与完整任务。
- `agents/*` 接口面向 2-5 号 Agent 的单独联调和 mock 驱动开发。
- 当前 Agent3/4/5 是“先定接口、后换实现”的版本：输入输出 schema 稳定，后续可以只替换内部逻辑。
