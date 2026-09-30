import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from core.config import RATE_LIMIT_SECONDS, USER_AGENT
from kbindex.discover import classify_url, parse_llms_links, robots_allows

ROBOTS_URL = "https://knowledge.catonetworks.com/robots.txt"
LLMS_URL = "https://knowledge.catonetworks.com/llms.txt"
_SKIP_REASON = {
    "skip_language": "language",
    "skip_not_article": "not an article",
}


def crawl(
    snapshot_root: Path | str,
    fetch: Callable[[str], tuple[int, bytes]],
    sleep: Callable[[float], None],
    now: Callable[[], datetime],
) -> Path:
    """Fetch the English knowledge-base articles and write one timestamped directory of raw markdown."""
    moment = now()
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    directory = Path(snapshot_root) / (moment.strftime("%Y-%m-%dT%H%M%S") + "Z")
    directory.mkdir(parents=True)

    robots_status, robots_body, robots_error = _call(fetch, ROBOTS_URL)
    sleep(RATE_LIMIT_SECONDS)
    llms_status, llms_body, llms_error = _call(fetch, LLMS_URL)
    sleep(RATE_LIMIT_SECONDS)

    failed: list[dict[str, str | int | None]] = []
    robots_text = _remember(ROBOTS_URL, robots_status, robots_body, robots_error, failed)
    links: list[str] = []
    if llms_error is not None:
        failed.append({"url": LLMS_URL, "error": llms_error})
    elif llms_status != 200:
        failed.append({"url": LLMS_URL, "status": llms_status})
    else:
        links = parse_llms_links(llms_body.decode("utf-8", "replace"))

    articles: list[dict[str, str | None]] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        decision = classify_url(url)
        if decision != "keep":
            skipped.append({"url": url, "reason": _SKIP_REASON[decision]})
            continue
        if not robots_allows(robots_text, url, USER_AGENT):
            skipped.append({"url": url, "reason": "robots"})
            continue
        sleep(RATE_LIMIT_SECONDS)
        status, body, error = _call(fetch, url)
        if error is not None:
            failed.append({"url": url, "error": error})
            continue
        if status != 200:
            failed.append({"url": url, "status": status})
            continue
        slug = urlparse(url).path.removeprefix("/docs/").removesuffix(".md")
        path = directory / f"{slug}.md"
        path.write_bytes(body)
        title, updated = _front_matter(body)
        articles.append(
            {
                "slug": slug,
                "file_path": path.as_posix(),
                "title": title,
                "public_url": f"https://knowledge.catonetworks.com/docs/{slug}",
                "site_updated_at": updated,
            }
        )
        if len(articles) % 50 == 0:
            print(f"saved {len(articles)}", flush=True)

    manifest = {
        "crawled_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_agent": USER_AGENT,
        "rate_limit_seconds": RATE_LIMIT_SECONDS,
        "robots_decision": robots_text,
        "discovery_source": "llms.txt",
        "articles": articles,
        "skipped": skipped,
        "failed": failed,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"done {directory} articles={len(articles)} skipped={len(skipped)} failed={len(failed)}",
        flush=True,
    )
    return directory


def _call(
    fetch: Callable[[str], tuple[int, bytes]],
    url: str,
) -> tuple[int | None, bytes, str | None]:
    try:
        status, body = fetch(url)
    except Exception as exc:
        return None, b"", str(exc)
    return status, body, None


def _remember(
    url: str,
    status: int | None,
    body: bytes,
    error: str | None,
    failed: list[dict[str, str | int | None]],
) -> str:
    if error is not None:
        failed.append({"url": url, "error": error})
        return ""
    if status != 200:
        failed.append({"url": url, "status": status})
        return ""
    return body.decode("utf-8", "replace")


def _front_matter(body: bytes) -> tuple[str | None, str | None]:
    text = body.decode("utf-8", "replace").lstrip("\ufeff")
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end < 0:
        return None, None
    title: str | None = None
    updated: str | None = None
    for line in text[3:end].splitlines():
        if line.startswith("title:"):
            title = _scalar(line.split(":", 1)[1])
        elif line.startswith("updated:"):
            updated = _scalar(line.split(":", 1)[1])
    return title, updated


def _scalar(raw: str) -> str | None:
    value = raw.strip().strip("\"'")
    return None if value in {"", "null", "~"} else value


def main() -> None:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=60,
    ) as client:

        def fetch(url: str) -> tuple[int, bytes]:
            response = client.get(url)
            return response.status_code, response.content

        crawl(
            Path("data/kb_ingestion"),
            fetch,
            time.sleep,
            lambda: datetime.now(timezone.utc),
        )


if __name__ == "__main__":
    main()
