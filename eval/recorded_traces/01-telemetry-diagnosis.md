# BGP route-limit exhaustion at a branch site (SC-01)

- Kind: telemetry-driven diagnosis
- Conversation: `b6d1c067-c81f-485a-ba7c-05711d69e624` (replay it in the reviewer app; full structured trace in `01-telemetry-diagnosis.json`)
- Caller: tal.kowalski@atlas-eng.com
- Recorded: 2026-10-04T19:17:04+00:00 by `python -m eval.record_traces`

## Turn 1

**Customer**

> Since we swapped our core switch to a Nexus 9k the BGP session to the Socket at our Austin office flaps every few minutes with hold timer expired. Our timers are 10/30.

**Agent**

> I’m sorry this has been disrupting the Austin office, especially since the core switch replacement. The strongest finding is that the BGP neighbor is at its route capacity: `routes_count 1024/1024` [telemetry:get_bgp_status]. The playbook’s remedy is to reduce the routes advertised to Cato by summarizing internal prefixes and filtering out infrastructure, transit, or other non-WAN-relevant prefixes; if the advertised routes still exceed the limit after those steps, contact Support for further assistance [kb:xops-network-playbook-bgp-prefix-exhaustion#step-2---reduce-the-number-of-advertised-routes].
>
> The session is currently reported as `state Established` [telemetry:get_bgp_status], but its recorded error and flap count are `last_error Hold Timer Expired` and `flaps_24h 11` [telemetry:get_bgp_status]. Your stated timer values of 10/30 differ from the recorded values: `hold_time negotiated 30s (configured 60s, keepalive 20s, peer 30s/10s)` [telemetry:get_bgp_status]. This evidence does not establish whether the Nexus replacement or the timer configuration caused the expirations. I’ve created a P3 support case to track the route-capacity finding and investigate the repeated resets. Please review the advertised prefixes and consider aggregation or filtering; avoid changing timers based on this evidence alone.
>
> I opened ticket TCK-20264262 for you.

**Trace**

| # | Agent | Status | Latency | Tokens | Tool calls |
|---|---|---|---|---|---|
| 1 | TRIAGE | OK | 12094 ms | 1955+259 | `get_ticket_history` (OK) |
| 2 | DIAGNOSTICS | OK | 6823 ms | 10088+388 | `list_sites` (OK), `get_site_status` (OK), `get_link_quality` (OK), `get_events` (OK), `get_bgp_status` (OK) |
| 3 | KNOWLEDGE | OK | 9581 ms | 10232+379 | `search_knowledge_base` (LOW_CONFIDENCE_REFUSAL), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `expand_article_sections` (CONFIDENT) |
| 4 | RESOLUTION | OK | 15825 ms | 37843+1882 | - |

## Turn 2

**Customer**

> OK we set 30/90 on the Nexus. Better, but it still dropped once in the last hour.

**Agent**

> Thanks for the update—I’m sorry the Austin session is still dropping after the Nexus change.
>
> The diagnostics snapshot still shows `routes_count 1024/1024`, `last_error Hold Timer Expired`, and `flaps_24h 11` [telemetry:get_bgp_status]. The BGP playbook identifies the route limit by checking whether `routes_count` has reached 1024 [kb:xops-network-playbook-bgp-prefix-exhaustion#check-bgp-status]. Its recommended next step is to reduce the routes advertised to Cato by summarizing internal prefixes and filtering infrastructure, transit, or other non-WAN-relevant prefixes; if the advertised routes remain above the limit after that, contact Support for further help [kb:xops-network-playbook-bgp-prefix-exhaustion#step-2---reduce-the-number-of-advertised-routes].
>
> Your reported Nexus timers are 30/90, while the snapshot records `hold_time negotiated 30s (configured 60s, keepalive 20s, peer 30s/10s)` [telemetry:get_bgp_status]. So this snapshot does not reflect the timer values you reported; it does not establish why, or whether the timer change caused the remaining drop. The saturated route count is the clearest finding to address first. The existing support case remains the place to track the investigation.

**Trace**

| # | Agent | Status | Latency | Tokens | Tool calls |
|---|---|---|---|---|---|
| 5 | TRIAGE | OK | 4288 ms | 3037+192 | `get_ticket_history` (OK) |
| 6 | DIAGNOSTICS | OK | 18207 ms | 23610+1014 | `list_sites` (OK), `get_site_status` (OK), `get_link_quality` (OK), `get_events` (OK), `get_bgp_status` (OK) |
| 7 | KNOWLEDGE | OK | 9545 ms | 10536+422 | `search_knowledge_base` (LOW_CONFIDENCE_REFUSAL), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `expand_article_sections` (CONFIDENT) |
| 8 | RESOLUTION | OK | 17817 ms | 38874+2048 | - |

## Turn 3

**Customer**

> We do advertise a lot of prefixes, around 1,100. Is that a problem?

**Agent**

> Yes. The Austin neighbor is already at its route limit: `routes_count 1024/1024` [telemetry:get_bgp_status]. The playbook covers identifying and resolving a reached BGP route limit [kb:xops-network-playbooks-1#xops-network-playbook---bgp-prefix-exhaustionhttpsknowledgecatonetworkscomdocsxops-network-playbook-bgp-prefix-exhaustionmd], and specifies 1024 as the limit [kb:xops-network-playbook-bgp-prefix-exhaustion#check-bgp-status]. Your estimate of around 1,100 advertised prefixes is therefore above that limit.
>
> The recommended fix is to reduce the routes advertised to Cato by summarizing internal prefixes and filtering infrastructure, transit, or other non-WAN-relevant prefixes. If the advertised count still exceeds the limit after those changes, contact Support for further assistance [kb:xops-network-playbook-bgp-prefix-exhaustion#step-2---reduce-the-number-of-advertised-routes]. The existing case remains open to track the investigation.

**Trace**

| # | Agent | Status | Latency | Tokens | Tool calls |
|---|---|---|---|---|---|
| 9 | TRIAGE | OK | 7029 ms | 4906+579 | `get_ticket_history` (OK) |
| 10 | DIAGNOSTICS | OK | 6771 ms | 7577+386 | `list_sites` (OK), `get_bgp_status` (OK) |
| 11 | KNOWLEDGE | OK | 6966 ms | 8675+181 | `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `search_knowledge_base` (CONFIDENT), `expand_article_sections` (CONFIDENT) |
| 12 | RESOLUTION | OK | 13934 ms | 23648+1046 | - |
