import pytest

from guardrails import CitationMarker, MarkerKind, extract_markers, strip_markers


@pytest.mark.parametrize(
    ("message", "markers", "stripped"),
    [
        (
            "Raise MTU [kb:tunnels#mtu]. See [policy:POL-SEV1] and [telemetry:get_site_health] [kb:tunnels#mtu]",
            (
                CitationMarker(kind=MarkerKind.KB, ref="tunnels#mtu"),
                CitationMarker(kind=MarkerKind.POLICY, ref="POL-SEV1"),
                CitationMarker(kind=MarkerKind.TELEMETRY, ref="get_site_health"),
            ),
            "Raise MTU . See and",
        ),
        ("No markers here.", (), "No markers here."),
    ],
)
def test_extract_and_strip(
    message: str, markers: tuple[CitationMarker, ...], stripped: str
) -> None:
    assert extract_markers(message) == markers
    assert strip_markers(message) == stripped
