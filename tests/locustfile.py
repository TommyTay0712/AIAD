import re
from locust import HttpUser, task, between

class AIADFrontendUser(HttpUser):
    # 模拟真实用户的思考停留时间 (1秒到3秒)
    wait_time = between(1, 3)

    @task(3)
    def load_homepage(self):
        """场景 A：模拟用户加载首页与静态资源"""
        # 1. 访问首页
        response = self.client.get("/")
        
        # 2. 模拟浏览器解析 HTML，提取引用的 js 和 css
        if response.status_code == 200:
            html = response.text
            # Vite 打包后的资源路径通常形如 /assets/index-xxxxx.js
            assets = re.findall(r'href="(/assets/.*?\.css)"|src="(/assets/.*?\.js)"', html)
            for css, js in assets:
                asset_url = css if css else js
                if asset_url:
                    # 并发请求资源（在真实浏览器中是并发的，这里我们串行请求，足以测试网关压力）
                    self.client.get(asset_url, name="/assets/[hash].[ext]")

    @task(1)
    def submit_ad_intel_task(self):
        """场景 B：模拟高并发提交 API 任务"""
        payload = {
            "platform": "xhs",
            "url": "https://www.xiaohongshu.com/explore/test",
            "mock_mode": True
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": "test-key-for-stress", # 假设这是一个测试 key 或者故意触发 401/429
            "User-Agent": "Locust-Stress-Test"
        }
        # 预期会受到网关的速率限制或鉴权拦截，这也是防御压测的一部分
        with self.client.post("/api/ad-intel/run", json=payload, headers=headers, catch_response=True) as response:
            if response.status_code in [200, 202, 401, 429]:
                # 429 和 401 对于压测而言属于预期的安全拦截，视为成功抵挡
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")
