from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

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
        ev.metric_key == "udp_443_reachable" and ev.raw_value == "false" and ev.is_anomaly
        for ev in diag_res.evidence
    )
    assert any(
        ev.metric_key == "tcp_443_reachable" and ev.raw_value == "false" and ev.is_anomaly
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


def test_embedded_identity_mismatch_returns_unavailable(tmp_path: Path) -> None:
    # 1. BGP file with mismatched embedded site_id
    (tmp_path / "bgp_status").mkdir()
    bgp_mismatch = {
        "site_id": "S-9999-99",
        "queried_at": "2026-08-28T17:00:00Z",
        "neighbors": [
            {
                "peer_ip": "10.0.0.1",
                "peer_asn": 65001,
                "cato_asn": 65002,
                "state": "Established",
                "hold_time_configured": 60,
                "keepalive_configured": 20,
                "routes_count": 10,
                "routes_limit": 100,
            }
        ],
    }
    (tmp_path / "bgp_status" / "S-1007-01.json").write_text(json.dumps(bgp_mismatch), encoding="utf-8")

    # 2. IPsec file with mismatched embedded site_id
    (tmp_path / "ipsec_status").mkdir()
    ipsec_mismatch = {
        "site_id": "S-8888-88",
        "peer": "Azure",
        "ike_version": "ikev2",
        "initiator": "cato",
        "primary": {"status": "up"},
        "queried_at": "2026-08-28T17:00:00Z",
    }
    (tmp_path / "ipsec_status" / "S-1002-03.json").write_text(json.dumps(ipsec_mismatch), encoding="utf-8")

    # 3. Client diagnostics file with mismatched embedded user_email
    (tmp_path / "clients").mkdir()
    client_mismatch = {
        "user_email": "other.user@example.com",
        "customer_id": "ACC-1008",
        "os": "macOS",
        "client_version": "5.4.1",
        "last_connect_attempt": "2026-08-28T17:00:00Z",
        "network": {
            "captive_portal_detected": False,
            "udp_443_reachable": True,
            "tcp_443_reachable": True,
        },
        "queried_at": "2026-08-28T17:00:00Z",
    }
    (tmp_path / "clients" / "sam.dubois@atlas-eng.com.json").write_text(json.dumps(client_mismatch), encoding="utf-8")

    # 4. Events file with an event that has mismatched site_id
    (tmp_path / "events").mkdir()
    event_valid = {
        "ts": "2026-08-28T16:00:00Z",
        "site_id": "S-1008-02",
        "event_type": "Connectivity",
        "sub_type": "Keepalive",
        "action": "Connected",
        "message": "Connected",
    }
    event_invalid = {
        "ts": "2026-08-28T16:01:00Z",
        "site_id": "S-9999-99",
        "event_type": "Connectivity",
        "sub_type": "Keepalive",
        "action": "Connected",
        "message": "Foreign event",
    }
    events_text = f"{json.dumps(event_valid)}\n{json.dumps(event_invalid)}\n"
    (tmp_path / "events" / "S-1008-02.jsonl").write_text(events_text, encoding="utf-8")

    service = TelemetryService(telemetry_dir=tmp_path)
    assert service.get_bgp_status("S-1007-01").status == TelemetryStatus.UNAVAILABLE
    assert service.get_ipsec_status("S-1002-03").status == TelemetryStatus.UNAVAILABLE
    assert service.get_client_diagnostics("sam.dubois@atlas-eng.com").status == TelemetryStatus.UNAVAILABLE
    assert service.get_events("S-1008-02").status == TelemetryStatus.UNAVAILABLE


def test_client_diagnostics_reachability_and_ssid_evidence() -> None:
    service = TelemetryService()
    res = service.get_client_diagnostics("sam.dubois@atlas-eng.com")
    assert res.status == TelemetryStatus.OK
    assert res.data is not None

    udp_ev = next((ev for ev in res.evidence if ev.metric_key == "udp_443_reachable"), None)
    assert udp_ev is not None
    assert udp_ev.raw_value == "false"
    assert udp_ev.is_anomaly is True

    tcp_ev = next((ev for ev in res.evidence if ev.metric_key == "tcp_443_reachable"), None)
    assert tcp_ev is not None
    assert tcp_ev.raw_value == "false"
    assert tcp_ev.is_anomaly is True

    ssid_ev = next((ev for ev in res.evidence if ev.metric_key == "ssid"), None)
    assert ssid_ev is not None
    assert ssid_ev.raw_value == "HotelWifi"
    assert ssid_ev.is_anomaly is False


def test_positive_timeout_enforcement_returns_unavailable() -> None:
    def slow_parse(text: str) -> str:
        time.sleep(0.05)
        return text

    service = TelemetryService(timeout_seconds=0.005)
    res = service._load_validated(
        "test_tool",
        "ACC-1008",
        re.compile(r"^ACC-\d{4}$"),
        "account_id",
        "sites.json",
        slow_parse,
    )
    assert isinstance(res, TelemetryEvidence) is False
    assert res.status == TelemetryStatus.UNAVAILABLE


def test_finite_state_normalization_and_classification(tmp_path: Path) -> None:
    # 1. Lowercase "alert" action normalized and classified as anomaly
    (tmp_path / "events").mkdir()
    event_alert = {
        "ts": "2026-08-28T16:00:00Z",
        "site_id": "S-1008-02",
        "event_type": "Security",
        "sub_type": "Threat",
        "action": "alert",
        "message": "Potential threat detected",
    }
    (tmp_path / "events" / "S-1008-02.jsonl").write_text(json.dumps(event_alert) + "\n", encoding="utf-8")

    service = TelemetryService(telemetry_dir=tmp_path)
    res = service.get_events("S-1008-02")
    assert res.status == TelemetryStatus.OK
    assert res.data is not None
    assert res.data.events[0].action == "Alert"
    assert any(ev.metric_key == "Security/Threat (Alert)" and ev.is_anomaly for ev in res.evidence)

    # 2. Unsupported action variant rejected
    (tmp_path / "events" / "S-1008-02.jsonl").write_text(
        json.dumps({**event_alert, "action": "NonExistentAction"}) + "\n",
        encoding="utf-8",
    )
    assert service.get_events("S-1008-02").status == TelemetryStatus.UNAVAILABLE

    # 3. BGP neighbor state evidence classification
    (tmp_path / "bgp_status").mkdir()
    bgp_data = {
        "site_id": "S-1007-01",
        "queried_at": "2026-08-28T17:00:00Z",
        "neighbors": [
            {
                "peer_ip": "10.0.0.1",
                "peer_asn": 65001,
                "cato_asn": 65002,
                "state": "established",
                "hold_time_configured": 60,
                "keepalive_configured": 20,
                "routes_count": 10,
                "routes_limit": 100,
            }
        ],
    }
    (tmp_path / "bgp_status" / "S-1007-01.json").write_text(json.dumps(bgp_data), encoding="utf-8")
    bgp_res = service.get_bgp_status("S-1007-01")
    assert bgp_res.status == TelemetryStatus.OK
    assert bgp_res.data is not None
    assert bgp_res.data.neighbors[0].state == "Established"
    assert any(ev.metric_key == "state" and ev.raw_value == "Established" and not ev.is_anomaly for ev in bgp_res.evidence)


def test_oversized_window_regression_1000000000d() -> None:
    service = TelemetryService()
    res_days = service.get_link_quality("S-1008-02", window="1000000000d")
    assert res_days.status == TelemetryStatus.OK
    assert res_days.data is not None

    res_hours = service.get_link_quality("S-1008-02", window="1000000000h")
    assert res_hours.status == TelemetryStatus.OK
    assert res_hours.data is not None


def test_ipsec_note_anomaly_reflects_secondary_tunnel_health(tmp_path: Path) -> None:
    (tmp_path / "ipsec_status").mkdir()
    # Primary is UP, secondary is DOWN
    ipsec_secondary_down = {
        "site_id": "S-1002-03",
        "peer": "Azure",
        "ike_version": "ikev2",
        "initiator": "cato",
        "primary": {"status": "up"},
        "secondary": {"status": "down", "last_error": "PEER_NOT_RESPONDING"},
        "note": "Secondary tunnel configuration requires review",
        "queried_at": "2026-08-28T17:00:00Z",
    }
    (tmp_path / "ipsec_status" / "S-1002-03.json").write_text(json.dumps(ipsec_secondary_down), encoding="utf-8")
    service = TelemetryService(telemetry_dir=tmp_path)
    res = service.get_ipsec_status("S-1002-03")
    assert res.status == TelemetryStatus.OK
    assert res.data is not None
    note_ev = next((ev for ev in res.evidence if ev.metric_key == "note"), None)
    assert note_ev is not None
    assert note_ev.is_anomaly is True

    # Both tunnels UP with no errors -> note is not anomalous
    ipsec_both_up = {
        "site_id": "S-1002-03",
        "peer": "Azure",
        "ike_version": "ikev2",
        "initiator": "cato",
        "primary": {"status": "up"},
        "secondary": {"status": "up"},
        "note": "Standard maintenance note",
        "queried_at": "2026-08-28T17:00:00Z",
    }
    (tmp_path / "ipsec_status" / "S-1002-03.json").write_text(json.dumps(ipsec_both_up), encoding="utf-8")
    res_up = service.get_ipsec_status("S-1002-03")
    assert res_up.status == TelemetryStatus.OK
    note_ev_up = next((ev for ev in res_up.evidence if ev.metric_key == "note"), None)
    assert note_ev_up is not None
    assert note_ev_up.is_anomaly is False


def test_bgp_neighbor_timer_fields_optional_and_suppressed_when_absent() -> None:
    service = TelemetryService()

    # S-1010-02 has an Idle neighbor without negotiated timers
    idle_res = service.get_bgp_status("S-1010-02")
    assert idle_res.status == TelemetryStatus.OK
    assert idle_res.data is not None
    neighbor = idle_res.data.neighbors[0]
    assert neighbor.state == "Idle"
    assert neighbor.hold_time_negotiated is None
    assert neighbor.peer_hold_time is None
    assert neighbor.peer_keepalive is None

    # Hold time evidence must be suppressed when absent (no misleading "negotiated 0s")
    assert not any(ev.metric_key == "hold_time" for ev in idle_res.evidence)

    # State evidence must be emitted and flagged as anomaly for Idle
    assert any(ev.metric_key == "state" and ev.raw_value == "Idle" and ev.is_anomaly for ev in idle_res.evidence)

    # S-1007-01 has an Established neighbor with all timers present
    est_res = service.get_bgp_status("S-1007-01")
    assert est_res.status == TelemetryStatus.OK
    assert est_res.data is not None
    est_neighbor = est_res.data.neighbors[0]
    assert est_neighbor.state == "Established"
    assert est_neighbor.hold_time_negotiated == 30
    assert any(ev.metric_key == "hold_time" and "negotiated 30s" in ev.raw_value and ev.is_anomaly for ev in est_res.evidence)



def test_link_quality_overflow_during_filtering_returns_unavailable() -> None:
    ticks = iter([0.0, 1e9])
    overflowing_clock = SimulationClock(
        anchor=datetime.max.replace(tzinfo=timezone.utc),
        clock_fn=lambda: next(ticks),
    )
    res = TelemetryService(clock=overflowing_clock).get_link_quality("S-1008-02", window="24h")
    assert res.status == TelemetryStatus.UNAVAILABLE
    assert res.data is None
    assert res.error is not None and "overflowed" in res.error


def test_bgp_hold_time_evidence_emitted_with_partial_peer_timers(tmp_path: Path) -> None:
    (tmp_path / "bgp_status").mkdir()
    bgp_data = {
        "site_id": "S-1007-01",
        "queried_at": "2026-08-28T17:00:00Z",
        "neighbors": [
            {
                "peer_ip": "10.0.0.1",
                "peer_asn": 65001,
                "cato_asn": 65002,
                "state": "Established",
                "hold_time_configured": 60,
                "keepalive_configured": 20,
                "hold_time_negotiated": 60,
                "peer_hold_time": 60,
                "routes_count": 10,
                "routes_limit": 100,
            }
        ],
    }
    (tmp_path / "bgp_status" / "S-1007-01.json").write_text(json.dumps(bgp_data), encoding="utf-8")
    res = TelemetryService(telemetry_dir=tmp_path).get_bgp_status("S-1007-01")
    assert res.status == TelemetryStatus.OK
    hold_ev = next(ev for ev in res.evidence if ev.metric_key == "hold_time")
    assert "negotiated 60s" in hold_ev.raw_value and not hold_ev.is_anomaly
    assert "missing timer negotiation" not in hold_ev.raw_value
    peer_ev = next(ev for ev in res.evidence if ev.metric_key == "peer_timers")
    assert peer_ev.raw_value == "missing peer_keepalive"
