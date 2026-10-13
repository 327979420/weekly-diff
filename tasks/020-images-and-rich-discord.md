# 020 — Real images on the site; rich, Chinese-first Discord post

## 1. Images, self-hosted
- At build time (not in tests: mock HTTP), for each item with `image_url` (og:image / twitter:image from the source page, GitHub OpenGraph for repos/releases): download it (timeout 10 s, ≤ 5 MB, content-type image/*), resize with Pillow to max 640 px wide, save as WebP (quality ~80) to `site/assets/img/{issue_id}/{item-slug}.webp`, and record the relative path as `Item.extra.image_local` in the saved issue JSON. Failed download → no image (never a grey box). Add Pillow to requirements.txt.
- Images must survive re-renders: keep a cache dir `data/images/{issue_id}/` (committed, small WebP files) and copy them into `site/` on every render; `run.py render` must not need the network.
- Website (issue + home): a thumbnail per item when `image_local` exists: desktop ≥ 900 px → 160×90 rounded (8 px, hairline border) on the right of the item text, `object-fit: cover`; mobile → full-width 16:9 below the meta line. `loading="lazy"`, `decoding="async"`, `alt` = headline, explicit width/height to avoid layout shift. The first highlight's item image may appear as a wide 16:9 hero under the issue title (only if it exists).
- Remove the hotlink allowlist logic for the site (images are now local); keep image URLs only for Discord (Discord fetches them itself) — use the published local image URL `{base_url}/assets/img/...` for Discord so it always works.
- Budget: ≤ 15 images × ~40 KB; home HTML+CSS+JS stays < 50 KB (images excluded).

## 2. Discord: Chinese by default, card style
- Config `discord.languages: [zh]` (default; `[zh, en]` re-enables English as a second message). Validate.
- One message per language. `content`: `📰 **The Weekly Diff · 第 42 期** 已更新 · 10月6日 – 13日` (preview adds `【预览】` in front).
- Embeds (max 10 per message, total ≤ 6000 chars):
  1. Header embed: title `本周要点`, url = issue page, description = the 3 highlights numbered `**1.** …`, `image` = hero image (first highlight's item image) if present, colour `#FF5A1F`.
  2. One embed per top item (5): `title` = `{emoji} {headline}` linking to the source, `description` = takeaway + newline + `**上手：** …` (if present), `thumbnail` = item image if present, `footer` = `{source domain} · {tag label}`, colour = accent.
  3. Last embed: description `[阅读完整一期 →]({issue url}) · [往期]({archive url}) · RSS`, footer `每周一 08:00（墨尔本）更新`.
- Keep escaping, mention neutralisation, `allowed_mentions`, limits (trim per-embed text, drop the last item embeds if the 6000 total is exceeded), preview/public routing and `publish_enabled` exactly as now.

## Done means
Tests: image download success/failure/size limit (mocked), resize to WebP, render uses cached images offline, thumbnail markup only when present; Discord zh-only default, `[zh,en]` gives two messages, embed count and total length within limits, preview prefix, header hero image. `.venv/bin/python -m pytest -q` passes; `.venv/bin/python run.py render` exits 0. Report + COLLAB-LOG entry. No commit/push; don't touch publish_enabled.
