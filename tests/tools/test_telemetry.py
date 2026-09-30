from datetime import datetime, timezone
from pathlib import Path

from core.clock import SimulationClock
from tools import TelemetryEvidence, TelemetryService, TelemetryStatus


def test_munich_bureau_lte_no_carrier_anomaly() -> None:
    service = TelemetryService()

    list_res = service.list_sites("ACC-1008")
    assert list_res.status == TelemetryStatus.OK
    assert list_res.data is not None
    assert any(s.site_id == "S-1008-02" and s.status == "disconnected" for s in list_res.data.sites)

    site_res = service.get_site_status("S-1008-02")
    assert site_res.status == TelemetryStatus.OK
    assert site_res.data is not None
    assert site_res.data.customer_id == "ACC-1008"
    assert site_res.data.status == "disconnected"
    assert any(ev.metric_key == "status" and ev.raw_value == "disconnected" and ev.is_anomaly for ev in site_res.evidence)

    lq_res = service.get_link_quality("S-1008-02")
    assert lq_res.status == TelemetryStatus.OK
    assert lq_res.data is not None
    links_by_name = {link.link: link for link in lq_res.data.links}
    assert "WAN1" in links_by_name
    assert "WAN2" in links_by_name
    assert links_by_name["WAN1"].latest_packet_loss_pct == 100.0
    assert links_by_name["WAN2"].latest_packet_loss_pct == 100.0
    assert links_by_name["WAN1"].down_intervals > 0
    assert links_by_name["WAN2"].down_intervals > 0
    assert any(ev.metric_key == "WAN1.packet_loss_pct" and ev.is_anomaly for ev in lq_res.evidence)
    assert any(ev.metric_key == "WAN2.packet_loss_pct" and ev.is_anomaly for ev in lq_res.evidence)

    ev_res = service.get_events("S-1008-02")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    assert any(
        "Last Resort link WAN2 (LTE) has no carrier signal" in ev.message
        for ev in ev_res.data.events
    )
    assert any(
        "Last Resort link WAN2 (LTE) has no carrier signal" in ev.raw_value and ev.is_anomaly
        for ev in ev_res.evidence
    )


def test_austin_office_bgp_prefix_exhaustion_anomaly() -> None:
    service = TelemetryService()

    bgp_res = service.get_bgp_status("S-1007-01")
    assert bgp_res.status == TelemetryStatus.OK
    assert bgp_res.data is not None
    assert len(bgp_res.data.neighbors) >= 1
    neighbor = bgp_res.data.neighbors[0]
    assert neighbor.routes_count == 1024
    assert neighbor.routes_limit == 1024
    assert neighbor.last_error == "Hold Timer Expired"
    assert neighbor.flaps_24h == 11
    assert neighbor.hold_time_negotiated == 30

    assert any(
        ev.metric_key == "routes_count" and ev.raw_value == "1024/1024" and ev.is_anomaly
        for ev in bgp_res.evidence
    )
    assert any(
        ev.metric_key == "last_error" and ev.raw_value == "Hold Timer Expired" and ev.is_anomaly
        for ev in bgp_res.evidence
    )
    assert any(
        ev.metric_key == "flaps_24h" and ev.raw_value == "11" and ev.is_anomaly
        for ev in bgp_res.evidence
    )
    assert any(
        ev.metric_key == "hold_time" and "negotiated 30s" in ev.raw_value and ev.is_anomaly
        for ev in bgp_res.evidence
    )


