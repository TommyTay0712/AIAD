from __future__ import annotations

import logging
import re
from pathlib import Path


class SensitiveDataFilter(logging.Filter):
    """SEC-11: 日志脱敏过滤器，自动屏蔽 API Key、Token 等敏感信息。"""

    _PATTERNS = [
        # ModelScope API Key 格式
        (re.compile(r"ms-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", re.I), "ms-****"),
        # 通用 Bearer Token
        (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I), "Bearer ****"),
        # 通用 API Key 模式（sk-xxx, api-xxx 等）
        (re.compile(r"(?:sk|api|key|token)-[A-Za-z0-9]{16,}", re.I), "****-REDACTED"),
        # Cookie 值
        (re.compile(r"cookie[s]?\s*[:=]\s*[^\s;]{20,}", re.I), "cookie=****"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self._PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args and isinstance(record.args, tuple):
            sanitized = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in self._PATTERNS:
                        arg = pattern.sub(replacement, arg)
                sanitized.append(arg)
            record.args = tuple(sanitized)
        return True


def configure_logging(logs_dir: Path, level: str = "INFO") -> None:
    """初始化日志配置。"""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )
    # SEC-11: 为所有 handler 添加脱敏过滤器
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)

