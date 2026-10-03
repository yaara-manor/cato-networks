import pytest

from guardrails import MarkerKind
from orchestration import Citation
from ui.citation_render import render_reply, site_anchor

_KB = Citation(
    kind=MarkerKind.KB,
    ref="playbook#step-2---reduce",
    title="BGP Playbook",
    url="https://kb.example/playbook",
    heading="Step 2 - Reduce the number of advertised routes",
)
_POLICY = Citation(kind=MarkerKind.POLICY, ref="POL-SLA", title="SLA policy")


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [  # ids taken from the live knowledge-base page
        ("Step 2 - Reduce the number of advertised routes", "step-2-reduce-the-number-of-advertised-routes"),
        ("Using the Story Drill-down", "using-the-story-drilldown"),
        ("Check BGP Status", "check-bgp-status"),
    ],
)
def test_site_anchor_matches_the_site_heading_ids(heading: str, anchor: str) -> None:
    assert site_anchor(heading) == anchor


def test_markers_become_numbered_section_links_and_tool_tags() -> None:
    text = "Summarize routes [kb:playbook#step-2---reduce]. SLA applies [policy:POL-SLA]. Seen [telemetry:get_bgp_status]."
    assert render_reply(text, (_KB, _POLICY)) == (
        "Summarize routes [1](https://kb.example/playbook#step-2-reduce-the-number-of-advertised-routes). "
        "SLA applies [2]. Seen *(get_bgp_status)*."
    )


def test_marker_closing_a_blockquote_becomes_its_attribution() -> None:
    text = "The guide says:\n> Summarizing your prefixes reduces the route count. [kb:playbook#step-2---reduce]\nMore."
    assert render_reply(text, (_KB,)).splitlines() == [
        "The guide says:",
        "> Summarizing your prefixes reduces the route count.  ",
        "> — [BGP Playbook › Step 2 - Reduce the number of advertised routes]"
        "(https://kb.example/playbook#step-2-reduce-the-number-of-advertised-routes)",
        "More.",
    ]


def test_unresolved_marker_is_dropped() -> None:
    assert render_reply("Claim [kb:ghost#nope] done.", ()) == "Claim done."
