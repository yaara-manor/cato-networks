import json
from pathlib import Path

from kbindex.config import USER_AGENT
from kbindex.discover import classify_url, robots_allows

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"


def test_saved_articles_are_english_docs():
    crawl_dir = sorted(path for path in ROOT.iterdir() if path.is_dir())[-1]
    manifest = json.loads((crawl_dir / "manifest.json").read_text())
    for article in manifest["articles"]:
        slug = article["slug"]
        assert "/" not in slug
        assert Path(article["file_path"]).name == f"{slug}.md"
        assert classify_url(f"{article['public_url']}.md") == "keep"
    for skipped in manifest["skipped"]:
        url = skipped["url"]
        if skipped["reason"] == "robots":
            assert robots_allows(manifest["robots_decision"], url, USER_AGENT) is False
        else:
            assert classify_url(url) in {"skip_language", "skip_not_article"}
