from collections.abc import Callable
import concurrent.futures
import csv
from datetime import datetime
from functools import lru_cache
import io
import math
from pathlib import Path
import re
from re import Pattern

from pydantic import AwareDatetime, BaseModel

from core.clock import SimulationClock
from core.config import settings
from tools.models import (
    BgpStatusPayload,
    ClientDiagnosticsPayload,
    CmaEvent,
    EventsPayload,
    IpsecStatusPayload,
    LinkMetricsSummary,
    LinkQualityPayload,
    SiteListPayload,
    SiteRecord,
    TelemetryEvidence,
    TelemetryPayload,
    TelemetryStatus,
    TelemetryToolResult,
)

ACCOUNT_ID_PATTERN: Pattern[str] = re.compile(r"^ACC-\d{4}$")
SITE_ID_PATTERN: Pattern[str] = re.compile(r"^S-\d{4}-\d{2}$")
USER_EMAIL_PATTERN: Pattern[str] = re.compile(r"^[^/\\@\s]+@[^/\\@\s]+\.[^/\\@\s]+$")
WINDOW_PATTERN: Pattern[str] = re.compile(r"^(\d+(?:\.\d+)?)\s*([hd])$", re.IGNORECASE)
MAX_WINDOW_HOURS: float = 999_999_998.0 * 24.0


class _SitesFileSchema(BaseModel):
    generated_at: AwareDatetime
    sites: list[SiteRecord]


def _validate_identifier(value: str, pattern: Pattern[str], label: str) -> str | None:
    if not isinstance(value, str) or not value:
        return f"Invalid {label}: value must be a non-empty string."
    if "/" in value or "\\" in value or ".." in value:
        return f"Invalid {label} '{value}': path traversal characters are not allowed."
    if not pattern.match(value):
        return f"Invalid {label} '{value}': does not match expected format."
    return None


def _resolve_safe_path(base_dir: Path, relative_path: str) -> Path | None:
    try:
        base_resolved = base_dir.resolve()
        candidate = (base_resolved / relative_path).resolve()
    except OSError:
        return None
    if not candidate.is_relative_to(base_resolved):
        return None
    return candidate


def _parse_window_hours(window: str) -> float | None:
    if not isinstance(window, str):
        return None
    cleaned = window.strip().lower()
    if not cleaned:
        return None
    if cleaned == "all":
        return float("inf")
    match = WINDOW_PATTERN.match(cleaned)
    if not match:
        return None
    try:
        amount = float(match.group(1))
    except (ValueError, OverflowError):
        return float("inf")
    if amount <= 0:
        return None
    unit = match.group(2).lower()
    try:
        hours = amount if unit == "h" else amount * 24.0
    except OverflowError:
        return float("inf")
    if hours >= MAX_WINDOW_HOURS or math.isinf(hours):
        return float("inf")
    return hours


@lru_cache(maxsize=256)
def _read_text_cached(resolved_path: str, mtime_ns: int) -> str:
    _ = mtime_ns
    return Path(resolved_path).read_text(encoding="utf-8")


def _ev(
    tool_name: str,
    timestamp: AwareDatetime,
    metric_key: str,
    raw_value: str,
    is_anomaly: bool = False,
) -> TelemetryEvidence:
    return TelemetryEvidence(
        tool_name=tool_name,
        metric_key=metric_key,
        raw_value=raw_value,
        timestamp=timestamp,
        is_anomaly=is_anomaly,
    )


