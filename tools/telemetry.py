from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import csv
from datetime import datetime, timedelta
from functools import lru_cache
import io
from pathlib import Path
import re
from re import Pattern
import time

from pydantic import AwareDatetime, BaseModel, TypeAdapter

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

_DATETIME_ADAPTER: TypeAdapter[AwareDatetime] = TypeAdapter(AwareDatetime)


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
    amount = float(match.group(1))
    if amount <= 0:
        return None
    unit = match.group(2).lower()
    return amount if unit == "h" else amount * 24.0


@lru_cache(maxsize=256)
def _read_text_cached(resolved_path: str, mtime_ns: int) -> str:
    _ = mtime_ns
    return Path(resolved_path).read_text(encoding="utf-8")


def _load_with_timeout[R](fn: Callable[[], R], timeout_seconds: float) -> R:
    if timeout_seconds <= 0:
        raise TimeoutError(f"Telemetry read timed out (timeout_seconds={timeout_seconds})")
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn)
        try:
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"Telemetry read timed out after {timeout_seconds}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    if (time.monotonic() - started) > timeout_seconds:
        raise TimeoutError(f"Telemetry read exceeded {timeout_seconds}s")
    return result


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
        def _do_read() -> str:
            stat = path.stat()
            return _read_text_cached(str(path), stat.st_mtime_ns)

        return _load_with_timeout(_do_read, self.timeout_seconds)

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
            raw_text = self._read_file_text(resolved)
            return parse_fn(raw_text)
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
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key=f"{site.site_id}.status",
                raw_value=site.status,
                timestamp=site.last_seen,
                is_anomaly=(site.status != "connected"),
            )
            for site in matching_sites
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
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="status",
                raw_value=site.status,
                timestamp=site.last_seen,
                is_anomaly=is_disconnected,
            ),
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="last_seen",
                raw_value=site.last_seen.isoformat().replace("+00:00", "Z"),
                timestamp=site.last_seen,
                is_anomaly=is_disconnected,
            ),
        ]
        if site.socket_version is not None:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="socket_version",
                    raw_value=site.socket_version,
                    timestamp=site.last_seen,
                    is_anomaly=False,
                )
            )
        evidence.append(
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="wan_links",
                raw_value=", ".join(site.wan_links),
                timestamp=site.last_seen,
                is_anomaly=False,
            )
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
                        _DATETIME_ADAPTER.validate_python(row["ts"].strip()),
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
        now = self.clock.now()
        is_all = window.strip().lower() == "all"
        filtered_rows = [
            r
            for r in loaded
            if is_all or (timedelta(0) <= (now - r[0]) <= timedelta(hours=window_hours))
        ]

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
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key=f"{link_name}.packet_loss_pct",
                    raw_value=(
                        f"avg={summary.avg_packet_loss_pct}%, "
                        f"max={summary.max_packet_loss_pct}%, "
                        f"latest={summary.latest_packet_loss_pct}% "
                        f"(down_intervals={summary.down_intervals})"
                    ),
                    timestamp=summary.window_end,
                    is_anomaly=(
                        summary.max_packet_loss_pct >= 2.0
                        or summary.latest_packet_loss_pct >= 100.0
                        or summary.down_intervals > 0
                    ),
                )
            )
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key=f"{link_name}.jitter_ms",
                    raw_value=f"avg={summary.avg_jitter_ms}ms, max={summary.max_jitter_ms}ms",
                    timestamp=summary.window_end,
                    is_anomaly=(summary.max_jitter_ms >= 30.0),
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
            return [
                CmaEvent.model_validate_json(line.strip())
                for line in raw_text.splitlines()
                if line.strip()
            ]

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
                ev.action in {"Alert", "Disconnected", "Failed", "Block"}
                or "not ready" in ev.sub_type.lower()
            )
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key=f"{ev.event_type}/{ev.sub_type} ({ev.action})",
                    raw_value=raw_val,
                    timestamp=ev.ts,
                    is_anomaly=is_anom,
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
        evidence: list[TelemetryEvidence] = []
        for n in payload.neighbors:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="routes_count",
                    raw_value=f"{n.routes_count}/{n.routes_limit}",
                    timestamp=payload.queried_at,
                    is_anomaly=(n.routes_limit > 0 and n.routes_count >= n.routes_limit),
                )
            )
            if n.last_error:
                evidence.append(
                    TelemetryEvidence(
                        tool_name=tool_name,
                        metric_key="last_error",
                        raw_value=n.last_error,
                        timestamp=payload.queried_at,
                        is_anomaly=True,
                    )
                )
            if n.flaps_24h > 0:
                evidence.append(
                    TelemetryEvidence(
                        tool_name=tool_name,
                        metric_key="flaps_24h",
                        raw_value=str(n.flaps_24h),
                        timestamp=payload.queried_at,
                        is_anomaly=True,
                    )
                )
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="hold_time",
                    raw_value=(
                        f"negotiated {n.hold_time_negotiated}s "
                        f"(configured {n.hold_time_configured}s, "
                        f"keepalive {n.keepalive_configured}s, "
                        f"peer {n.peer_hold_time}s/{n.peer_keepalive}s)"
                    ),
                    timestamp=payload.queried_at,
                    is_anomaly=(
                        n.hold_time_negotiated > 0
                        and n.hold_time_negotiated != n.hold_time_configured
                    ),
                )
            )
            if n.static_ranges_overriding:
                evidence.append(
                    TelemetryEvidence(
                        tool_name=tool_name,
                        metric_key="static_ranges_overriding",
                        raw_value=", ".join(n.static_ranges_overriding),
                        timestamp=payload.queried_at,
                        is_anomaly=True,
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
        evidence: list[TelemetryEvidence] = [
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="primary.status",
                raw_value=f"{payload.primary.status}"
                + (f" ({payload.primary.last_error})" if payload.primary.last_error else ""),
                timestamp=payload.queried_at,
                is_anomaly=(
                    payload.primary.status != "up" or payload.primary.last_error is not None
                ),
            )
        ]
        if payload.secondary:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="secondary.status",
                    raw_value=f"{payload.secondary.status}"
                    + (
                        f" ({payload.secondary.last_error})"
                        if payload.secondary.last_error
                        else ""
                    ),
                    timestamp=payload.queried_at,
                    is_anomaly=(
                        payload.secondary.status != "up"
                        or payload.secondary.last_error is not None
                    ),
                )
            )
        if payload.init_message_parameters and payload.peer_reported_parameters_from_pcap:
            cato_enc = payload.init_message_parameters.encryption
            peer_enc = payload.peer_reported_parameters_from_pcap.child_sa_encryption
            peer_dh = payload.peer_reported_parameters_from_pcap.child_sa_dh_group
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="cipher_proposal",
                    raw_value=f"Cato configured {cato_enc} vs peer PCAP {peer_enc} (DH group {peer_dh})",
                    timestamp=payload.queried_at,
                    is_anomaly=(cato_enc != peer_enc),
                )
            )
        if payload.psk_last_changed:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="psk_last_changed",
                    raw_value=payload.psk_last_changed.isoformat().replace("+00:00", "Z"),
                    timestamp=payload.queried_at,
                    is_anomaly=False,
                )
            )
        if payload.note:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="note",
                    raw_value=payload.note,
                    timestamp=payload.queried_at,
                    is_anomaly=(payload.primary.status != "up"),
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
        evidence: list[TelemetryEvidence] = []
        if payload.last_error:
            evidence.append(
                TelemetryEvidence(
                    tool_name=tool_name,
                    metric_key="last_error",
                    raw_value=payload.last_error,
                    timestamp=payload.queried_at,
                    is_anomaly=True,
                )
            )
        evidence.append(
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="captive_portal_detected",
                raw_value=str(payload.network.captive_portal_detected).lower(),
                timestamp=payload.queried_at,
                is_anomaly=payload.network.captive_portal_detected,
            )
        )
        evidence.append(
            TelemetryEvidence(
                tool_name=tool_name,
                metric_key="reachability",
                raw_value=(
                    f"udp_443={payload.network.udp_443_reachable}, "
                    f"tcp_443={payload.network.tcp_443_reachable}"
                    + (f", ssid={payload.network.ssid}" if payload.network.ssid else "")
                ),
                timestamp=payload.queried_at,
                is_anomaly=(
                    not payload.network.udp_443_reachable
                    or not payload.network.tcp_443_reachable
                ),
            )
        )

        return TelemetryToolResult(
            tool_name=tool_name,
            status=TelemetryStatus.OK,
            data=payload,
            evidence=evidence,
        )
