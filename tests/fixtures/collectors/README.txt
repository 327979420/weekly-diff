Source samples recorded on 2026-10-12; request URLs are in provenance.json.
rss.xml, index.html, article.html, releases.json, repos.json, hn.json and hf.json
are trimmed public responses. Bodies and fields unrelated to parsing were removed.
Hugging Face full=true includes createdAt, author and trendingScore.
repo-small/large, snapshots, release-flags, hn-cases and hf-org are controlled
variants of these records for deterministic limits and boundary tests.
Stargazers access returned HTTP 403. stars-page1/page2/invalid use the documented
star+json response shape with controlled timestamps (no real user data).
text.html and malformed/empty/error fixtures exercise extraction and failures.
atom.xml adapts recorded RSS items for Atom updated/content precedence tests.
