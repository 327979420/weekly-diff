"""Repository paths; importing this module never creates directories."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ISSUES = DATA / "issues"
SEEN = DATA / "seen.json"
STARS = DATA / "stars.json"
BUILD = ROOT / "build"
DRY_RUN = BUILD / "dry-run"
SITE = ROOT / "site"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