def test_aws_eu_central_1_ipsec_no_proposal_chosen_anomaly() -> None:
    service = TelemetryService()

    ipsec_res = service.get_ipsec_status("S-1002-03")
    assert ipsec_res.status == TelemetryStatus.OK
    assert ipsec_res.data is not None
    assert ipsec_res.data.primary.last_error == "NO_PROPOSAL_CHOSEN"
    assert ipsec_res.data.secondary is not None
    assert ipsec_res.data.secondary.last_error == "NO_PROPOSAL_CHOSEN"
    assert ipsec_res.data.init_message_parameters is not None
    assert ipsec_res.data.init_message_parameters.encryption == "AES GCM 256"
    assert ipsec_res.data.peer_reported_parameters_from_pcap is not None
    assert ipsec_res.data.peer_reported_parameters_from_pcap.child_sa_encryption == "AES CBC 256"
    assert ipsec_res.data.note is not None

    assert any(
        ev.metric_key == "primary.status" and "NO_PROPOSAL_CHOSEN" in ev.raw_value and ev.is_anomaly
        for ev in ipsec_res.evidence
    )
    assert any(
        ev.metric_key == "secondary.status" and "NO_PROPOSAL_CHOSEN" in ev.raw_value and ev.is_anomaly
        for ev in ipsec_res.evidence
    )
    assert any(
        ev.metric_key == "cipher_proposal"
        and "AES GCM 256" in ev.raw_value
        and "AES CBC 256" in ev.raw_value
        and ev.is_anomaly
        for ev in ipsec_res.evidence
    )
    assert any(
        ev.metric_key == "note" and ev.raw_value == ipsec_res.data.note and ev.is_anomaly
        for ev in ipsec_res.evidence
    )


def test_denver_clinic_socket_upgrade_grace_time_anomaly() -> None:
    service = TelemetryService()

    site_res = service.get_site_status("S-1009-01")
    assert site_res.status == TelemetryStatus.OK
    assert site_res.data is not None
    assert site_res.data.customer_id == "ACC-1009"
    assert site_res.data.status == "disconnected"
    assert any(ev.metric_key == "status" and ev.raw_value == "disconnected" and ev.is_anomaly for ev in site_res.evidence)

    ev_res = service.get_events("S-1009-01")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    assert any("No open tunnel after grace time" in ev.message for ev in ev_res.data.events)
    assert any(
        "No open tunnel after grace time" in ev.raw_value and ev.is_anomaly
        for ev in ev_res.evidence
    )


def test_perth_mine_site_ha_version_mismatch_anomaly() -> None:
    service = TelemetryService()

    ev_res = service.get_events("S-1010-01")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    assert any("HA Not Ready" in ev.sub_type or "HA Not Ready" in ev.message for ev in ev_res.data.events)
    assert any(
        "Compatible Version check failed: primary 27.0.19812, secondary 26.0.18990" in ev.message
        for ev in ev_res.data.events
    )
    assert any(
        "HA Not Ready" in ev.metric_key
        and "Compatible Version check failed: primary 27.0.19812, secondary 26.0.18990" in ev.raw_value
        and ev.is_anomaly
        for ev in ev_res.evidence
    )


def test_sydney_bureau_link_quality_and_4d_event_preserved() -> None:
    service = TelemetryService()

    list_res = service.list_sites("ACC-1008")
    assert list_res.status == TelemetryStatus.OK
    assert list_res.data is not None
    assert any(s.site_id == "S-1008-03" for s in list_res.data.sites)

    lq_res = service.get_link_quality("S-1008-03")
    assert lq_res.status == TelemetryStatus.OK
    assert lq_res.data is not None
    assert len(lq_res.data.links) >= 1
    link = lq_res.data.links[0]
    assert link.max_packet_loss_pct >= 2.0
    assert link.max_jitter_ms >= 30.0
    assert any(ev.metric_key.endswith(".packet_loss_pct") and ev.is_anomaly for ev in lq_res.evidence)
    assert any(ev.metric_key.endswith(".jitter_ms") and ev.is_anomaly for ev in lq_res.evidence)

    ev_res = service.get_events("S-1008-03", window="24h")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    expected_ts = datetime(2026, 8, 24, 17, 0, 0, tzinfo=timezone.utc)
    assert any(
        ev.ts == expected_ts and ev.sub_type == "Last-Mile Quality"
        for ev in ev_res.data.events
    )


