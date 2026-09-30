from pydantic import AwareDatetime, BaseModel


class TelemetryEvidence(BaseModel):
    tool_name: str
    metric_key: str
    raw_value: str
    timestamp: AwareDatetime
    is_anomaly: bool
