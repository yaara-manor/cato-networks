from typing import assert_never

from agents import Intent, TriageResult
from storage import ConversationStage


def next_stage_after_triage(result: TriageResult) -> ConversationStage:
    if result.identity.scoping_question:
        return ConversationStage.RESOLUTION
    if result.scoping_question and result.decision.intent is not Intent.TELEMETRY_DIAGNOSIS:
        return ConversationStage.RESOLUTION
    match result.decision.intent:
        case Intent.ADVERSARIAL:
            return ConversationStage.RESOLUTION
        case Intent.TELEMETRY_DIAGNOSIS:
            return ConversationStage.DIAGNOSTICS
        case Intent.KB_INQUIRY | Intent.POLICY_REQUEST:
            # a named site has telemetry worth reading before answering
            return ConversationStage.DIAGNOSTICS if result.decision.site_id else ConversationStage.KNOWLEDGE_RETRIEVAL
        case _:
            assert_never(result.decision.intent)


def compose_reply(
    prefix_notices: tuple[str, ...], message: str, confirmations: tuple[str, ...], denial_reasons: tuple[str, ...]
) -> str:
    return "\n\n".join(part for part in (*prefix_notices, message, *confirmations, *denial_reasons) if part)