def test_client_diagnostics_hotel_wifi_captive_portal() -> None:
    service = TelemetryService()

    diag_res = service.get_client_diagnostics("sam.dubois@atlas-eng.com")
    assert diag_res.status == TelemetryStatus.OK
    assert diag_res.data is not None
    assert diag_res.data.last_error is not None
    assert "TUNNEL_TIMEOUT (408)" in diag_res.data.last_error
    assert diag_res.data.network.captive_portal_detected is True
    assert diag_res.data.network.udp_443_reachable is False
    assert diag_res.data.network.tcp_443_reachable is False

    assert any(
        ev.metric_key == "last_error" and "TUNNEL_TIMEOUT (408)" in ev.raw_value and ev.is_anomaly
        for ev in diag_res.evidence
    )
    assert any(
        ev.metric_key == "captive_portal_detected" and ev.raw_value == "true" and ev.is_anomaly
        for ev in diag_res.evidence
    )
    assert any(
        ev.metric_key == "reachability"
        and "udp_443=False" in ev.raw_value
        and "tcp_443=False" in ev.raw_value
        and ev.is_anomaly
        for ev in diag_res.evidence
    )


def test_chicago_studio_flapping_and_upstream_loss() -> None:
    service = TelemetryService()

    ev_res = service.get_events("S-1008-01")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    disconnected_count = sum(1 for ev in ev_res.data.events if ev.action == "Disconnected")
    reconnected_count = sum(1 for ev in ev_res.data.events if ev.action == "Reconnected")
    assert disconnected_count == 8
    assert reconnected_count == 8
    assert any("22%" in ev.message and "upstream" in ev.message.lower() for ev in ev_res.data.events)


def test_fortigate_dc_ipsec_authentication_failed() -> None:
    service = TelemetryService()

    ipsec_res = service.get_ipsec_status("S-1010-02")
    assert ipsec_res.status == TelemetryStatus.OK
    assert ipsec_res.data is not None
    assert ipsec_res.data.primary.last_error == "AUTHENTICATION_FAILED"
    assert ipsec_res.data.secondary is not None
    assert ipsec_res.data.secondary.last_error == "AUTHENTICATION_FAILED"
    assert ipsec_res.data.psk_last_changed == datetime(2026, 8, 27, 15, 0, 0, tzinfo=timezone.utc)
    assert ipsec_res.data.note is not None
    assert "26h" in ipsec_res.data.note or "PSK" in ipsec_res.data.note

    assert any(
        ev.metric_key == "primary.status" and "AUTHENTICATION_FAILED" in ev.raw_value and ev.is_anomaly
        for ev in ipsec_res.evidence
    )
    assert any(
        ev.metric_key == "secondary.status" and "AUTHENTICATION_FAILED" in ev.raw_value and ev.is_anomaly
        for ev in ipsec_res.evidence
    )
    assert any(
        ev.metric_key == "psk_last_changed" and ev.raw_value == "2026-08-27T15:00:00Z"
        for ev in ipsec_res.evidence
    )


def test_pittsburgh_plant_c2_blocks() -> None:
    service = TelemetryService()

    ev_res = service.get_events("S-1004-01", event_type="Security")
    assert ev_res.status == TelemetryStatus.OK
    assert ev_res.data is not None
    c2_events = [
        ev
        for ev in ev_res.data.events
        if "badexfil-cdn.net" in ev.message or (ev.dst and "badexfil-cdn.net" in ev.dst)
    ]
    assert len(c2_events) == 6
    assert all(ev.action == "Block" for ev in c2_events)


