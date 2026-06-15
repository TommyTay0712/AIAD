# AIAD (AI Advertising Discovery)

AIAD 是一个面向广告洞察与评论区软植入生成的实验项目，当前仓库包含：

- API Gateway (入口与代理)
- Task Service (任务编排与 SSE 推送)
- Crawler Service (爬虫封装，**宿主机运行**）
- Analysis Service (视觉、NLP 评论分析、RAG)
- Copywriter Service (软植入文案生成)
- Vue 3 + Vite 前端（内嵌 Nginx 镜像）

## 项目结构

```text
AIAD/
├─ services/               # 微服务集群目录
│  ├─ gateway/             # API Gateway
│  ├─ task/                # 任务与流水线服务
│  ├─ crawler/             # 采集服务（宿主机启动）
│  ├─ analysis/            # 分析服务
│  ├─ copywriter/          # 文案生成服务
│  └─ shared/              # 共享数据结构与配置
├─ frontend/               # Vue 3 + Vite 前端
├─ vendor/MediaCrawler/    # 第三方爬虫（submodule）
├─ assets/seeds/           # Agent 4 预置种子
├─ data/raw/               # 原始抓取数据
├─ data/processed/         # 处理后结果
├─ ai_logs/autologs/       # AI 辅助开发日志
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

## 启动方式（当前架构）

> **架构说明**：Crawler Service 需要访问宿主机浏览器（Chrome），无法在 Docker 容器内正常运行。
> 因此采用**部分 Docker 化**方案：Crawler 在宿主机 Windows 启动，其余服务全部跑 Docker。

### 第一步：准备环境变量

```powershell
Copy-Item .env.example .env
```

打开 `.env`，至少填入：

```env
LLM_API_KEY=你的_ModelScope_Token
VISION_API_KEY=你的_ModelScope_Token
```

### 第二步：启动 Crawler Service（宿主机，终端 1）

```powershell
E:\AIAD\.conda\aiad\python.exe -m uvicorn services.crawler.main:app --host 0.0.0.0 --port 8002
```

Crawler Service 监听 `http://localhost:8002`，Docker 容器通过 `host.docker.internal:8002` 访问它。

### 第三步：启动其余服务（Docker，终端 2）

```powershell
docker-compose up --build -d
```

首次构建约需几分钟。启动后各服务端口：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 + Gateway 入口 | `http://localhost:8000` | 通过 Nginx 统一对外 |
| Task Service | `http://localhost:8001` | 内部服务 |
| Crawler Service | `http://localhost:8002` | **宿主机进程** |
| Analysis Service | `http://localhost:8003` | 内部服务 |
| Copywriter Service | `http://localhost:8004` | 内部服务 |
| Redis | `localhost:6379` | 内部服务 |

打开浏览器访问 `http://localhost:8000` 即可使用。

### 小红书登录说明

- 每次发起抓取任务时，MediaCrawler 会**自动弹出 Chrome 窗口**，在窗口内完成小红书扫码/手机验证登录。
- 登录完成后爬虫自动继续，无需在网页端做任何操作。
- Cookie 有效期较短，每次抓取前通常需要重新登录。

---

## Conda 环境

本项目使用两个独立的 Conda 环境：

| 环境 | 路径 | 用途 |
|------|------|------|
| `aiad` | `E:\AIAD\.conda\aiad\python.exe` | 主工程（API、服务、测试） |
| `mediacrawler` | `E:\AIAD\.conda\mediacrawler\python.exe` | MediaCrawler 子进程 |

首次创建：

```powershell
conda env create -f environment.aiad.yml
```

更新已有环境：

```powershell
conda env update -f environment.aiad.yml --prune
```

---

## Agent 4 初始化

```powershell
.\scripts\bootstrap_agent4.ps1 -Python E:\AIAD\.conda\aiad\python.exe
```

验证状态：

```powershell
E:\AIAD\.conda\aiad\python.exe -m app.services.memory.cli status
E:\AIAD\.conda\aiad\python.exe -m app.services.memory.cli probe tests/memory/fixtures/mock_global_state_beach.json
```

---

## 前端开发模式（可选）

正常使用时前端已内嵌在 Nginx Docker 镜像中，无需单独启动。

如需热重载开发：

```powershell
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

然后访问 `http://localhost:5173`（直连 Vite Dev Server，不经过 Nginx）。

---

## 接口文档

- Swagger：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

---

## 常用接口

### 主流程

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ad-intel/run` | 创建分析任务 |
| GET | `/api/ad-intel/task/{task_id}/stream` | SSE 实时进度 |
| GET | `/api/ad-intel/task/{task_id}/meta` | 任务最终结果 |
| GET | `/api/ad-intel/task/{task_id}/insights` | 洞察数据（前端用） |

### Agent 联调

| 方法 | 路径 |
|------|------|
| GET | `/api/ad-intel/agents/state-schema` |
| POST | `/api/ad-intel/agents/vision/run` |
| POST | `/api/ad-intel/agents/context/run` |
| POST | `/api/ad-intel/agents/rag/run` |
| POST | `/api/ad-intel/agents/copywriter/run` |

---

## 环境变量说明

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | ModelScope API Token（LLM 调用） |
| `VISION_API_KEY` | ModelScope API Token（视觉分析） |
| `LLM_MODEL` | 默认 `Qwen/Qwen3.5-397B-A17B` |
| `MEDIACRAWLER_PYTHON_EXE` | MediaCrawler 解释器路径 |
| `PLAYWRIGHT_BROWSERS_PATH` | Playwright 浏览器缓存目录 |
| `CRAWLER_SUBPROCESS_TIMEOUT` | 爬虫子进程超时秒数（默认 480） |
| `HEADLESS_BROWSER` | `false` = 显示浏览器窗口（推荐，方便登录） |
| `AIAD_API_KEYS` | 逗号分隔的合法 API Key，留空则跳过认证 |

API Key 不要提交到仓库。`.env` 已在 `.gitignore` 中。

---

## 本地质量检查

```powershell
# 单元测试
E:\AIAD\.conda\aiad\python.exe -m pytest tests -q

# 类型检查
E:\AIAD\.conda\aiad\python.exe -m mypy app tests
```

---

## 联调文档

- 智能体接口与并行开发规范：`docs/智能体接口与并行开发规范.md`
- 项目分工与路线规划：`docs/项目分工与路线规划.md`
