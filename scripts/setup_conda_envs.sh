#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AIAD_PREFIX="$ROOT_DIR/.conda/aiad"
MEDIACRAWLER_PREFIX="$ROOT_DIR/.conda/mediacrawler"
AIAD_PYTHON="$AIAD_PREFIX/bin/python"
MEDIACRAWLER_PYTHON="$MEDIACRAWLER_PREFIX/bin/python"
PLAYWRIGHT_DIR="$ROOT_DIR/.ms-playwright"

CONDA_BIN="${CONDA_EXE:-}"
if [ -z "$CONDA_BIN" ] && command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
fi
if [ -z "$CONDA_BIN" ] && [ -x "/opt/homebrew/Caskroom/miniforge/base/bin/conda" ]; then
  CONDA_BIN="/opt/homebrew/Caskroom/miniforge/base/bin/conda"
fi

if [ -z "$CONDA_BIN" ]; then
  cat <<'EOF'
conda 未安装或不在 PATH 中。
建议先执行以下任一方案：
  1. brew install --cask miniforge
  2. 安装现有 Conda 发行版后，确保 `conda` 可在终端直接调用
EOF
  exit 1
fi

create_prefix_env() {
  local prefix="$1"
  local python_version="$2"
  local python_bin="$3"
  if [ -x "$python_bin" ]; then
    echo "环境已存在，跳过创建: $prefix"
    return 0
  fi
  "$CONDA_BIN" create --prefix "$prefix" "python=${python_version}" -y
}

echo ">>> 创建 AIAD 主工程环境"
create_prefix_env "$AIAD_PREFIX" "3.10" "$AIAD_PYTHON"

echo ">>> 创建 MediaCrawler 环境"
create_prefix_env "$MEDIACRAWLER_PREFIX" "3.11" "$MEDIACRAWLER_PYTHON"

echo ">>> 安装 AIAD 依赖"
"$AIAD_PYTHON" -m pip install --upgrade pip
"$AIAD_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"

echo ">>> 安装 MediaCrawler 依赖"
"$MEDIACRAWLER_PYTHON" -m pip install --upgrade pip setuptools wheel
"$MEDIACRAWLER_PYTHON" -m pip install -r "$ROOT_DIR/vendor/MediaCrawler/requirements.txt"

mkdir -p "$PLAYWRIGHT_DIR"
echo ">>> 安装 Playwright Chromium 浏览器"
if ! PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_DIR" \
  "$MEDIACRAWLER_PYTHON" -m playwright install chromium; then
  cat <<EOF
Playwright 浏览器下载失败，请重试以下命令：
  PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_DIR" "$MEDIACRAWLER_PYTHON" -m playwright install chromium
如果网络受限，可考虑代理后重试。
EOF
  exit 1
fi

cat <<EOF
环境初始化完成。

AIAD Python:
  $AIAD_PYTHON

MediaCrawler Python:
  $MEDIACRAWLER_PYTHON

建议复制 .env.example 为 .env，并确认以下配置：
  MEDIACRAWLER_PYTHON_EXE=.conda/mediacrawler/bin/python
  PLAYWRIGHT_BROWSERS_PATH=.ms-playwright
EOF