class TelemetryService:
    def __init__(
        self,
        telemetry_dir: Path = settings.repo_root / "data" / "telemetry",
        clock: SimulationClock | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.telemetry_dir: Path = telemetry_dir
        self.clock: SimulationClock = clock or SimulationClock.frozen()
        self.timeout_seconds: float = timeout_seconds

    def _read_file_text(self, path: Path) -> str:
        if self.timeout_seconds <= 0:
            raise TimeoutError(f"Telemetry read timed out (timeout_seconds={self.timeout_seconds})")
        stat = path.stat()
        return _read_text_cached(str(path), stat.st_mtime_ns)

    def _load_with_timeout[R](
        self,
        path: Path,
        parse_fn: Callable[[str], R],
    ) -> R:
        if self.timeout_seconds <= 0:
            raise TimeoutError(f"Telemetry read timed out (timeout_seconds={self.timeout_seconds})")

        def _execute() -> R:
            text = self._read_file_text(path)
            return parse_fn(text)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_execute)
            return future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise TimeoutError(
                f"Telemetry operation timed out after {self.timeout_seconds}s"
            ) from exc
        finally:
            executor.shutdown(wait=False)

    def _load_validated[P: TelemetryPayload, R](
        self,
        tool_name: str,
        identifier: str,
        pattern: Pattern[str],
        label: str,
        relative_path: str,
        parse_fn: Callable[[str], R],
        *,
        missing_status: TelemetryStatus = TelemetryStatus.NOT_FOUND,
        extra_error: str | None = None,
    ) -> R | TelemetryToolResult[P]:
        err = _validate_identifier(identifier, pattern, label) or extra_error
        if err is not None:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.INVALID_ARGUMENT,
                error=err,
            )
        resolved = _resolve_safe_path(self.telemetry_dir, relative_path)
        if resolved is None:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.INVALID_ARGUMENT,
                error=f"Invalid path for {label} '{identifier}'.",
            )
        if not resolved.is_file():
            return TelemetryToolResult(
                tool_name=tool_name,
                status=missing_status,
                error=f"Telemetry file '{relative_path}' not found for '{identifier}'.",
            )
        try:
            parsed = self._load_with_timeout(resolved, parse_fn)
            if hasattr(parsed, "site_id") and getattr(parsed, "site_id") != identifier:
                return TelemetryToolResult(
                    tool_name=tool_name,
                    status=TelemetryStatus.UNAVAILABLE,
                    error=(
                        f"Embedded site_id '{getattr(parsed, 'site_id')}' "
                        f"does not match requested '{identifier}'."
                    ),
                )
            if hasattr(parsed, "user_email") and getattr(parsed, "user_email") != identifier:
                return TelemetryToolResult(
                    tool_name=tool_name,
                    status=TelemetryStatus.UNAVAILABLE,
                    error=(
                        f"Embedded user_email '{getattr(parsed, 'user_email')}' "
                        f"does not match requested '{identifier}'."
                    ),
                )
            return parsed
        except Exception as exc:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.UNAVAILABLE,
                error=f"Failed to read or parse '{relative_path}' for '{identifier}': {exc}",
            )

    def list_sites(self, account_id: str) -> TelemetryToolResult[SiteListPayload]:
        tool_name = "list_sites"
        loaded = self._load_validated(
            tool_name,
            account_id,
            ACCOUNT_ID_PATTERN,
            "account_id",
            "sites.json",
            _SitesFileSchema.model_validate_json,
            missing_status=TelemetryStatus.UNAVAILABLE,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        matching_sites = [s for s in loaded.sites if s.customer_id == account_id]
        if not matching_sites:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.NOT_FOUND,
                error=f"No sites found for account_id '{account_id}'.",
            )

        evidence = [
            _ev(tool_name, s.last_seen, f"{s.site_id}.status", s.status, s.status != "connected")
            for s in matching_sites
        ]
        payload = SiteListPayload(
            account_id=account_id,
            generated_at=loaded.generated_at,
            sites=matching_sites,
        )
        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )

    def get_site_status(self, site_id: str) -> TelemetryToolResult[SiteRecord]:
        tool_name = "get_site_status"
        loaded = self._load_validated(
            tool_name,
            site_id,
            SITE_ID_PATTERN,
            "site_id",
            "sites.json",
            _SitesFileSchema.model_validate_json,
            missing_status=TelemetryStatus.UNAVAILABLE,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        site = next((s for s in loaded.sites if s.site_id == site_id), None)
        if site is None:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.NOT_FOUND,
                error=f"Site '{site_id}' not found.",
            )

        is_disconnected = site.status != "connected"
        evidence: list[TelemetryEvidence] = [
            _ev(tool_name, site.last_seen, "status", site.status, is_disconnected),
            _ev(
                tool_name,
                site.last_seen,
                "last_seen",
                site.last_seen.isoformat().replace("+00:00", "Z"),
                is_disconnected,
            ),
        ]
        if site.socket_version is not None:
            evidence.append(
                _ev(tool_name, site.last_seen, "socket_version", site.socket_version)
            )
        evidence.append(
            _ev(tool_name, site.last_seen, "wan_links", ", ".join(site.wan_links))
        )
        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=site,
            evidence=evidence,
        )

    def get_link_quality(
        self, site_id: str, window: str = "24h"
    ) -> TelemetryToolResult[LinkQualityPayload]:
        tool_name = "get_link_quality"
        window_hours = _parse_window_hours(window)
        window_err = (
            None
            if window_hours is not None
            else f"Invalid window '{window}': expected e.g. '1h', '6h', '12h', '24h', '7d', or 'all'."
        )

        def _parse_csv(
            raw_text: str,
        ) -> list[tuple[datetime, str, float, float, float, float, float]]:
            reader = csv.DictReader(io.StringIO(raw_text))
            required_cols = {
                "ts",
                "link",
                "packet_loss_pct",
                "latency_ms",
                "jitter_ms",
                "upstream_mbps",
                "downstream_mbps",
            }
            if reader.fieldnames is None or not required_cols.issubset(set(reader.fieldnames)):
                raise ValueError("Missing required CSV columns")

            rows: list[tuple[datetime, str, float, float, float, float, float]] = []
            for row in reader:
                if any(
                    row.get(col) is None or row.get(col, "").strip() == "" for col in required_cols
                ):
                    raise ValueError("Empty or missing CSV field in row")
                rows.append(
                    (
                        datetime.fromisoformat(row["ts"].strip()),
                        row["link"].strip(),
                        float(row["packet_loss_pct"]),
                        float(row["latency_ms"]),
                        float(row["jitter_ms"]),
                        float(row["upstream_mbps"]),
                        float(row["downstream_mbps"]),
                    )
                )
            if not rows:
                raise ValueError("CSV contains no data rows")
            return rows

        loaded = self._load_validated(
            tool_name,
            site_id,
            SITE_ID_PATTERN,
            "site_id",
            f"link_quality/{site_id}.csv",
            _parse_csv,
            extra_error=window_err,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        assert window_hours is not None
        filtered_rows: list[tuple[datetime, str, float, float, float, float, float]] = []
        for r in loaded:
            if math.isinf(window_hours):
                filtered_rows.append(r)
                continue
            try:
                in_window = self.clock.is_within(r[0], window_hours)
            except OverflowError:
                return TelemetryToolResult(
                    tool_name=tool_name,
                    status=TelemetryStatus.UNAVAILABLE,
                    error=f"Window '{window}' overflowed while filtering sample at {r[0].isoformat()}.",
                )
            if in_window:
                filtered_rows.append(r)

        grouped: dict[str, list[tuple[datetime, str, float, float, float, float, float]]] = {}
        for r in filtered_rows:
            grouped.setdefault(r[1], []).append(r)

        summaries: list[LinkMetricsSummary] = []
        evidence: list[TelemetryEvidence] = []

        for link_name, rows in grouped.items():
            rows_sorted = sorted(rows, key=lambda item: item[0])
            count = len(rows_sorted)
            losses = [item[2] for item in rows_sorted]
            latencies = [item[3] for item in rows_sorted]
            jitters = [item[4] for item in rows_sorted]
            ups = [item[5] for item in rows_sorted]
            downs = [item[6] for item in rows_sorted]

            summary = LinkMetricsSummary(
                link=link_name,
                sample_count=count,
                window_start=rows_sorted[0][0],
                window_end=rows_sorted[-1][0],
                avg_packet_loss_pct=round(sum(losses) / count, 2),
                max_packet_loss_pct=max(losses),
                latest_packet_loss_pct=losses[-1],
                avg_latency_ms=round(sum(latencies) / count, 2),
                max_latency_ms=max(latencies),
                avg_jitter_ms=round(sum(jitters) / count, 2),
                max_jitter_ms=max(jitters),
                avg_upstream_mbps=round(sum(ups) / count, 2),
                avg_downstream_mbps=round(sum(downs) / count, 2),
                down_intervals=sum(1 for loss_val in losses if loss_val >= 100.0),
            )
            summaries.append(summary)

            evidence.append(
                _ev(
                    tool_name,
                    summary.window_end,
                    f"{link_name}.packet_loss_pct",
                    (
                        f"avg={summary.avg_packet_loss_pct}%, "
                        f"max={summary.max_packet_loss_pct}%, "
                        f"latest={summary.latest_packet_loss_pct}% "
                        f"(down_intervals={summary.down_intervals})"
                    ),
                    (
                        summary.max_packet_loss_pct >= 2.0
                        or summary.latest_packet_loss_pct >= 100.0
                        or summary.down_intervals > 0
                    ),
                )
            )
            evidence.append(
                _ev(
                    tool_name,
                    summary.window_end,
                    f"{link_name}.jitter_ms",
                    f"avg={summary.avg_jitter_ms}ms, max={summary.max_jitter_ms}ms",
                    summary.max_jitter_ms >= 30.0,
                )
            )

        payload = LinkQualityPayload(
            site_id=site_id,
            window=window,
            links=summaries,
        )
        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )

    def get_events(
        self,
        site_id: str,
        event_type: str | None = None,
        window: str = "24h",
    ) -> TelemetryToolResult[EventsPayload]:
        tool_name = "get_events"
        window_err = (
            None
            if _parse_window_hours(window) is not None
            else f"Invalid window '{window}': expected e.g. '1h', '6h', '12h', '24h', '7d', or 'all'."
        )

        def _parse_jsonl(raw_text: str) -> list[CmaEvent]:
            events: list[CmaEvent] = []
            for line in raw_text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                ev = CmaEvent.model_validate_json(stripped)
                if ev.site_id != site_id:
                    raise ValueError(
                        f"Embedded site_id '{ev.site_id}' does not match requested '{site_id}'."
                    )
                events.append(ev)
            return events

        loaded = self._load_validated(
            tool_name,
            site_id,
            SITE_ID_PATTERN,
            "site_id",
            f"events/{site_id}.jsonl",
            _parse_jsonl,
            extra_error=window_err,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        events = loaded
        if any(ev.site_id != site_id for ev in events):
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.UNAVAILABLE,
                error=f"Event site_id mismatch for '{site_id}'.",
            )

        # ponytail: each events/<site_id>.jsonl has <20 rows; return all matching events so 4-day-old alerts like S-1008-03 are never dropped by an LLM passing window="24h"
        if event_type is not None and event_type.strip().lower() not in {"", "all"}:
            needle = event_type.strip().lower()
            events = [
                ev
                for ev in events
                if needle in ev.event_type.lower() or needle in ev.sub_type.lower()
            ]

        evidence: list[TelemetryEvidence] = []
        for ev in events:
            raw_val = ev.message
            if ev.verdict is not None or ev.dst is not None:
                raw_val += f" [src={ev.src}, dst={ev.dst}, verdict={ev.verdict}]"
            if ev.link is not None:
                raw_val += f" [link={ev.link}]"
            is_anom = (
                ev.action.lower() in {"alert", "disconnected", "failed", "block"}
                or "not ready" in ev.sub_type.lower()
            )
            evidence.append(
                _ev(
                    tool_name,
                    ev.ts,
                    f"{ev.event_type}/{ev.sub_type} ({ev.action})",
                    raw_val,
                    is_anom,
                )
            )

        payload = EventsPayload(
            site_id=site_id,
            event_type_filter=event_type,
            window=window,
            events=events,
        )
        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )

    def get_bgp_status(self, site_id: str) -> TelemetryToolResult[BgpStatusPayload]:
        tool_name = "get_bgp_status"
        loaded = self._load_validated(
            tool_name,
            site_id,
            SITE_ID_PATTERN,
            "site_id",
            f"bgp_status/{site_id}.json",
            BgpStatusPayload.model_validate_json,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        payload = loaded
        if payload.site_id != site_id:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.UNAVAILABLE,
                error=f"Mismatched site_id in payload: expected '{site_id}', got '{payload.site_id}'.",
            )

        evidence: list[TelemetryEvidence] = []
        for n in payload.neighbors:
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "state",
                    n.state,
                    n.state != "Established",
                )
            )
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "routes_count",
                    f"{n.routes_count}/{n.routes_limit}",
                    n.routes_limit > 0 and n.routes_count >= n.routes_limit,
                )
            )
            if n.last_error:
                evidence.append(
                    _ev(tool_name, payload.queried_at, "last_error", n.last_error, True)
                )
            if n.flaps_24h > 0:
                evidence.append(
                    _ev(tool_name, payload.queried_at, "flaps_24h", str(n.flaps_24h), True)
                )
            if n.hold_time_negotiated is not None:
                peer_timers = (
                    f", peer {n.peer_hold_time}s/{n.peer_keepalive}s"
                    if n.peer_hold_time is not None and n.peer_keepalive is not None
                    else ""
                )
                evidence.append(
                    _ev(
                        tool_name,
                        payload.queried_at,
                        "hold_time",
                        (
                            f"negotiated {n.hold_time_negotiated}s "
                            f"(configured {n.hold_time_configured}s, "
                            f"keepalive {n.keepalive_configured}s{peer_timers})"
                        ),
                        n.hold_time_negotiated != n.hold_time_configured,
                    )
                )
                missing_peer = [
                    name
                    for name, value in (
                        ("peer_hold_time", n.peer_hold_time),
                        ("peer_keepalive", n.peer_keepalive),
                    )
                    if value is None
                ]
                if missing_peer:
                    evidence.append(
                        _ev(
                            tool_name,
                            payload.queried_at,
                            "peer_timers",
                            f"missing {', '.join(missing_peer)}",
                            False,
                        )
                    )
            elif n.state == "Established":
                evidence.append(
                    _ev(
                        tool_name,
                        payload.queried_at,
                        "hold_time",
                        (
                            f"missing timer negotiation (configured {n.hold_time_configured}s, "
                            f"keepalive {n.keepalive_configured}s)"
                        ),
                        True,
                    )
                )
            if n.static_ranges_overriding:
                evidence.append(
                    _ev(
                        tool_name,
                        payload.queried_at,
                        "static_ranges_overriding",
                        ", ".join(n.static_ranges_overriding),
                        True,
                    )
                )

        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )

    def get_ipsec_status(self, site_id: str) -> TelemetryToolResult[IpsecStatusPayload]:
        tool_name = "get_ipsec_status"
        loaded = self._load_validated(
            tool_name,
            site_id,
            SITE_ID_PATTERN,
            "site_id",
            f"ipsec_status/{site_id}.json",
            IpsecStatusPayload.model_validate_json,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        payload = loaded
        if payload.site_id != site_id:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.UNAVAILABLE,
                error=f"Mismatched site_id in payload: expected '{site_id}', got '{payload.site_id}'.",
            )

        primary_unhealthy = (
            payload.primary.status != "up" or payload.primary.last_error is not None
        )
        secondary_unhealthy = (
            payload.secondary is not None
            and (payload.secondary.status != "up" or payload.secondary.last_error is not None)
        )
        tunnel_unhealthy = primary_unhealthy or secondary_unhealthy

        evidence: list[TelemetryEvidence] = [
            _ev(
                tool_name,
                payload.queried_at,
                "primary.status",
                f"{payload.primary.status}"
                + (f" ({payload.primary.last_error})" if payload.primary.last_error else ""),
                primary_unhealthy,
            )
        ]
        if payload.secondary:
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "secondary.status",
                    f"{payload.secondary.status}"
                    + (
                        f" ({payload.secondary.last_error})"
                        if payload.secondary.last_error
                        else ""
                    ),
                    secondary_unhealthy,
                )
            )
        if payload.init_message_parameters and payload.peer_reported_parameters_from_pcap:
            cato_enc = payload.init_message_parameters.encryption
            peer_enc = payload.peer_reported_parameters_from_pcap.child_sa_encryption
            peer_dh = payload.peer_reported_parameters_from_pcap.child_sa_dh_group
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "cipher_proposal",
                    f"Cato configured {cato_enc} vs peer PCAP {peer_enc} (DH group {peer_dh})",
                    cato_enc != peer_enc,
                )
            )
        if payload.psk_last_changed:
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "psk_last_changed",
                    payload.psk_last_changed.isoformat().replace("+00:00", "Z"),
                )
            )
        if payload.note:
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "note",
                    payload.note,
                    tunnel_unhealthy,
                )
            )

        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )

    def get_client_diagnostics(
        self, user_email: str
    ) -> TelemetryToolResult[ClientDiagnosticsPayload]:
        tool_name = "get_client_diagnostics"
        loaded = self._load_validated(
            tool_name,
            user_email,
            USER_EMAIL_PATTERN,
            "user_email",
            f"clients/{user_email}.json",
            ClientDiagnosticsPayload.model_validate_json,
        )
        if isinstance(loaded, TelemetryToolResult):
            return loaded

        payload = loaded
        if payload.user_email != user_email:
            return TelemetryToolResult(
                tool_name=tool_name,
                status=TelemetryStatus.UNAVAILABLE,
                error=f"Mismatched user_email in payload: expected '{user_email}', got '{payload.user_email}'.",
            )

        evidence: list[TelemetryEvidence] = []
        if payload.last_error:
            evidence.append(
                _ev(tool_name, payload.queried_at, "last_error", payload.last_error, True)
            )
        evidence.append(
            _ev(
                tool_name,
                payload.queried_at,
                "captive_portal_detected",
                str(payload.network.captive_portal_detected).lower(),
                payload.network.captive_portal_detected,
            )
        )
        evidence.append(
            _ev(
                tool_name,
                payload.queried_at,
                "udp_443_reachable",
                str(payload.network.udp_443_reachable).lower(),
                not payload.network.udp_443_reachable,
            )
        )
        evidence.append(
            _ev(
                tool_name,
                payload.queried_at,
                "tcp_443_reachable",
                str(payload.network.tcp_443_reachable).lower(),
                not payload.network.tcp_443_reachable,
            )
        )
        if payload.network.ssid:
            evidence.append(
                _ev(
                    tool_name,
                    payload.queried_at,
                    "ssid",
                    payload.network.ssid,
                )
            )

        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )
