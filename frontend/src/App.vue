<template>

      <aside class="fixed left-0 top-0 bottom-0 z-40 w-64 bg-slate-100 border-r border-slate-200/50 flex flex-col text-sm">
        <div class="p-8">
          <h1 class="text-xl font-headline font-extrabold text-blue-900">精准架构师</h1>
          <p class="text-xs text-on-surface-variant/80 mt-1">小红书评论广告助手</p>
        </div>
        <nav class="flex-1 px-4 space-y-1">
          <button v-for="nav in navItems" :key="nav.key" @click="setActiveScreen(nav.key)" class="w-full flex items-center gap-3 px-4 py-3 text-left rounded-xl transition-all duration-200"
            :class="activeScreen === nav.key ? 'text-blue-800 font-bold border-r-4 border-blue-800 bg-white/60' : 'text-slate-600 hover:text-blue-700 hover:bg-slate-200/50'">
            <span class="material-symbols-outlined" :class="activeScreen === nav.key ? 'active-fill' : ''">{{ nav.icon }}</span>
            <span>{{ nav.label }}</span>
          </button>
        </nav>
        <div class="p-4 mt-auto space-y-2">
          <button class="w-full signature-gradient text-white py-3 rounded-xl font-semibold flex items-center justify-center gap-2" @click="startNewCampaign">
            <span class="material-symbols-outlined text-sm">add</span>
            新建任务
          </button>
          <div class="px-2 pt-2 text-xs text-on-surface-variant">Stitch Project: {{ stitchProjectId }}</div>
        </div>
      </aside>

      <main class="ml-64 min-h-screen">
        <header class="h-16 flex justify-between items-center px-8 w-full border-b border-slate-200/50 bg-slate-50 sticky top-0 z-30">
          <div class="flex items-center gap-3">
            <h2 class="text-lg font-headline font-bold text-primary">{{ activeScreenTitle }}</h2>
            <span class="px-2 py-1 rounded-full text-xs font-semibold" :class="taskStateBadgeClass">{{ taskStatusText }}</span>
          </div>
          <div class="flex items-center gap-4">
            <div class="relative">
              <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-lg">search</span>
              <input class="pl-10 pr-4 py-2 bg-slate-100 rounded-full border-none focus:ring-2 focus:ring-primary/20 w-72 text-sm" placeholder="搜索任务、评论、关键词..." v-model.trim="globalFilter" />
            </div>
            <span class="text-xs text-on-surface-variant">任务ID：{{ taskId || "未生成" }}</span>
          </div>
        </header>

        <section class="p-12 max-w-7xl mx-auto space-y-10" v-if="activeScreen === 'campaign'">
          <div class="rounded-xl px-4 py-3 text-sm" :class="taskStateCardClass">
            <div class="font-semibold">{{ taskStateTitle }}</div>
            <div class="mt-1">{{ taskStateDesc }}</div>
            <div class="mt-2 flex gap-2" v-if="taskPhase === 'success'">
              <button class="px-3 py-1 rounded-lg bg-primary text-white" @click="setActiveScreen('review')">查看审核队列</button>
              <button class="px-3 py-1 rounded-lg bg-surface-container-highest" @click="setActiveScreen('analytics')">查看数据看板</button>
            </div>
            <div class="mt-2" v-if="taskPhase === 'error'">
              <button class="px-3 py-1 rounded-lg bg-red-100 text-red-700" @click="runTask" :disabled="isRunning || !adType">重试任务</button>
            </div>
          </div>

          <div class="flex justify-between items-end">
            <div>
              <h3 class="text-4xl font-headline font-extrabold text-primary tracking-tight">Campaign Configuration</h3>
              <p class="text-on-surface-variant mt-2">按 Stitch 的 Campaign Setup 结构配置抓取与投放策略。</p>
            </div>
            <div class="flex gap-3">
              <button class="px-6 py-2.5 rounded-xl bg-surface-container-highest text-on-surface font-semibold" @click="saveDraft">保存草稿</button>
              <button class="px-8 py-2.5 rounded-xl signature-gradient text-white font-bold flex items-center gap-2 disabled:opacity-60" @click="runTask" :disabled="isRunning || !adType">
                <span class="material-symbols-outlined text-sm">auto_awesome</span>
                {{ isRunning ? "分析中..." : "开始AI分析" }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-12 gap-8">
            <div class="col-span-7 space-y-8">
              <div class="bg-surface-container-lowest p-8 rounded-xl shadow-sm">
                <h4 class="font-headline text-xl font-bold text-primary mb-6">产品标识</h4>
                <div class="space-y-6">
                  <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">广告主题</label>
                    <input class="w-full bg-surface-container-low border-none rounded-xl px-4 py-4 focus:ring-2 focus:ring-secondary/20" v-model.trim="adType" placeholder="例如：高端护肤精华" />
                  </div>
                  <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">价值主张</label>
                    <textarea class="w-full bg-surface-container-low border-none rounded-xl px-4 py-4 focus:ring-2 focus:ring-secondary/20 resize-none" rows="4" v-model.trim="valueProposition" placeholder="写出广告策略亮点"></textarea>
                  </div>
                </div>
              </div>

              <div class="bg-surface-container-lowest p-8 rounded-xl shadow-sm">
                <h4 class="font-headline text-xl font-bold text-primary mb-6">受众定向</h4>
                <div class="grid grid-cols-2 gap-6">
                  <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">行业</label>
                    <select class="w-full bg-surface-container-low border-none rounded-xl px-4 py-4 focus:ring-2 focus:ring-secondary/20" v-model="industry">
                      <option>美妆护肤</option>
                      <option>本地生活</option>
                      <option>母婴亲子</option>
                      <option>运动健康</option>
                    </select>
                  </div>
                  <div>
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">语气风格</label>
                    <div class="flex p-1 bg-surface-container-low rounded-xl">
                      <button v-for="tone in tones" :key="tone" class="flex-1 py-3 text-sm rounded-lg" :class="campaignTone === tone ? 'bg-surface-container-lowest shadow-sm font-semibold' : 'text-on-surface-variant'" @click="campaignTone = tone">{{ tone }}</button>
                    </div>
                  </div>
                  <div class="col-span-2">
                    <label class="block text-xs font-bold uppercase tracking-widest text-on-surface-variant mb-2">关键词</label>
                    <input class="w-full bg-surface-container-low border-none rounded-xl px-4 py-4 focus:ring-2 focus:ring-secondary/20" v-model.trim="keywords" placeholder="多个关键词用逗号分隔" />
                  </div>
                </div>
              </div>
            </div>

            <div class="col-span-5 space-y-8">
              <div class="bg-primary text-white p-8 rounded-xl shadow-xl space-y-8">
                <h4 class="font-headline text-xl font-bold">抓取参数</h4>
                <div>
                  <div class="flex justify-between items-end mb-3">
                    <label class="text-xs font-bold uppercase tracking-widest opacity-70">帖子抓取量</label>
                    <span class="text-3xl font-headline font-extrabold text-secondary-container">{{ postLimit }}</span>
                  </div>
                  <input class="w-full" type="range" min="20" max="300" v-model.number="postLimit" />
                </div>
                <div>
                  <div class="flex justify-between items-end mb-3">
                    <label class="text-xs font-bold uppercase tracking-widest opacity-70">每帖评论深度</label>
                    <span class="text-3xl font-headline font-extrabold text-secondary-container">{{ commentsPerPostLimit }}</span>
                  </div>
                  <input class="w-full" type="range" min="5" max="80" v-model.number="commentsPerPostLimit" />
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <label class="bg-white/10 p-3 rounded-lg border border-white/20 flex items-center justify-between"><span class="text-sm">小红书</span><input type="checkbox" checked disabled /></label>
                  <label class="bg-white/10 p-3 rounded-lg border border-white/20 flex items-center justify-between"><span class="text-sm">下载媒体</span><input type="checkbox" v-model="enableMediaDownload" /></label>
                </div>
              </div>

              <div class="bg-surface-container-low p-8 rounded-xl">
                <h4 class="font-headline text-lg font-bold text-primary">智能上下文洞察</h4>
                <p class="text-sm text-on-surface-variant mt-2 italic">{{ aiHintText }}</p>
                <div class="mt-3 space-y-1 text-xs text-on-surface-variant">
                  <div>模型：{{ modelName }}</div>
                  <div>接口前缀：{{ apiPrefix }}</div>
                  <div v-if="baseUrl">服务地址：{{ baseUrl }}</div>
                </div>
                <div class="mt-5 grid grid-cols-2 gap-3 text-sm">
                  <div class="bg-surface-container-lowest rounded-xl p-4">
                    <div class="text-xs text-on-surface-variant">任务轮询</div>
                    <div class="text-xl font-bold text-primary mt-1">{{ pollCount }} 次</div>
                  </div>
                  <div class="bg-surface-container-lowest rounded-xl p-4">
                    <div class="text-xs text-on-surface-variant">耗时</div>
                    <div class="text-xl font-bold text-primary mt-1">{{ elapsedSeconds }} 秒</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="errorText" class="bg-red-50 text-red-700 border border-red-200 rounded-xl px-4 py-3 text-sm">
            <div>{{ errorText }}</div>
            <button class="mt-2 px-3 py-1 rounded-lg bg-red-100 text-red-700" @click="runTask" :disabled="isRunning || !adType">重试任务</button>
          </div>
        </section>

        <section class="p-12 max-w-7xl mx-auto space-y-6" v-if="activeScreen === 'review'">
          <div class="flex justify-between items-end">
            <div>
              <p class="text-secondary font-bold text-xs uppercase tracking-widest">待审批</p>
              <h3 class="font-headline text-3xl font-extrabold text-primary">审核队列</h3>
              <p class="text-on-surface-variant mt-2">对 AI 生成文案进行审核并派发。</p>
            </div>
            <div class="flex gap-3">
              <button class="px-5 py-2.5 bg-surface-container-highest rounded-xl text-sm font-semibold" @click="notifySoon('批量驳回功能待接入')">批量驳回</button>
              <button class="px-5 py-2.5 signature-gradient text-white rounded-xl text-sm font-semibold" @click="notifySoon(`已标记 ${filteredReviewQueue.length} 条为通过（演示）`)">全部通过 ({{ filteredReviewQueue.length }})</button>
            </div>
          </div>
          <div class="space-y-4">
            <div v-for="item in filteredReviewQueue" :key="item.comment_id" class="bg-surface-container-lowest rounded-xl p-6 flex flex-col md:flex-row gap-6">
              <div class="flex-1 space-y-3">
                <div class="text-xs text-on-surface-variant">{{ item.author }} · {{ item.platform }}</div>
                <div class="bg-surface-container-low p-4 rounded-xl text-sm italic">{{ item.source_text }}</div>
              </div>
              <div class="flex-[1.5] space-y-3">
                <div class="flex justify-between items-center">
                  <span class="px-3 py-1 bg-tertiary-container text-on-tertiary-container rounded-full text-[10px] font-bold uppercase">AI建议文案</span>
                  <span class="text-xs text-secondary font-bold">{{ item.predicted_affinity }}% 匹配度</span>
                </div>
                <div class="bg-primary/5 p-4 rounded-xl text-sm">{{ item.ad_text }}</div>
                <div class="text-xs text-on-surface-variant">投放方向：{{ item.focus }}</div>
              </div>
              <div class="flex items-center">
                <button class="w-12 h-12 rounded-full signature-gradient text-white flex items-center justify-center" @click="dispatchAd(item)">
                  <span class="material-symbols-outlined active-fill">send</span>
                </button>
              </div>
            </div>
            <div v-if="filteredReviewQueue.length === 0" class="bg-surface-container-lowest rounded-xl p-8 text-on-surface-variant">暂无可审核评论，请先运行任务配置。</div>
          </div>
        </section>

        <section class="p-12 max-w-7xl mx-auto space-y-8" v-if="activeScreen === 'progress'">
          <div class="flex justify-between items-end">
            <div>
              <p class="text-secondary font-bold text-xs uppercase tracking-widest">处理中</p>
              <h3 class="text-4xl font-headline font-extrabold text-primary">智能分析进行中</h3>
              <p class="text-on-surface-variant mt-2">实时显示抓取、整理、分析进度。</p>
            </div>
            <div class="flex gap-4">
              <div class="bg-surface-container-lowest p-4 rounded-xl w-44">
                <div class="text-xs text-on-surface-variant uppercase">已扫描帖子</div>
                <div class="text-2xl font-black text-primary mt-1">{{ progressMetrics.posts_scanned }}</div>
              </div>
              <div class="bg-surface-container-lowest p-4 rounded-xl w-44">
                <div class="text-xs text-on-surface-variant uppercase">已读取评论</div>
                <div class="text-2xl font-black text-secondary mt-1">{{ progressMetrics.comments_read }}</div>
              </div>
            </div>
          </div>

          <div class="bg-surface-container-low rounded-xl p-1">
            <div class="bg-surface-container-lowest rounded-xl p-10">
              <div class="text-center space-y-5">
                <div class="inline-flex items-center gap-2 px-3 py-1 bg-secondary-container/30 rounded-full text-xs font-bold uppercase">第 {{ progressStep.current }} 步 / 共 {{ progressStep.total }} 步：{{ progressStep.label }}</div>
                <div class="text-6xl font-black text-primary">{{ progressStep.percent }}<span class="text-2xl opacity-50">%</span></div>
                <div class="w-full max-w-3xl mx-auto">
                  <div class="h-2 bg-surface-container-highest rounded-full overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-primary to-secondary transition-all duration-500" :style="{ width: `${progressStep.percent}%` }"></div>
                  </div>
                </div>
              </div>
              <div class="mt-8 bg-surface-container-low rounded-xl p-5">
                <div class="text-xs font-bold text-primary uppercase mb-3">实时处理日志</div>
                <div class="space-y-2 text-xs text-on-surface-variant font-mono">
                  <div v-for="line in progressLogs" :key="line">{{ line }}</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="p-12 max-w-7xl mx-auto space-y-8" v-if="activeScreen === 'analytics'">
          <div>
            <span class="text-secondary font-bold text-xs uppercase tracking-widest bg-secondary-container/20 px-3 py-1 rounded-full">报告：实时分析</span>
            <h3 class="text-4xl font-headline font-extrabold text-primary mt-4">分析看板</h3>
            <p class="text-on-surface-variant mt-2">按 Stitch 风格重做的数据驾驶舱。</p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div class="bg-surface-container-lowest p-6 rounded-xl">
              <p class="text-on-surface-variant text-xs uppercase mb-2">总评论数</p>
              <h4 class="text-3xl font-headline font-extrabold text-primary">{{ analyticsKpis.comment_count }}</h4>
            </div>
            <div class="bg-surface-container-lowest p-6 rounded-xl">
              <p class="text-on-surface-variant text-xs uppercase mb-2">分析帖子数</p>
              <h4 class="text-3xl font-headline font-extrabold text-primary">{{ analyticsKpis.content_count }}</h4>
            </div>
            <div class="md:col-span-2 signature-gradient p-6 rounded-xl text-white">
              <p class="text-xs uppercase opacity-70 mb-2">广告植入效率</p>
              <h4 class="text-3xl font-headline font-extrabold">{{ analyticsKpis.dispatch_efficiency }}%</h4>
              <p class="text-sm mt-3 opacity-80">任务已完成 {{ analyticsKpis.completed_tasks }} 次，当前状态：{{ taskStatusText }}</p>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div class="lg:col-span-7 bg-surface-container-lowest p-8 rounded-xl">
              <div class="flex justify-between items-center mb-5">
                <h4 class="text-xl font-headline font-bold text-primary">话题频率</h4>
                <button class="bg-surface-container-low p-2 rounded-lg text-slate-500" @click="notifySoon('筛选功能待接入')"><span class="material-symbols-outlined">filter_list</span></button>
              </div>
              <div class="min-h-[280px] flex flex-wrap gap-x-6 gap-y-3 items-center justify-center">
                <span v-for="tag in analyticsTopics" :key="tag.word" :class="tag.className">{{ tag.word }}</span>
              </div>
            </div>
            <div class="lg:col-span-5 bg-surface-container-low p-8 rounded-xl">
              <h4 class="text-xl font-headline font-bold text-primary">情感指数</h4>
              <div class="space-y-5 mt-6">
                <div v-for="bar in sentimentBars" :key="bar.label" class="space-y-2">
                  <div class="flex justify-between text-xs font-bold text-on-surface-variant"><span>{{ bar.label }}</span><span>{{ bar.value }}%</span></div>
                  <div class="h-2 bg-surface-container-highest rounded-full overflow-hidden"><div class="h-full" :class="bar.colorClass" :style="{ width: `${bar.value}%` }"></div></div>
                </div>
              </div>
              <div class="mt-8 pt-6 border-t border-outline-variant/20 text-sm text-on-surface-variant italic">“{{ analyticsInsight }}”</div>
            </div>
          </div>
        </section>
      </main>

      <div v-if="toastText" class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2 rounded-lg shadow-lg z-50">
        {{ toastText }}
      </div>
</template>

<script>
import { AGENT6_CONFIG } from './config/agent6';
import {
  getTaskInsights,
  getTaskMeta,
  submitTask,
  toUserErrorMessage,
  waitTaskDone,
} from './services/adIntelApi';

export default {
  data() {
    return {
      stitchProjectId: "15597441123141010762",
      modelName: AGENT6_CONFIG.modelName,
      baseUrl: AGENT6_CONFIG.baseUrl,
      apiPrefix: AGENT6_CONFIG.apiPrefix,
      navItems: [
        { key: "campaign", label: "任务配置", icon: "rocket_launch" },
        { key: "progress", label: "AI分析", icon: "psychology" },
        { key: "analytics", label: "数据看板", icon: "leaderboard" },
        { key: "review", label: "审核队列", icon: "rate_review" },
      ],
      activeScreen: "campaign",
      globalFilter: "",
      adType: "",
      keywords: "",
      valueProposition: "",
      industry: "美妆护肤",
      campaignTone: "专业",
      tones: ["专业", "自然", "锋利"],
      postLimit: 120,
      commentsPerPostLimit: 20,
      enableMediaDownload: false,
      taskPhase: "idle",
      isRunning: false,
      taskStatusText: "未开始",
      errorText: "",
      taskId: "",
      pollCount: 0,
      elapsedSeconds: 0,
      startedAtMs: 0,
      summary: {},
      contentTable: [],
      commentTable: [],
      featureTable: [],
      reviewQueue: [],
      progressStep: { current: 1, total: 4, label: "初始化", percent: 0 },
      progressMetrics: { posts_scanned: 0, comments_read: 0 },
      progressLogs: [],
      analyticsKpis: { comment_count: 0, content_count: 0, dispatch_efficiency: 0, completed_tasks: 0 },
      analyticsTopics: [],
      sentimentBars: [],
      analyticsInsight: "等待任务数据生成洞察。",
      taskMeta: {},
      toastText: "",
      toastTimerId: null,
    };
  },
  mounted() {
    this.syncScreenFromPath();
    window.addEventListener("popstate", this.handlePopState);
  },
  beforeUnmount() {
    window.removeEventListener("popstate", this.handlePopState);
    if (this.toastTimerId) {
      clearTimeout(this.toastTimerId);
      this.toastTimerId = null;
    }
  },
  computed: {
    taskStateBadgeClass() {
      const mapping = {
        idle: "bg-surface-container-highest text-on-surface-variant",
        running: "bg-secondary-container/40 text-secondary",
        success: "bg-green-100 text-green-700",
        error: "bg-red-100 text-red-700",
      };
      return mapping[this.taskPhase] || mapping.idle;
    },
    taskStateCardClass() {
      const mapping = {
        idle: "bg-surface-container-low text-on-surface-variant border border-surface-container-high",
        running: "bg-secondary-container/20 text-secondary border border-secondary-container/60",
        success: "bg-green-50 text-green-700 border border-green-200",
        error: "bg-red-50 text-red-700 border border-red-200",
      };
      return mapping[this.taskPhase] || mapping.idle;
    },
    taskStateTitle() {
      const mapping = {
        idle: "等待启动",
        running: "任务执行中",
        success: "任务执行成功",
        error: "任务执行失败",
      };
      return mapping[this.taskPhase] || mapping.idle;
    },
    taskStateDesc() {
      const mapping = {
        idle: "请填写广告主题并点击“开始AI分析”。",
        running: `任务正在执行，已轮询 ${this.pollCount} 次，耗时 ${this.elapsedSeconds} 秒。`,
        success: "已拿到任务结果，可以前往审核队列或数据看板继续处理。",
        error: this.errorText || "任务失败，请检查参数后重试。",
      };
      return mapping[this.taskPhase] || mapping.idle;
    },
    activeScreenTitle() {
      const mapping = {
        campaign: "任务配置",
        review: "审核与派发",
        progress: "分析进度",
        analytics: "数据看板",
      };
      return mapping[this.activeScreen] || "任务配置";
    },
    aiHintText() {
      if (!this.adType) return "请先输入广告主题，系统会根据关键词密度自动评估抓取深度。";
      return `当前策略将围绕“${this.adType}”在${this.postLimit}条帖子和每帖${this.commentsPerPostLimit}条评论范围内构建语义投放线索。`;
    },
    filteredReviewQueue() {
      const query = this.globalFilter.trim().toLowerCase();
      if (!query) return this.reviewQueue;
      return this.reviewQueue.filter((item) => {
        const haystack = `${item.source_text} ${item.ad_text} ${item.author} ${item.focus}`.toLowerCase();
        return haystack.includes(query);
      });
    },
  },
  methods: {
    screenPathMap() {
      return {
        campaign: "/campaign_setup",
        progress: "/analysis_progress",
        analytics: "/analytics_dashboard",
        review: "/review_queue",
      };
    },
    pathToScreen(pathname) {
      const normalized = String(pathname || "").toLowerCase();
      const mapping = {
        "/campaign_setup": "campaign",
        "/analysis_progress": "progress",
        "/analytics_dashboard": "analytics",
        "/review_queue": "review",
      };
      return mapping[normalized] || "campaign";
    },
    syncScreenFromPath() {
      this.activeScreen = this.pathToScreen(window.location.pathname);
    },
    handlePopState() {
      this.syncScreenFromPath();
    },
    setActiveScreen(screen) {
      this.activeScreen = screen;
      const nextPath = this.screenPathMap()[screen] || "/campaign_setup";
      if (window.location.pathname !== nextPath) {
        window.history.pushState({}, "", nextPath);
      }
    },
    startNewCampaign() {
      this.setActiveScreen("campaign");
      this.setTaskPhase("idle");
      this.errorText = "";
      this.taskId = "";
      this.pollCount = 0;
      this.elapsedSeconds = 0;
      this.notifySoon("已切换到新建任务");
    },
    notifySoon(message) {
      this.toastText = message;
      if (this.toastTimerId) {
        clearTimeout(this.toastTimerId);
      }
      this.toastTimerId = setTimeout(() => {
        this.toastText = "";
        this.toastTimerId = null;
      }, 1600);
    },
    saveDraft() {
      this.notifySoon("草稿已保存（本地演示）");
    },
    dispatchAd(item) {
      const author = item?.author || "目标用户";
      this.notifySoon(`已派发给 ${author}（演示）`);
    },
    setTaskPhase(phase) {
      const statusTextMap = {
        idle: "未开始",
        running: "运行中",
        success: "成功",
        error: "失败",
      };
      this.taskPhase = phase;
      this.taskStatusText = statusTextMap[phase] || "未开始";
    },
    parseKeywords() {
      if (!this.keywords) return [this.adType];
      const parsed = this.keywords
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      return parsed.length > 0 ? parsed : [this.adType];
    },
    normalizePositiveInt(value, fallback) {
      const parsed = Number.parseInt(String(value), 10);
      if (Number.isNaN(parsed) || parsed <= 0) return fallback;
      return parsed;
    },
    updateElapsed() {
      if (!this.startedAtMs) return;
      this.elapsedSeconds = Math.max(0, Math.round((Date.now() - this.startedAtMs) / 1000));
    },
    async loadInsights() {
      if (!this.taskId) return;
      try {
        const insights = await getTaskInsights(this.taskId);
        this.reviewQueue = insights.review_queue || [];
        this.progressStep = insights.progress?.step || this.progressStep;
        this.progressMetrics = insights.progress?.metrics || this.progressMetrics;
        this.progressLogs = insights.progress?.logs || [];
        this.analyticsKpis = insights.analytics?.kpis || this.analyticsKpis;
        this.sentimentBars = insights.analytics?.sentiment_bars || [];
        this.analyticsTopics = insights.analytics?.topic_cloud || [];
        this.analyticsInsight = insights.analytics?.insight || this.analyticsInsight;
      } catch (error) {
        this.errorText = toUserErrorMessage(error);
      }
    },
    async runTask() {
      if (!this.adType) return;
      this.errorText = "";
      this.setTaskPhase("running");
      this.isRunning = true;
      this.taskId = "";
      this.pollCount = 0;
      this.elapsedSeconds = 0;
      this.summary = {};
      this.contentTable = [];
      this.commentTable = [];
      this.featureTable = [];
      this.reviewQueue = [];
      this.progressLogs = [];
      this.progressStep = { current: 1, total: 4, label: "初始化", percent: 8 };
      this.progressMetrics = { posts_scanned: 0, comments_read: 0 };
      this.startedAtMs = Date.now();
      this.setActiveScreen("progress");
      const timer = setInterval(() => this.updateElapsed(), 1000);
      try {
        const payload = {
          ad_type: this.adType,
          keywords: this.parseKeywords(),
          platform: "xhs",
          limit: this.normalizePositiveInt(this.postLimit, 120),
          max_comments_per_note: this.normalizePositiveInt(this.commentsPerPostLimit, 20),
          enable_media_download: this.enableMediaDownload,
          time_range: "",
        };
        const runData = await submitTask(payload);
        this.taskId = runData.task_id || "";
        const task = await waitTaskDone(this.taskId, (count, status) => {
          this.pollCount = count;
          if (status === "running") {
            this.setTaskPhase("running");
            this.progressStep = {
              current: 3,
              total: 4,
              label: "内容合成中",
              percent: Math.min(90, 20 + count * 3),
            };
          }
        });
        const meta = await getTaskMeta(this.taskId);
        this.taskMeta = meta;
        if (task.status && task.status !== "success") {
          this.setTaskPhase("error");
          this.errorText = task.message || "任务失败";
          return;
        }
        this.setTaskPhase("success");
        this.progressStep = { current: 4, total: 4, label: "完成", percent: 100 };
        this.summary = task.summary || {};
        this.contentTable = task.content_table || [];
        this.commentTable = task.comment_table || [];
        this.featureTable = task.feature_table || [];
        await this.loadInsights();
        this.setActiveScreen("review");
      } catch (error) {
        this.setTaskPhase("error");
        this.errorText = toUserErrorMessage(error);
        this.setActiveScreen("progress");
      } finally {
        clearInterval(timer);
        this.updateElapsed();
        this.isRunning = false;
      }
    },
  },
}
</script>
