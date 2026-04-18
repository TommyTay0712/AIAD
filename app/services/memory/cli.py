"""Agent 4 命令行入口。用法：

    python -m app.services.memory.cli init            # 灌种子数据（upsert）
    python -m app.services.memory.cli init --force    # 删除并重建 collection
    python -m app.services.memory.cli status          # 查看各 collection 当前条数
    python -m app.services.memory.cli probe <state>   # 用 mock global_state 做检索冒烟
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.services.memory.config import get_agent4_settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _cmd_init(args: argparse.Namespace) -> int:
    from app.services.memory.seed_loader import load_seeds_into_memory

    settings = get_agent4_settings()
    print(f"[init] persist_dir={settings.persist_dir}")
    print(f"[init] seed_dir   ={settings.seed_dir}")
    print(f"[init] embedding  ={settings.embedding_provider} / {settings.embedding_model}")
    print(f"[init] force      ={args.force}")
    counts = load_seeds_into_memory(settings, force=args.force)
    print("[init] counts     =", json.dumps(counts, ensure_ascii=False))
    return 0


def _cmd_status(_: argparse.Namespace) -> int:
    from app.services.memory.embedder import build_embedder
    from app.services.memory.memory_store import MemoryStore

    settings = get_agent4_settings()
    embedder = build_embedder(settings)
    store = MemoryStore(settings, embedder)
    store.ensure_collections()
    report = {
        "persist_dir": str(settings.persist_dir),
        "seed_dir": str(settings.seed_dir),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "collections": {
            settings.collection_ad_examples: store.count(
                settings.collection_ad_examples
            ),
            settings.collection_product_knowledge: store.count(
                settings.collection_product_knowledge
            ),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from app.services.memory.rag_agent import run_rag_agent

    path = Path(args.state_file)
    if not path.exists():
        print(f"[probe] 找不到文件: {path}", file=sys.stderr)
        return 2
    global_state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    state = {"global_state": global_state}
    result = run_rag_agent(state)
    new_gs = result.get("global_state", {})
    output = {
        "retrieval_summary": new_gs.get("retrieval_summary"),
        "rag_references": new_gs.get("rag_references"),
        "rag_references_full": new_gs.get("rag_references_full"),
        "rag_product_knowledge": new_gs.get("rag_product_knowledge"),
        "rag_forbidden_phrases": new_gs.get("rag_forbidden_phrases"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent4-memory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="灌入 assets/seeds/ 下的种子数据")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="先删除同名 collection 再重建（用于模型换代或种子重排）",
    )
    p_init.set_defaults(func=_cmd_init)

    p_status = sub.add_parser("status", help="查看 Chroma collection 状态")
    p_status.set_defaults(func=_cmd_status)

    p_probe = sub.add_parser("probe", help="用 mock global_state 做检索冒烟")
    p_probe.add_argument(
        "state_file",
        help="包含 global_state 顶层 JSON 的文件路径",
    )
    p_probe.set_defaults(func=_cmd_probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
