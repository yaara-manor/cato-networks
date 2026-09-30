from pydantic import BaseModel, ConfigDict


class PolicyDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    title: str
    file_path: str
    body: str

    def citation_tag(self) -> str:
        return f"[policy:{self.policy_id}]"
