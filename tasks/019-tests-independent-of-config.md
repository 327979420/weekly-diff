# 019 — No test may depend on the live config.yaml values

## What happened
Claude changed `llm.min_score` in config.yaml from 5 to 4 (so the vibe-coder scoring fills 10+ items; the live run now gives 10). 10 tests failed because they load the real config.yaml and assume min_score 5. Same class of bug as 014-fix. CI on main is red.

## Change
- Every test that needs a Config must build it from `tests/fixtures/config.yaml` (or a helper fixture in conftest.py that loads it and allows overrides). Only one test may load the real `config.yaml`: a smoke test that it parses and validates.
- Fix the 10 failing tests and grep for any other `load_config()` without a fixture path in tests/.
- Do not change config.yaml.

## Done means
`.venv/bin/python -m pytest -q` → all pass with the current config.yaml **and** still pass if `llm.min_score` is temporarily set back to 5 (check, then restore). Report + COLLAB-LOG entry. No commit/push; don't touch publish_enabled.
