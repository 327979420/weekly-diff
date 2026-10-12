import io
import logging
import pytest
from weekly_diff.log import RedactionFilter, SECRET_NAMES, redact, setup_logging


@pytest.mark.parametrize("name", SECRET_NAMES)
def test_env_redaction(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, "fake-secret-1234")
    assert redact("prefix fake-secret-1234 suffix") == "prefix *** suffix"
    monkeypatch.setenv(name, "short")
    assert redact("short") == "short"


@pytest.mark.parametrize("domain", ["discord.com", "discordapp.com"])
def test_webhook_redaction(domain: str) -> None:
    assert redact(f"url https://{domain}/api/webhooks/fake/token") == "url https://discord.com/api/webhooks/***"


def test_message_args_and_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fake-secret-1234")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(RedactionFilter())
    logger = logging.Logger("redaction-test")
    logger.addHandler(handler)
    try:
        raise ValueError("fake-secret-1234 https://discordapp.com/api/webhooks/fake/token")
    except ValueError:
        logger.exception("fake-secret-1234 %s", {"token": "fake-secret-1234"})
    text = output.getvalue()
    assert "fake-secret-1234" not in text
    assert "/fake/token" not in text
    assert "Traceback" in text
    assert "ValueError: ***" in text


def test_setup_is_idempotent() -> None:
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    try:
        setup_logging(False)
        assert root.level == logging.INFO
        setup_logging(True)
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].filters[0], RedactionFilter)
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = old_handlers
        root.setLevel(old_level)
