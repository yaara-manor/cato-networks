from pathlib import Path

from kbindex.hashing import sha256_file


def load_policies(policies_dir) -> list:
    # Read the six policy files into records, including POL-SLA.
    policies_dir = Path(policies_dir)
    repo = Path(__file__).resolve().parents[1]
    records = []
    for path in sorted(policies_dir.glob("POL-*.md")):
        text = path.read_text(encoding="utf-8")
        title = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        try:
            rel_path = path.resolve().relative_to(repo).as_posix()
        except ValueError:
            rel_path = str(path)
        records.append({
            "id": path.stem,
            "title": title,
            "content_hash": sha256_file(path),
            "file_path": rel_path,
            "body": text,
        })
    return records
