import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

_LINK = re.compile(r"\]\(([^)\s]+)")


def classify_url(url: str) -> str:
    """Decide whether a URL is an English article, a translation, or something else."""
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
        return "keep"
    if len(parts) == 2 and parts[1] == "llms.txt":
        return "skip_language"
    if len(parts) == 3 and parts[0] == "docs" and parts[2].endswith(".md"):
        return "skip_language"
    return "skip_not_article"


def parse_llms_links(markdown: str) -> list[str]:
    """Collect the markdown link targets from an llms.txt page."""
    return _LINK.findall(markdown)


def robots_allows(robots_text: str, url: str, user_agent: str) -> bool:
    """Return whether robots.txt allows this user agent to fetch this URL."""
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())
    return parser.can_fetch(user_agent, url)
