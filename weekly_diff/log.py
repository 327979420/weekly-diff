"""Logging with environment-secret and Discord webhook redaction."""
import logging
import os
import re

SECRET_NAMES = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DISCORD_WEBHOOK_URL",
    "DISCORD_PREVIEW_WEBHOOK_URL", "GITHUB_TOKEN",
)
WEBHOOK = re.compile(r"https://discord(?:app)?\.com/api/webhooks/[^\s<>\"']+", re.IGNORECASE)


def redact(text: str) -> str:
    text = WEBHOOK.sub("https://discord.com/api/webhooks/***", text)
    secrets = sorted({os.environ.get(name, "") for name in SECRET_NAMES}, key=len, reverse=True)
    for value in secrets:
        if len(value) >= 8:
            text = text.replace(value, "***")
    return text


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def setup_logging(verbose: bool) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactionFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=[handler], force=True)
