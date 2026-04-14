# AIAD 智能原生广告植入引擎 - 实验方案与团队协作报告

## 一、 实验命题与方案概述

**1.1 实验命题**
本小组选定的实验命题为：**基于多模态大模型的社区内容（小红书）智能原生广告（Native Advertising）植入引擎**。
随着内容社区商业化的推进，生硬的广告植入极易引起用户反感。本实验旨在利用 AI 智能体技术，深入解析小红书帖子的图文/视频特征及评论区语境，自动生成高度契合场景、带有网感且不引起反感的植入式广告评论，从而提升转化率。

**1.2 实验核心目标**
构建一套端到端（End-to-End）的自动化智能营销系统，实现从“目标贴抓取 -> 多模态语义分析 -> 相似高转化案例检索 -> 拟人化文案生成 -> 前端交互展示”的全链路智能闭环。

---

## 二、 AI 技术栈与核心组件设计

为保障实验方案的落地，我们采用了以下先进的 AI 技术栈和架构组件：

**2.1 智能体编排 (Agent Orchestration)**
- **Langgraph**：作为工作流引擎，将复杂的生成任务拆解为多个子 Agent（数据抓取、视觉分析、情感理解、生成），通过有向图（Graph）定义各 Agent 的数据流转和条件路由（如生成质量不达标则触发重写）。选用依据：相比线性流，Langgraph 提供了极佳的循环（Cyclic）处理能力和状态（State）管理机制，适合处理长链路且需要自我校验的 AI 任务。

**2.2 模型上下文协议 (MCP - Model Context Protocol)**
- **MCP 接入层**：将外部工具（如 MediaCrawler 爬虫脚本、ChromaDB 检索接口）封装为标准的 MCP Server。
- **选用依据**：使得核心大模型（LLM）能够通过标准化的协议直接调用本地爬虫环境或数据库，降低了硬编码 API 的耦合度，提升了系统的可扩展性。

**2.3 规则系统与防风控机制 (Rule System & Guardrails)**
- **安全与风控规则**：在生成阶段引入 Guardrails，强制校验生成的评论是否包含违禁词、是否符合《广告法》要求、是否过度生硬。
- **爬虫风控规则**：配置随机 User-Agent 库和请求间隔（`time.sleep(random.uniform(1, 3))`）来绕过小红书反爬。

**2.4 技能模块库 (Skills Library)**
- 独立编写并封装的一系列原子化技能：`fetch_xhs_comments()`、`analyze_image_vibe()`、`query_rag_chroma()`。这些 Skill 挂载在不同的 Agent 上，作为其可用工具（Tools）。

---

## 三、 团队分工与角色映射 (8人制)

结合软件工程规范与多智能体架构，我们为 8 位组员分配了具体的研发角色，并严格对齐了前期的智能体（Agent）分配：

| 组员 | 软件工程角色 | 负责的智能体 / 模块 | 具体职责说明 |
| :--- | :--- | :--- | :--- |
| **队员 1** | **数据工程师 (Data Engineer)** | **Data Harvester Agent**<br>(数据采集与清洗智能体) | 负责 MediaCrawler 爬虫模块开发与 MCP 封装。处理小红书反爬，清洗图文/评论流为标准 JSON。 |
| **队员 2** | **算法工程师 (Vision AI)** | **Vision Analyst Agent**<br>(多模态视觉理解智能体) | 负责调用视觉大模型（如 GPT-4V），提取图片/视频中的场景、商品类别、人物情绪及氛围。 |
| **队员 3** | **算法工程师 (NLP)** | **Context NLP Agent**<br>(评论区语境与情感智能体) | 负责分析现有评论区数据，进行情感分析，挖掘用户痛点与流行语境，提炼植入切入点。 |
| **队员 4** | **数据库工程师 (DBA)** | **RAG & Memory Agent**<br>(记忆与检索智能体) | 搭建与维护 Chroma 向量数据库，负责历史成功广告与产品知识库的向量化及语义相似度检索。 |
| **队员 5** | **提示词工程师 (Prompt Engineer)** | **Creative Copywriter Agent**<br>(核心文案生成智能体) | 聚合所有前置信息，设计 System Prompt，生成多风格（测评、安利等）且极具吸引力的自然植入式广告。 |
| **队员 6** | **后端架构师 (Backend/Arch)** | **Langgraph Orchestrator Agent**<br>(工作流编排与路由智能体) | 负责 Langgraph 的状态图构建与全局 State 定义。设计条件路由，串联所有 Agent，并暴露后端 API。 |
| **队员 7** | **交互设计师 (UI/UX Designer)** | **UX/UI Design Agent**<br>(场景交互设计智能体) | 使用 Figma 设计完整的前端 SaaS 页面：首页输入、加载动画、多模态仪表盘及最终广告结果展示。 |
| **队员 8** | **前端工程师 (Frontend Dev)** | **Vue3 Frontend Agent**<br>(前端开发与对接智能体) | 使用 Vue3 1:1 还原 Figma 设计稿。对接后端 Langgraph API，实现实时进度展示与动态结果交互。 |

> ⚠️ **全员质量与测试保障要求（极度重要）**：
> 本项目取消专职的 QA/测试工程师岗位，实行**全员全栈测试机制**。
> 每位组员**必须自行保证**其负责的 Agent 模块的**单元测试（Unit Testing）**和独立运行的**功能性测试（Functional Testing）**。在将各自的模块融合进入 Langgraph 整体系统时，每位开发者必须参与端到端（E2E）联调，**确保整体系统的运行正常、稳定，且不阻塞数据上下文流转**。任何单一 Agent 的故障不应引发全局崩溃。

---

## 四、 团队协作措施与规范

**4.1 代码仓库与版本控制策略**
- **仓库架构**：采用 Mono-repo（单体仓库）结构，将 `frontend/`、`backend/`、`agents/`、`crawler/` 放在同一 Git 仓库下，便于整体联调。
- **Git Flow**：
  - `main`：生产环境主分支，必须通过 PR 且全自动化测试通过后合并。
  - `develop`：集成测试分支，各组员的特性分支（`feature/agent-vision` 等）开发完毕后，向 `develop` 发起 PR。
  - **Code Review**：每次 PR 必须至少有一名其他组员进行 Review，确保代码质量和 API 接口契合度。

**4.2 技能模块与脚本编写标准**
- **语言标准**：后端与 Agent 开发统一使用 Python 3.10+。
- **环境隔离**：严格使用 Conda 管理环境，主工程使用 `aiad` 环境，爬虫工程使用 `mediacrawler` 环境。
- **健壮性与日志**：所有核心 Skill 必须包含完整的 `try-except` 异常捕获机制，严禁使用裸 `print()`，统一使用 Python `logging` 模块输出结构化日志（包含时间戳、级别、所在 Agent）。
- **注释规范**：遵循 PEP8 规范，函数级别必须提供 Docstring 描述参数、返回值和核心逻辑。

---

## 五、 工具链与 AI 智能体集成

**5.1 开发框架**
- **Langgraph / Langchain**：作为 Agent 的底层开发框架，提供节点定义和记忆管理能力。
- **FastAPI**：将 Langgraph 编排后的系统暴露为 RESTful / WebSocket API，供前端调用。
- **Vue3 + TailwindCSS**：快速构建具有科技感的前端界面。

**5.2 CI/CD 工具链与全员自动化测试**
- **GitHub Actions**：编写 `.github/workflows/main.yml`，每次提交自动触发代码 Linting（Flake8 / Black）、单元测试（Pytest）以及前端构建。
- **全自动测试卡点**：在 CI 流程中，注入一个虚拟的“发帖数据”，流水线会自动运行端到端的链路评估。**只有在所有队员负责的 Agent 模块均通过单元测试与系统级联调测试后，PR 才允许被合并**。这进一步贯彻了全员质量保障的理念。

**5.3 监控与观测平台**
- **LangSmith**：深度集成至所有的 Agent 调用中，实现“执行轨迹跟踪（Tracing）”。团队可通过 LangSmith 面板直接查看每一步 Prompt 的输入输出、耗时及 Token 成本。
- **Prometheus + Grafana**：用于监控 FastAPI 后端和 ChromaDB 数据库的运行指标（如 QPS、内存占用率）。

---

## 六、 自动生成报告与 PDF 提交说明

实验的最终验收将体现 AI 自动化的极致：
我们将在 Langgraph 链路的最后，增加一个名为 `Document Generation Agent` 的报告生成智能体。
该 Agent 会：
1. 读取各节点的运行日志（Auto-Log）。
2. 聚合生成的广告用例、成功率统计数据以及 LangSmith 导出的图表。
3. 利用 Markdown 模板引擎生成完整的《实验报告.md》。
4. 调用 `WeasyPrint` 或 `Pandoc` 等自动化工具链，将 Markdown 文件无损转换为符合学术/工程规范的 **PDF 格式**。
最终，小组只需一键执行指令，即可自动生成并提交最终的 PDF 实验报告。