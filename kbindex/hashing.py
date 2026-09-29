import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    # Return the lowercase hex SHA-256 of these bytes.
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    # Return the lowercase hex SHA-256 of a file's raw bytes.
    return sha256_bytes(Path(path).read_bytes())


def write_manifest_hashes(crawl_dir: Path | str) -> None:
    # Store each saved article's SHA-256 on its manifest entry.
    crawl_dir = Path(crawl_dir)
    manifest_path = crawl_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    repo = Path(__file__).resolve().parents[1]
    for article in manifest["articles"]:
        article["content_hash"] = sha256_file(repo / article["file_path"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
