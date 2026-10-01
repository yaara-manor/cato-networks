from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict


class PolicyDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    title: str
    file_path: str
    body: str

    def citation_tag(self) -> str:
        return f"[policy:{self.policy_id}]"


class KBSearchStatus(StrEnum):
    CONFIDENT = "CONFIDENT"
    LOW_CONFIDENCE_REFUSAL = "LOW_CONFIDENCE_REFUSAL"
    UNAVAILABLE = "UNAVAILABLE"


class RetrievedPassage(BaseModel):
    model_config = ConfigDict(frozen=True)

    passage_id: str
    slug: str
    title: str
    public_url: str
    site_updated_at: AwareDatetime | None
    heading: str
    heading_anchor: str
    body: str
    lex_rank: int | None
    vec_rank: int | None
    rrf_score: float
    rerank_score: float

    def citation_tag(self) -> str:
        return f"[kb:{self.slug}#{self.heading_anchor}]"


class KBSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: KBSearchStatus
    query: str
    passages: list[RetrievedPassage] = []
    candidates: list[RetrievedPassage] = []
    snapshot_date: AwareDatetime | None
    error: str | None = None
