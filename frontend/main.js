async function requestJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data === "object" ? JSON.stringify(data) : String(data));
  }
  return data;
}

async function waitTaskDone(taskId, onPoll, maxAttempts = 180, sleepMs = 3000) {
  for (let i = 0; i < maxAttempts; i += 1) {
    const task = await requestJson(`/api/ad-intel/task/${taskId}`);
    if (onPoll) onPoll(i + 1, task.status || "success");
    if (!task.status || task.status === "success" || task.status === "failed") return task;
    await new Promise((resolve) => setTimeout(resolve, sleepMs));
  }
  throw new Error("任务等待超时，请稍后再试");
}

const { createApp } = Vue;

createApp({
  data() {
    return {
      stitchProjectId: "15597441123141010762",
      navItems: [
        { key: "campaign", label: "Campaigns", icon: "rocket_launch" },
        { key: "progress", label: "AI Analysis", icon: "psychology" },
        { key: "analytics", label: "Analytics", icon: "leaderboard" },
        { key: "review", label: "Review Queue", icon: "rate_review" },
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
      progressStep: { current: 1, total: 4, label: "Initialization", percent: 0 },
      progressMetrics: { posts_scanned: 0, comments_read: 0 },
      progressLogs: [],
      analyticsKpis: { comment_count: 0, content_count: 0, dispatch_efficiency: 0, completed_tasks: 0 },
      analyticsTopics: [],
      sentimentBars: [],
      analyticsInsight: "等待任务数据生成洞察。",
      taskMeta: {},
    };
  },
  computed: {
    activeScreenTitle() {
      const mapping = {
        campaign: "Campaign Setup",
        review: "Ad Review & Dispatch",
        progress: "Analysis Progress",
        analytics: "Analytics Dashboard",
      };
      return mapping[this.activeScreen] || "Campaign Setup";
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
        const insights = await requestJson(`/api/ad-intel/task/${this.taskId}/insights`);
        this.reviewQueue = insights.review_queue || [];
        this.progressStep = insights.progress?.step || this.progressStep;
        this.progressMetrics = insights.progress?.metrics || this.progressMetrics;
        this.progressLogs = insights.progress?.logs || [];
        this.analyticsKpis = insights.analytics?.kpis || this.analyticsKpis;
        this.sentimentBars = insights.analytics?.sentiment_bars || [];
        this.analyticsTopics = insights.analytics?.topic_cloud || [];
        this.analyticsInsight = insights.analytics?.insight || this.analyticsInsight;
      } catch (error) {
        this.errorText = String(error);
      }
    },
    async runTask() {
      if (!this.adType) return;
      this.errorText = "";
      this.taskStatusText = "运行中";
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
      this.startedAtMs = Date.now();
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
        const runData = await requestJson("/api/ad-intel/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        this.taskId = runData.task_id || "";
        const task = await waitTaskDone(this.taskId, (count, status) => {
          this.pollCount = count;
          if (status === "running") this.taskStatusText = "运行中";
        });
        const meta = await requestJson(`/api/ad-intel/task/${this.taskId}/meta`);
        this.taskMeta = meta;
        if (task.status && task.status !== "success") {
          this.taskStatusText = "失败";
          this.errorText = task.message || "任务失败";
          return;
        }
        this.taskStatusText = "成功";
        this.summary = task.summary || {};
        this.contentTable = task.content_table || [];
        this.commentTable = task.comment_table || [];
        this.featureTable = task.feature_table || [];
        await this.loadInsights();
        this.activeScreen = "review";
      } catch (error) {
        this.taskStatusText = "失败";
        this.errorText = String(error);
        this.activeScreen = "progress";
      } finally {
        clearInterval(timer);
        this.updateElapsed();
        this.isRunning = false;
      }
    },
  },
}).mount("#app");
