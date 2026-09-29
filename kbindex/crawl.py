import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from kbindex.config import RATE_LIMIT_SECONDS, USER_AGENT

ROBOTS_URL = "https://knowledge.catonetworks.com/robots.txt"
LLMS_URL = "https://knowledge.catonetworks.com/llms.txt"
_LINK = re.compile(r"\]\(([^)\s]+)")


def crawl(snapshot_root, fetch, sleep, now) -> Path:
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

    failed = []
    robots_text = _remember(ROBOTS_URL, robots_status, robots_body, robots_error, failed)
    links = []
    if llms_error is not None:
        failed.append({"url": LLMS_URL, "error": llms_error})
    elif llms_status != 200:
        failed.append({"url": LLMS_URL, "status": llms_status})
    else:
        links = _LINK.findall(llms_body.decode("utf-8", "replace"))

    robots = RobotFileParser()
    robots.parse(robots_text.splitlines())

    articles = []
    skipped = []
    seen = set()
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        reason = _skip_reason(url, robots)
        if reason is not None:
            skipped.append({"url": url, "reason": reason})
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


def _call(fetch, url):
    try:
        status, body = fetch(url)
    except Exception as exc:
        return None, b"", str(exc)
    return status, body, None


def _remember(url, status, body, error, failed):
    if error is not None:
        failed.append({"url": url, "error": error})
        return ""
    if status != 200:
        failed.append({"url": url, "status": status})
        return ""
    return body.decode("utf-8", "replace")


def _skip_reason(url, robots):
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    english_article = (
        parsed.scheme == "https"
        and parsed.netloc == "knowledge.catonetworks.com"
        and len(parts) == 2
        and parts[0] == "docs"
        and parts[1].endswith(".md")
        and not parsed.query
        and not parsed.fragment
    )
    if english_article:
        if robots.can_fetch(USER_AGENT, url):
            return None
        return "robots"
    if len(parts) == 2 and parts[1] == "llms.txt":
        return "language"
    if len(parts) == 3 and parts[0] == "docs" and parts[2].endswith(".md"):
        return "language"
    return "not an article"


def _front_matter(body):
    text = body.decode("utf-8", "replace").lstrip("\ufeff")
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end < 0:
        return None, None
    title = updated = None
    for line in text[3:end].splitlines():
        if line.startswith("title:"):
            title = _scalar(line.split(":", 1)[1])
        elif line.startswith("updated:"):
            updated = _scalar(line.split(":", 1)[1])
    return title, updated


def _scalar(raw):
    value = raw.strip()
    if value in {"", "null", "~", "''", '""'}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def main():
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=60,
    ) as client:

        def fetch(url):
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
