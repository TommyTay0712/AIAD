"""Agent 4 (RAG & Memory) 一键环境 bootstrap（跨平台 Python 版）。

对标 scripts/bootstrap_agent4.ps1。步骤：
    1. 检查 Python 版本 (>= 3.10)
    2. 配置 HuggingFace 镜像与本地模型缓存目录
    3. 安装 requirements.txt 中的依赖
    4. 首次创建 .env（若已存在则保留）
    5. 下载 BGE 模型 + 灌入 assets/seeds 到本地 Chroma
    6. 冒烟校验

用法示例：
    python scripts/bootstrap_agent4.py                首次或日常同步
    python scripts/bootstrap_agent4.py --force        强制重建 Chroma collection
    python scripts/bootstrap_agent4.py --skip-install 只重灌种子
    python scripts/bootstrap_agent4.py --no-mirror    海外网络不使用国内镜像

任何一步失败会立刻退出并返回非 0 状态码。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HF_MIRROR = "https://hf-mirror.com"
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
MIN_PY = (3, 10)

# ANSI 颜色码（Windows 10+ / *nix 都支持）
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_GRAY = "\033[90m"


def banner(msg: str) -> None:
    print(f"\n{C_MAGENTA}{'=' * 50}\n  {msg}\n{'=' * 50}{C_RESET}")


def step(idx: int, total: int, msg: str) -> None:
    print(f"\n{C_CYAN}[{idx}/{total}] {msg}{C_RESET}")


def ok(msg: str) -> None:
    print(f"      {C_GREEN}\u2713 {msg}{C_RESET}")


def info(msg: str) -> None:
    print(f"      {C_GRAY}\u00b7 {msg}{C_RESET}")


def warn(msg: str) -> None:
    print(f"      {C_YELLOW}! {msg}{C_RESET}")


def fail(msg: str, code: int = 1) -> "None":
    print(f"      {C_RED}\u2717 {msg}{C_RESET}")
    sys.exit(code)


def run(cmd: list[str], **kwargs) -> None:
    info("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=kwargs.pop("cwd", ROOT), **kwargs)
    if result.returncode != 0:
        fail(f"命令失败（退出码 {result.returncode}）: {' '.join(cmd)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent 4 (RAG & Memory) 一键环境 bootstrap",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="重建 Chroma collection（换模型或种子大改时使用）",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="跳过 pip install（只想重灌种子时使用）",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="不使用 pypi 和 HuggingFace 国内镜像（海外网络）",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="指定 Python 可执行文件（默认使用当前解释器）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python = args.python or sys.executable

    banner("Agent 4 (RAG & Memory) Bootstrap")
    info(f"ProjectRoot = {ROOT}")
    info(f"Python      = {python}")

    total = 6

    # --- Step 1: Python 版本 ---
    step(1, total, "检查 Python 版本 (要求 >= 3.10)...")
    try:
        ver_out = subprocess.check_output(
            [python, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"],
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        fail(f"找不到 Python 可执行文件: {python} ({exc})", code=2)
    major, minor, *_ = [int(x) for x in ver_out.split(".")]
    if (major, minor) < MIN_PY:
        fail(f"Python 版本过低: {ver_out} (需要 >= {MIN_PY[0]}.{MIN_PY[1]})", code=2)
    ok(f"Python {ver_out}")

    # --- Step 2: HF 镜像 + 模型缓存 ---
    step(2, total, "配置 HuggingFace 镜像与模型缓存...")
    model_cache = ROOT / ".model_cache"
    model_cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(model_cache)
    if args.no_mirror:
        info("已跳过国内镜像 (--no-mirror)")
        pip_index: list[str] = []
    else:
        os.environ["HF_ENDPOINT"] = HF_MIRROR
        info(f"HF_ENDPOINT = {HF_MIRROR}")
        pip_index = ["-i", PYPI_MIRROR]
    ok(f"HF_HOME     = {model_cache}")

    # --- Step 3: 安装依赖 ---
    step(3, total, "安装 Python 依赖...")
    if args.skip_install:
        info("已跳过 (--skip-install)")
    else:
        run([python, "-m", "pip", "install", "--upgrade", "pip"] + pip_index)
        run([python, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")] + pip_index)
        ok("依赖安装完成")

    # --- Step 4: 准备 .env ---
    step(4, total, "准备 .env 文件...")
    env_path = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if env_path.exists():
        ok(".env 已存在，保留不覆盖")
        info("如果需要新增 AGENT4_* 配置，请手动对比 .env.example")
    else:
        if not env_example.exists():
            fail(".env.example 不存在，无法自动生成 .env")
        shutil.copy(env_example, env_path)
        ok("已从 .env.example 生成 .env")
        warn("请编辑 .env，把 MEDIACRAWLER_PYTHON_EXE 改成你自己的路径")

    # --- Step 5: 下载模型 + 灌种子 ---
    step(5, total, "下载 BGE 模型 + 灌入 assets/seeds 到 Chroma...")
    info("首次执行会从 HuggingFace 下载 BAAI/bge-small-zh-v1.5 (~95MB)")
    init_cmd = [python, "-m", "app.services.memory.cli", "init"]
    if args.force:
        init_cmd.append("--force")
    run(init_cmd)
    ok("种子灌库完成")

    # --- Step 6: 冒烟 ---
    step(6, total, "冒烟校验...")
    run([python, "-m", "app.services.memory.cli", "status"])
    fixture = ROOT / "tests" / "memory" / "fixtures" / "mock_global_state_beach.json"
    if fixture.exists():
        info("运行 probe 冒烟 (海边场景)...")
        result = subprocess.run(
            [python, "-m", "app.services.memory.cli", "probe", str(fixture)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            ok("probe OK")
        else:
            warn("probe 返回非 0 状态，但不致命")
            if result.stderr:
                info(result.stderr.strip()[:400])

    print()
    banner("\u2705 Agent 4 环境就绪")
    print("下一步你可以：")
    print(f"  \u00b7 跑单元测试     : pytest tests/memory -v")
    print(f"  \u00b7 查看 collection : {python} -m app.services.memory.cli status")
    print(
        f"  \u00b7 端到端冒烟     : {python} -m app.services.memory.cli probe "
        f"tests/memory/fixtures/mock_global_state_beach.json"
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
