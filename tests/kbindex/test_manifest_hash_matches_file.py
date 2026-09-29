import json
from pathlib import Path

from kbindex.hashing import sha256_file

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data" / "kb_ingestion"


def test_manifest_hash_matches_file(tmp_path):
    crawl_dir = sorted(path for path in ROOT.iterdir() if path.is_dir())[-1]
    manifest = json.loads((crawl_dir / "manifest.json").read_text())
    articles = manifest["articles"]
    assert articles
    for article in articles:
        saved = REPO / article["file_path"]
        assert sha256_file(saved) == article["content_hash"]

    sample = REPO / articles[0]["file_path"]
    original = sample.read_bytes()
    copy = tmp_path / sample.name
    copy.write_bytes(original + b"x")
    assert sha256_file(copy) != articles[0]["content_hash"]
    assert sample.read_bytes() == original
