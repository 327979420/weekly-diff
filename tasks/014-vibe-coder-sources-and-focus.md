# 014 — Vibe-coder focus and broader, practical sources

## Reader persona (put this in the score, summarise and sixty prompts)
The reader is a **vibe coder**: builds apps and automations with AI tools (Claude Code, Codex, Cursor, Lovable, Bolt, Replit, v0…), is comfortable with a terminal and GitHub but is not a professional engineer, cares about what they can try this week, cost/free tiers, and which models are good for coding. Every item must answer: **what is it, what can I do with it, how do I start.**

## Scoring changes
- Favour: new or updated AI coding tools and features; models that matter for coding/agents (with price or speed facts from the source); MCP servers, skills, templates and starter repos; free-tier/pricing/limit changes; practical guides and tutorials from credible authors; useful trending repos and Hugging Face Spaces you can try in a browser.
- Penalise: funding, partnerships, enterprise deals, policy, pure research papers with nothing to try, rumours, minor patch releases with only bug fixes (unless widely used, e.g. Claude Code / Codex / Cursor — then one combined item).
- Add to the score output a boolean `try_now` (can the reader try it today?); prefer `try_now` items when filling sections and the top list.

## Sources to add (verify each live before adding; drop any that fail, and list results in the report)
Use the existing collector types (rss, html_index, github_releases, github_trending queries, huggingface); add a new collector only where noted.
- RSS / changelogs: Simon Willison (`https://simonwillison.net/atom/everything/`), GitHub Changelog Copilot label (`https://github.blog/changelog/label/copilot/feed/`), Google Developers Blog, Vercel changelog, Supabase blog, Replit blog, Zed blog, Hugging Face blog (already present) — find the correct feed URL for each.
- html_index (changelog pages without RSS): Lovable changelog, Windsurf changelog, Bolt / StackBlitz blog, OpenAI Codex changelog (developers.openai.com), v0 / Vercel AI changelog if separate. Use `link_pattern` + publish date as now; skip pages without dates.
- github_releases: add `ollama/ollama`, `zed-industries/zed`, `Kilo-Org/kilocode`, `charmbracelet/crush`, `vercel/ai`, `modelcontextprotocol/servers` (check each repo exists and publishes releases; use the canonical owner/name).
- github_trending queries: add `topic:mcp-server`, `topic:claude-code`, `topic:vibe-coding`, `topic:cursor`, `topic:ai-coding` (created in window, stars > 50).
- huggingface: new `spaces` mode: `GET https://huggingface.co/api/spaces?sort=trendingScore&direction=-1&limit=20`, keep Spaces created within 30 days; section_hint `quick`, key `hfspace:{id}`, url `https://huggingface.co/spaces/{id}`.
- New collector `reddit.py`: top posts of the week from r/vibecoding, r/ClaudeAI, r/cursor, r/ChatGPTCoding, r/LocalLLaMA via `https://www.reddit.com/r/{sub}/top.json?t=week&limit=25` with the configured User-Agent; keep posts with score ≥ a config threshold (start 300). If the post links outward, use that URL as the source (primary preferred); self-posts use the Reddit permalink. If Reddit returns 403/429 (common from cloud IPs), log and skip — never fail the run. Config switch `sources.reddit.enabled`.
- Make every new source fail gracefully exactly like the existing ones; keep total collect time reasonable (< 3 minutes).

## Tags
Replace the three tags with vibe-coder ones (config + validation + site/Discord labels, both languages): `try` "🚀 Try it now / 马上能试", `learn` "📚 Learn / 学一招", `watch` "👀 Worth watching / 值得关注". Old issues with old tag keys must still render (map builders→try, work→learn, beginner→learn).

## Done means
- Tests for: reddit collector (normal, 403 skip, outward link vs self-post), HF spaces, new tags + legacy mapping, `try_now` preference in selection.
- `.venv/bin/python -m pytest -q` → all pass. A live `--dry-run collect` lists per-source counts in the report (needs network; if blocked, say so).
- Do not touch `publish_enabled`. Do not commit or push. Report + COLLAB-LOG entry per AGENTS.md.

## Test command
`.venv/bin/python -m pytest -q`
