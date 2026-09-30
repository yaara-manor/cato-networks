from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class _GuardModel(BaseModel):
    model_config = ConfigDict(frozen=True)


# declaration order is merge precedence: structural -> vendor -> contextual -> entropy
class SecretKind(StrEnum):
    PRIVATE_KEY = "PRIVATE_KEY"
    BEARER_TOKEN = "BEARER_TOKEN"
    JWT = "JWT"
    VENDOR_KEY = "VENDOR_KEY"
    KEY_VALUE = "KEY_VALUE"
    VENDOR_CONFIG = "VENDOR_CONFIG"
    CONTEXTUAL = "CONTEXTUAL"
    HIGH_ENTROPY = "HIGH_ENTROPY"


class RedactionFinding(_GuardModel):
    kind: SecretKind
    start: int
    end: int
    sha256: str


class RedactionResult(_GuardModel):
    text: str
    findings: tuple[RedactionFinding, ...]

    @property
    def was_redacted(self) -> bool:
        return bool(self.findings)
