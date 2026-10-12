import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent


def cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "run.py"), *args], cwd=ROOT,
                          env=env, text=True, capture_output=True, timeout=10)


def test_status_github_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.write_text("existing=value\n")
    result = cli("status", "--issue", "2026-41", "--github-output", env={**os.environ, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == {"name=The Weekly Diff", "issue_id=2026-41", "paused=false", "publish_enabled=false"}
    assert output.read_text() == "existing=value\npaused=false\npublish_enabled=false\nissue_id=2026-41\n"


def test_help_and_default_status() -> None:
    result = cli("--help")
    assert result.returncode == 0
    for command in ("collect", "build", "render", "publish", "status"):
        assert command in result.stdout
    assert cli("status").returncode == 0


@pytest.mark.parametrize(("command", "task"), [("collect", "002"), ("build", "004"), ("render", "005"), ("publish", "006")])
def test_stubs(command: str, task: str) -> None:
    result = cli("--dry-run", command)
    assert result.returncode == 1
    assert f"task {task}" in result.stderr
    assert "Traceback" not in result.stderr


def test_verbose_and_preview() -> None:
    result = cli("publish", "--preview", "-v", "--dry-run")
    assert result.returncode == 1
    assert "Traceback" in result.stderr


@pytest.mark.parametrize("args", [("--config", "absent", "status"), ("status", "--issue", "2027-53"), ("missing",), ()])
def test_config_and_usage_errors(args: tuple[str, ...]) -> None:
    assert cli(*args).returncode == 2


def test_missing_github_output() -> None:
    env = {key: value for key, value in os.environ.items() if key != "GITHUB_OUTPUT"}
    result = cli("status", "--github-output", env=env)
    assert result.returncode == 1
    assert "GITHUB_OUTPUT is not set" in result.stderr


def test_config_option_after_command() -> None:
    result = cli("status", "--config", "tests/fixtures/config.yaml")
    assert result.returncode == 0
    assert "name=Test Roundup" in result.stdout
