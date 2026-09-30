import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"


def test_crawled_article_has_text():
    crawl_dir = max(path for path in ROOT.iterdir() if path.is_dir())
    manifest = json.loads((crawl_dir / "manifest.json").read_text())
    article = manifest["articles"][0]
    body = (REPO / article["file_path"]).read_text()
    assert body.strip()
    assert ".md" not in article["public_url"]
    for saved in manifest["articles"]:
        path = saved["file_path"]
        assert "/docs/fr/" not in path
        assert "llms.txt" not in path
