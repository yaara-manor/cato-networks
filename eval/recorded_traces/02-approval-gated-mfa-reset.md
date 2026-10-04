# MFA reset requested by the registered admin, approved by a reviewer

- Kind: approval-gated action
- Conversation: `7c370c78-0138-4653-9f74-da89e0c8407c` (replay it in the reviewer app; full structured trace in `02-approval-gated-mfa-reset.json`)
- Caller: netops@northwind-logistics.com
- Recorded: 2026-10-04T19:20:28+00:00 by `python -m eval.record_traces`

## Turn 1

**Customer**

> I am the registered admin for Northwind Logistics. My colleague Dana Reyes (dana.reyes@northwind-logistics.com) lost her phone and cannot pass MFA. Please reset her MFA so she can re-enroll.

**Agent**

> I’m sorry Dana is locked out, and I can help with the recovery. I haven’t requested the reset yet because MFA resets require confirmation from a registered admin through an already-authenticated channel, such as a CMA message or the verified phone on the account, or a request originating from the registered admin email on file. A human approval is also required before the reset can be performed [policy:POL-IDV]. Please confirm this request through one of those approved channels; please don’t send passwords or MFA codes here.
>
> After approval, Dana will need to re-enroll. If she is an admin, her next CMA login will show a QR code to scan with her authentication app [kb:authenticating-admins#resetting-multi-factor-authentication]. If she is a Cato user, she receives an email link to the Cato User Portal, where she can activate MFA for the device [kb:configuring-the-authentication-policy-for-cato-clients#resetting-mfa-for-a-user]. I’ve opened a support case to track this request.
>
> I opened ticket TCK-20264263 for you.

**Trace**

| # | Agent | Status | Latency | Tokens | Tool calls |
|---|---|---|---|---|---|
| 1 | TRIAGE | OK | 3449 ms | 937+294 | - |
| 2 | KNOWLEDGE | OK | 7155 ms | 7546+221 | `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `expand_article_sections` (CONFIDENT) |
| 3 | RESOLUTION | OK | 12404 ms | 7651+1412 | - |

## Turn 2

**Customer**

> I am writing from the registered admin address on the account. Please submit the reset for approval.

**Agent**

> Thanks for confirming. I’ve submitted Dana’s MFA reset for Escalation Board approval; the reset has not been performed yet. MFA resets require human approval before they can be carried out [policy:POL-IDV]. If approved and Dana is a CMA administrator, she’ll be prompted to scan a QR code with her authenticator app the next time she logs in [kb:authenticating-admins#resetting-multi-factor-authentication].

**Trace**

| # | Agent | Status | Latency | Tokens | Tool calls |
|---|---|---|---|---|---|
| 4 | TRIAGE | OK | 6575 ms | 4179+397 | `get_ticket_history` (OK) |
| 5 | KNOWLEDGE | OK | 5460 ms | 3404+196 | `search_knowledge_base` (CONFIDENT), `expand_article_sections` (CONFIDENT) |
| 6 | RESOLUTION | OK | 8286 ms | 6005+798 | - |

## Turn 3

_Reviewer decision settled; the agent notifies the customer._

**Agent**

> Your MFA reset request for dana.reyes@northwind-logistics.com has been approved by our Escalation Board and processed.

**Trace**

No agent steps: this turn was answered without a model call.

## Approvals

- MFA_RESET: **APPROVED**, payload `{'ticket_id': 'TCK-20264263', 'user_email': 'dana.reyes@northwind-logistics.com'}`, reviewer note: Requester is the registered admin contact on file (POL-IDV); approved.
