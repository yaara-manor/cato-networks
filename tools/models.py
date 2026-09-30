from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field


class TelemetryStatus(StrEnum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"


class TelemetryEvidence(BaseModel):
    tool_name: str
    metric_key: str
    raw_value: str
    timestamp: AwareDatetime
    is_anomaly: bool

    def format_citation(self) -> str:
        return f"{self.metric_key} {self.raw_value} [telemetry:{self.tool_name}]"


class SiteRecord(BaseModel):
    site_id: str
    customer_id: str
    name: str
    country: str
    connection_type: Literal["socket", "ipsec"]
    socket_model: str | None = None
    socket_version: str | None = None
    ha: bool
    wan_links: list[str]
    connected_pop: str
    status: str
    last_seen: AwareDatetime
    native_range: str


class SiteListPayload(BaseModel):
    account_id: str
    generated_at: AwareDatetime
    sites: list[SiteRecord]


class LinkMetricsSummary(BaseModel):
    link: str
    sample_count: int
    window_start: AwareDatetime
    window_end: AwareDatetime
    avg_packet_loss_pct: float
    max_packet_loss_pct: float
    latest_packet_loss_pct: float
    avg_latency_ms: float
    max_latency_ms: float
    avg_jitter_ms: float
    max_jitter_ms: float
    avg_upstream_mbps: float
    avg_downstream_mbps: float
    down_intervals: int


class LinkQualityPayload(BaseModel):
    site_id: str
    window: str
    links: list[LinkMetricsSummary]


class CmaEvent(BaseModel):
    ts: AwareDatetime
    site_id: str
    event_type: str
    sub_type: str
    action: str
    message: str
    link: str | None = None
    src: str | None = None
    dst: str | None = None
    verdict: str | None = None


class EventsPayload(BaseModel):
    site_id: str
    event_type_filter: str | None = None
    window: str
    events: list[CmaEvent]


class BgpNeighbor(BaseModel):
    peer_ip: str
    peer_asn: int
    cato_asn: int
    state: str
    uptime_seconds: int = 0
    hold_time_configured: int
    keepalive_configured: int
    hold_time_negotiated: int = 0
    peer_hold_time: int = 0
    peer_keepalive: int = 0
    routes_count: int
    routes_limit: int
    last_error: str | None = None
    flaps_24h: int = 0
    bfd: str | None = None


class BgpStatusPayload(BaseModel):
    site_id: str
    queried_at: AwareDatetime
    neighbors: list[BgpNeighbor]


class IpsecTunnelEndpoint(BaseModel):
    status: str
    last_error: str | None = None
    cato_egress_ip: str | None = None
    site_ip: str | None = None


class IkeParameters(BaseModel):
    encryption: str
    dh_group: str
    prf: str | None = None
    integrity: str


class PeerPcapParameters(BaseModel):
    child_sa_encryption: str
    child_sa_integrity: str
    child_sa_dh_group: str


class IpsecStatusPayload(BaseModel):
    site_id: str
    peer: str
    ike_version: str
    initiator: str
    primary: IpsecTunnelEndpoint
    secondary: IpsecTunnelEndpoint | None = None
    init_message_parameters: IkeParameters | None = None
    auth_message_parameters: IkeParameters | None = None
    peer_reported_parameters_from_pcap: PeerPcapParameters | None = None
    psk_last_changed: AwareDatetime | None = None
    note: str | None = None
    queried_at: AwareDatetime


class ClientNetworkInfo(BaseModel):
    ssid: str | None = None
    captive_portal_detected: bool = False
    udp_443_reachable: bool = True
    tcp_443_reachable: bool = True


class ClientSession(BaseModel):
    ts: AwareDatetime
    pop: str
    duration_min: int
    network: str


class ClientDiagnosticsPayload(BaseModel):
    user_email: str
    customer_id: str
    os: str
    client_version: str
    last_connect_attempt: AwareDatetime
    last_error: str | None = None
    network: ClientNetworkInfo
    recent_sessions: list[ClientSession] = Field(default_factory=list)
    scim_state: str | None = None
    queried_at: AwareDatetime


type TelemetryPayload = (
    SiteListPayload
    | SiteRecord
    | LinkQualityPayload
    | EventsPayload
    | BgpStatusPayload
    | IpsecStatusPayload
    | ClientDiagnosticsPayload
)


class TelemetryToolResult[T: TelemetryPayload](BaseModel):
    tool_name: str
    status: TelemetryStatus
    data: T | None = None
    evidence: list[TelemetryEvidence] = Field(default_factory=list)
    error: str | None = None
