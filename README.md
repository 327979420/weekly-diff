# The Weekly Diff

A fully automatic weekly roundup of AI and developer news in plain English: what happened, why it matters, and links to the sources.

Read it at **https://327979420.github.io/weekly-diff/**.

## What arrives when

- **Friday around 20:00 Melbourne:** a preview goes to the private Discord channel. The website preview is also available to download from the Actions run as `site-preview`.
- **Monday around 08:00 Melbourne:** the full issue appears on the website, then a short Discord post links to it. Until you go live, that post goes only to the private preview channel.

Both times are one hour earlier in Melbourne winter (19:00 Friday and 07:00 Monday). GitHub may start scheduled runs late. The website updates even while public Discord posting is disabled.

## Go live, pause, or rename

In GitHub, open **config.yaml → pencil icon**, make your change, then choose **Commit changes**.

| To… | Change… |
| --- | --- |
| Go live on public Discord | `publish_enabled: false` to `publish_enabled: true` |
| Pause scheduled runs | `paused: false` to `paused: true` |
| Resume scheduled runs | `paused: true` to `paused: false` |
| Rename the roundup | `name:` and, if wanted, `tagline:` |

A rename updates the website within a few minutes. Pausing stops the Friday and Monday schedules; manual runs and website updates from edits still work.

## Run it now

Open **Actions → Weekly issue → Run workflow**. Leave **dry run** ticked to review a downloadable `site-preview` without committing data, changing the live site, or sending Discord messages. Untick **dry run** for a real run. A real run sends public Discord only when `publish_enabled` is `true`.

Dry runs still fetch sources and use the paid AI model. To send a private preview without updating the website, choose **Friday preview** and untick **dry run**.

## One-time setup and secrets

Under **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**. The workflows need permission to write issue data to the repository and deploy Pages; branch protection must allow the automated data commits.

From a terminal in this repository, use `gh secret set NAME` for each secret below. The command prompts for its value. Never paste secrets into issues or chat, or save them in repository files.

| Name | Needed? |
| --- | --- |
| `ANTHROPIC_API_KEY` | Set this or `OPENAI_API_KEY`; one AI key is required. |
| `OPENAI_API_KEY` | Optional if Anthropic is set; otherwise required. With both, Anthropic is used by default. |
| `DISCORD_WEBHOOK_URL` | Required for public posting; optional before going live. |
| `DISCORD_PREVIEW_WEBHOOK_URL` | Optional. Without it, private previews are skipped. |
| `GITHUB_TOKEN` | Supplied automatically by Actions; do not set it as a repository secret. Optional locally for higher GitHub API limits. |

For example: `gh secret set ANTHROPIC_API_KEY`. Local commands read keys from environment variables instead of GitHub secrets.

GitHub Actions and Pages are free for this public repository. Budget a few cents per week for the AI model; actual cost varies with usage and pricing, and extra runs cost extra.

## Fix an issue

Issues are stored in **data/issues/**, one `YYYY-WW.json` file per week. Open that week's JSON in GitHub, correct the bad item's text or source link, and commit the change. Keep the JSON structure intact. The website re-renders within a few minutes; an existing Discord message is not edited automatically.

## For developers

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python run.py --dry-run collect
python run.py --dry-run build
python -m pytest -q
```

Set an AI key in your environment before building. Dry-run output goes to `build/dry-run/` and the rendered website to `site/`; `data/` stays untouched. `python run.py render` rebuilds the website from saved issues without network or AI calls. All settings live in `config.yaml`.
