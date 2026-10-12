from pathlib import Path
from weekly_diff import paths


def test_repo_paths_and_on_demand_creation(tmp_path: Path) -> None:
    assert paths.ROOT == Path(__file__).resolve().parent.parent
    assert paths.ISSUES == paths.DATA / "issues"
    assert paths.SEEN == paths.DATA / "seen.json"
    assert paths.STARS == paths.DATA / "stars.json"
    assert paths.DRY_RUN == paths.BUILD / "dry-run"
    assert paths.SITE == paths.ROOT / "site"
    target = tmp_path / "new" / "nested"
    assert not target.exists()
    assert paths.ensure_directory(target) == target
    assert paths.ensure_directory(target).is_dir()
