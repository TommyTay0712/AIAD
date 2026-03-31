async function fetchTask(taskId) {
  const response = await fetch(`/api/ad-intel/task/${taskId}`);
  return response.json();
}

async function fetchTaskMeta(taskId) {
  const response = await fetch(`/api/ad-intel/task/${taskId}/meta`);
  return response.json();
}

async function waitTaskDone(taskId, onPoll, maxAttempts = 180, sleepMs = 3000) {
  for (let i = 0; i < maxAttempts; i += 1) {
    const task = await fetchTask(taskId);
    if (onPoll) onPoll(i + 1, task.status || "success");
    if (!task.status || task.status === "success" || task.status === "failed") {
      return task;
    }
    await new Promise((resolve) => setTimeout(resolve, sleepMs));
  }
  throw new Error("任务等待超时，请稍后再试");
}

const { createApp } = Vue;

createApp({
  data() {
    return {
      adType: "",
      keywords: "",
      postLimit: 20,
      commentsPerPostLimit: 12,
      enableMediaDownload: false,
      isRunning: false,
      taskStatusText: "未开始",
      errorText: "",
      taskId: "",
      pollCount: 0,
      elapsedSeconds: 0,
      processedFile: "",
      chromaCounts: {},
      taskMeta: {},
      summary: {},
      contentTable: [],
      commentTable: [],
      featureTable: [],
      startedAtMs: 0,
    };
  },
  computed: {
    statusClass() {
      if (this.taskStatusText === "成功") return "badge-success";
      if (this.taskStatusText === "失败") return "badge-failed";
      return "badge-running";
    },
    noteCards() {
      const perPostLimit = Number(this.commentsPerPostLimit) > 0 ? Number(this.commentsPerPostLimit) : 12;
      const contentMap = new Map(this.contentTable.map((item) => [item.note_id, item]));
      const featureMap = new Map(this.featureTable.map((item) => [item.note_id, item]));
      const grouped = new Map();
      for (const comment of this.commentTable) {
        if (!grouped.has(comment.note_id)) grouped.set(comment.note_id, []);
        grouped.get(comment.note_id).push(comment);
      }
      return Array.from(grouped.entries())
        .map(([noteId, comments]) => {
          const content = contentMap.get(noteId) || {};
          const feature = featureMap.get(noteId) || {};
          return {
            noteId,
            title: content.title || "未获取到标题",
            desc: content.desc || "",
            authorName: content.author_name || "未知作者",
            noteUrl: content.note_url || "",
            topicCluster: feature.topic_cluster || "general",
            adFitScore: feature.ad_fit_score ?? "",
            comments: comments.slice(0, perPostLimit),
            totalComments: comments.length,
          };
        })
        .sort((a, b) => b.totalComments - a.totalComments);
    },
  },
  methods: {
    pretty(value) {
      return JSON.stringify(value, null, 2);
    },
    commentAnalysisPlaceholder(comment) {
      const text = String(comment.comment_text || "");
      if (!text) return "待补充分析";
      if (text.includes("贵") || text.includes("价格")) return "价格敏感倾向，建议补充价格锚点";
      if (text.includes("好吃") || text.includes("喜欢")) return "正向反馈，适合作为卖点素材";
      if (text.includes("一般") || text.includes("不好")) return "存在负向信号，建议排查具体痛点";
      return "待补充分析";
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
    async runTask() {
      if (!this.adType) return;
      this.errorText = "";
      this.taskStatusText = "运行中";
      this.isRunning = true;
      this.taskId = "";
      this.pollCount = 0;
      this.elapsedSeconds = 0;
      this.processedFile = "";
      this.chromaCounts = {};
      this.taskMeta = {};
      this.summary = {};
      this.contentTable = [];
      this.commentTable = [];
      this.featureTable = [];
      this.startedAtMs = Date.now();
      const timer = setInterval(() => this.updateElapsed(), 1000);
      try {
        const payload = {
          ad_type: this.adType,
          keywords: this.parseKeywords(),
          platform: "xhs",
          limit: this.normalizePositiveInt(this.postLimit, 20),
          max_comments_per_note: this.normalizePositiveInt(this.commentsPerPostLimit, 10),
          enable_media_download: this.enableMediaDownload,
          time_range: "",
        };
        const runResp = await fetch("/api/ad-intel/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const runData = await runResp.json();
        if (!runResp.ok) {
          this.taskStatusText = "失败";
          this.errorText = JSON.stringify(runData);
          return;
        }
        this.taskId = runData.task_id || "";
        const task = await waitTaskDone(
          this.taskId,
          (count, status) => {
            this.pollCount = count;
            if (status === "running") this.taskStatusText = "运行中";
          },
        );
        const meta = await fetchTaskMeta(this.taskId);
        this.taskMeta = meta;
        this.processedFile = meta.processed_file || "";
        this.chromaCounts = meta.chroma_counts || {};
        if (task.status && task.status !== "success") {
          this.taskStatusText = "失败";
          this.errorText = task.message || "";
          return;
        }
        this.taskStatusText = "成功";
        this.summary = task.summary || {};
        this.contentTable = task.content_table || [];
        this.commentTable = task.comment_table || [];
        this.featureTable = task.feature_table || [];
      } catch (error) {
        this.taskStatusText = "失败";
        this.errorText = String(error);
      } finally {
        clearInterval(timer);
        this.updateElapsed();
        this.isRunning = false;
      }
    },
  },
}).mount("#app");