def test_boundary_validation_and_malformed_identifiers() -> None:
    service = TelemetryService()

    assert service.list_sites("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.list_sites("INVALID-1").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.list_sites("").status == TelemetryStatus.INVALID_ARGUMENT

    assert service.get_site_status("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_site_status("S-999").status == TelemetryStatus.INVALID_ARGUMENT

    assert service.get_link_quality("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_link_quality("S-1008-02", window="invalid").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_link_quality("S-1008-02", window="0h").status == TelemetryStatus.INVALID_ARGUMENT

    assert service.get_events("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_events("S-1008-02", window="bad_window").status == TelemetryStatus.INVALID_ARGUMENT

    assert service.get_bgp_status("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_ipsec_status("../../.env").status == TelemetryStatus.INVALID_ARGUMENT

    assert service.get_client_diagnostics("../../.env").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_client_diagnostics("not-an-email").status == TelemetryStatus.INVALID_ARGUMENT
    assert service.get_client_diagnostics("a/b@example.com").status == TelemetryStatus.INVALID_ARGUMENT


def test_not_found_entities() -> None:
    service = TelemetryService()

    assert service.list_sites("ACC-9999").status == TelemetryStatus.NOT_FOUND
    assert service.get_site_status("S-9999-99").status == TelemetryStatus.NOT_FOUND
    assert service.get_link_quality("S-9999-99").status == TelemetryStatus.NOT_FOUND
    assert service.get_events("S-9999-99").status == TelemetryStatus.NOT_FOUND
    assert service.get_bgp_status("S-1008-02").status == TelemetryStatus.NOT_FOUND
    assert service.get_ipsec_status("S-1008-02").status == TelemetryStatus.NOT_FOUND
    assert service.get_client_diagnostics("nobody@nowhere.example").status == TelemetryStatus.NOT_FOUND


def test_corrupt_or_missing_files_return_unavailable(tmp_path: Path) -> None:
    empty_service = TelemetryService(telemetry_dir=tmp_path)
    assert empty_service.list_sites("ACC-1008").status == TelemetryStatus.UNAVAILABLE
    assert empty_service.get_site_status("S-1008-02").status == TelemetryStatus.UNAVAILABLE

    (tmp_path / "sites.json").write_text("{not valid json", encoding="utf-8")
    (tmp_path / "link_quality").mkdir()
    (tmp_path / "link_quality" / "S-1008-02.csv").write_text("bad_header_1,bad_header_2\n1,2\n", encoding="utf-8")
    (tmp_path / "events").mkdir()
    (tmp_path / "events" / "S-1008-02.jsonl").write_text("{corrupt jsonl}\n", encoding="utf-8")
    (tmp_path / "bgp_status").mkdir()
    (tmp_path / "bgp_status" / "S-1007-01.json").write_text("[]", encoding="utf-8")
    (tmp_path / "ipsec_status").mkdir()
    (tmp_path / "ipsec_status" / "S-1002-03.json").write_text("{}", encoding="utf-8")
    (tmp_path / "clients").mkdir()
    (tmp_path / "clients" / "sam.dubois@atlas-eng.com.json").write_text("not json", encoding="utf-8")

    corrupt_service = TelemetryService(telemetry_dir=tmp_path)
    assert corrupt_service.list_sites("ACC-1008").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_site_status("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_link_quality("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_events("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_bgp_status("S-1007-01").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_ipsec_status("S-1002-03").status == TelemetryStatus.UNAVAILABLE
    assert corrupt_service.get_client_diagnostics("sam.dubois@atlas-eng.com").status == TelemetryStatus.UNAVAILABLE


def test_timeout_returns_unavailable() -> None:
    timed_out_service = TelemetryService(
        clock=SimulationClock.frozen(),
        timeout_seconds=0.0,
    )
    assert timed_out_service.list_sites("ACC-1008").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_site_status("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_link_quality("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_events("S-1008-02").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_bgp_status("S-1007-01").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_ipsec_status("S-1002-03").status == TelemetryStatus.UNAVAILABLE
    assert timed_out_service.get_client_diagnostics("sam.dubois@atlas-eng.com").status == TelemetryStatus.UNAVAILABLE


def test_telemetry_evidence_format_citation() -> None:
    ev = TelemetryEvidence(
        tool_name="get_bgp_status",
        metric_key="routes_count",
        raw_value="1024/1024",
        timestamp=datetime(2026, 8, 28, 16, 55, 0, tzinfo=timezone.utc),
        is_anomaly=True,
    )
    assert ev.format_citation() == "routes_count 1024/1024 [telemetry:get_bgp_status]"
