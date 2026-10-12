Changes: Filter HF repacks using quant markers and configured authors; fill quick-hit minima and share non-GitHub backups, consuming each backup key once in build.py.
Changes: Configure 90-character headlines in validation and prompts; shorten at a word boundary after retry only when length is the sole error, then revalidate.
Testing: `.venv/bin/python -m pytest -q` → 349 passed.
Testing: `git diff --check` → passed.
Unfinished: None.
Questions: None.
