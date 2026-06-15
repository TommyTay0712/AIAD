FROM aiad-base:latest

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/*

COPY app/ app/
COPY services/ services/
COPY vendor/MediaCrawler/requirements.txt /tmp/mediacrawler-requirements.txt
RUN pip install --no-cache-dir -r /tmp/mediacrawler-requirements.txt && \
    pip install --no-cache-dir --force-reinstall opencv-python-headless

# Playwright 官方脚本在 Debian Trixie 上找不到 ttf-unifont/ttf-ubuntu-font-family
# 手动安装 Trixie 的正确包名，再装浏览器本体（不带 --with-deps）
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-unifont fonts-liberation \
        libnss3 libnspr4 \
        libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libgbm1 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libpango-1.0-0 libcairo2 libasound2t64 \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install chromium

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "services.crawler.main:app", "--host", "0.0.0.0", "--port", "8002"]
