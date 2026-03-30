const runBtn = document.getElementById("runBtn");
const taskStatus = document.getElementById("taskStatus");
const errorText = document.getElementById("errorText");

function setResult(id, value) {
  document.getElementById(id).textContent = JSON.stringify(value, null, 2);
}

function parseKeywords(raw) {
  if (!raw) return [];
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

async function fetchTask(taskId) {
  const response = await fetch(`/api/ad-intel/task/${taskId}`);
  return response.json();
}

runBtn.addEventListener("click", async () => {
  const payload = {
    ad_type: document.getElementById("adType").value.trim(),
    keywords: parseKeywords(document.getElementById("keywords").value),
    platform: document.getElementById("platform").value,
    limit: Number(document.getElementById("limit").value || 20),
    time_range: document.getElementById("timeRange").value.trim(),
  };
  errorText.textContent = "";
  taskStatus.textContent = "任务状态：运行中";
  try {
    const runResp = await fetch("/api/ad-intel/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const runData = await runResp.json();
    if (!runResp.ok) {
      taskStatus.textContent = "任务状态：失败";
      errorText.textContent = `错误：${JSON.stringify(runData)}`;
      return;
    }
    const task = await fetchTask(runData.task_id);
    if (task.status && task.status !== "success") {
      taskStatus.textContent = `任务状态：${task.status}`;
      errorText.textContent = `错误：${task.message || ""}`;
      return;
    }
    taskStatus.textContent = "任务状态：成功";
    setResult("summary", task.summary || {});
    setResult("contentTable", task.content_table || []);
    setResult("commentTable", task.comment_table || []);
    setResult("featureTable", task.feature_table || []);
  } catch (error) {
    taskStatus.textContent = "任务状态：失败";
    errorText.textContent = `错误：${error}`;
  }
});
