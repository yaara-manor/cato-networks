# Rerank Threshold Calibration

- Date: 2026-10-01
- Reranker: `cross-encoder/ms-marco-MiniLM-L12-v2` @ `7b0235231ca2674cb8ca8f022859a6eba2b1c968`

## Decision

- Plan-rule threshold: **0.773** (answerable vs off-domain: overlapping)
- Applied `rerank_min_score`: **2.0** (safety floor, see ADR-007)
- Answerable questions refused: 1 (Q14)

## Score ranges (top-1 rerank score)

| Set | Count | Min | Max |
|---|---|---|---|
| answerable | 35 | -1.651 | 8.757 |
| off-domain | 10 | -11.169 | 0.773 |
| partial-coverage | 2 | 4.241 | 4.741 |

## Latency (all 47 queries)

- p50: 1487 ms
- p95: 1867 ms

## Per-query scores

| Id | Set | Top-1 score | Top-1 slug | Latency ms |
|---|---|---|---|---|
| Q03 | answerable | 8.757 | socket-mtu-and-dtls-tunnels | 1394 |
| Q16 | answerable | 8.695 | configuring-your-account-to-support-ip-overlapping | 1375 |
| Q02 | answerable | 8.095 | socket-mtu-and-dtls-tunnels | 1361 |
| Q12 | answerable | 7.967 | cato-cloud-thresholds-and-limits | 1452 |
| Q13 | answerable | 7.934 | recommendations-for-ipsec-connections | 1461 |
| Q21 | answerable | 7.701 | what-is-socket-ha | 1437 |
| Q25 | answerable | 7.524 | understanding-acceptable-and-unacceptable-sla-for-sites | 1447 |
| Q32 | answerable | 7.430 | allowlisting-ips-signatures | 1784 |
| Q28 | answerable | 7.403 | socket-upgrade-failure-troubleshooting | 1754 |
| Q29 | answerable | 7.343 | connectivity-requirements-for-socket-upgrades | 1706 |
| Q08 | answerable | 7.298 | configuring-bfd-for-bgp-neighbors | 1653 |
| Q04 | answerable | 7.188 | configuring-bgp-neighbors-for-an-ipsec-connection | 1450 |
| Q31 | answerable | 7.127 | certificate-warnings-with-blocked-https-websites | 1719 |
| Q34 | answerable | 7.115 | how-cato-mfa-and-expiration-mechanism-works | 1434 |
| Q24 | answerable | 6.870 | monitoring-your-site-with-connectivity-events | 1841 |
| Q22 | answerable | 6.559 | manually-activate-socket-ha-failover | 1534 |
| Q17 | answerable | 6.448 | understanding-cato-networking-in-china | 1326 |
| Q06 | answerable | 6.267 | working-with-bgp-summary-routes | 1051 |
| Q33 | answerable | 6.031 | how-to-configure-a-network-rule-to-egress-traffic | 1810 |
| Q11 | answerable | 5.725 | xops-network-playbook-ipsec-phase2-failure | 1503 |
| Q26 | answerable | 5.680 | last-mile-monitoring-probes-and-connectivity | 1698 |
| Q01 | answerable | 5.566 | socket-mtu-and-dtls-tunnels | 1755 |
| Q20 | answerable | 5.279 | what-is-socket-ha | 1546 |
| Q07 | answerable | 5.091 | cato-socket-vs-ipsec-sites-and-tunnels | 1563 |
| Q30 | answerable | 4.905 | tls-inspection-troubleshooting | 1608 |
| Q35 | answerable | 4.573 | xops-network-playbook-scim-provisioning-failed | 1508 |
| Q19 | answerable | 4.335 | what-is-socket-ha | 1215 |
| Q18 | answerable | 4.225 | performance-troubleshooting-socket-behind-a-third-party-firewall | 1215 |
| Q09 | answerable | 3.905 | xops-network-playbooks-1 | 1392 |
| Q10 | answerable | 3.870 | xops-network-playbook-ipsec-phase2-failure | 1487 |
| Q27 | answerable | 3.715 | xops-network-playbook-link-quality-sla | 1606 |
| Q23 | answerable | 2.750 | monitoring-your-site-with-connectivity-events | 1644 |
| Q15 | answerable | 2.735 | recommendations-for-ipsec-connections | 1151 |
| Q05 | answerable | 2.007 | working-with-bgp-summary-routes | 1332 |
| Q14 | answerable | -1.651 | 2023-release-notes | 1403 |
| OOD05 | off-domain | 0.773 | working-with-cato-account-license-lifecycle-jan-2027-license | 1654 |
| OOD04 | off-domain | 0.670 | using-the-cma-to-add-sites | 1531 |
| OOD03 | off-domain | -1.048 | configuring-ha-for-aws-vsockets | 1885 |
| OOD09 | off-domain | -3.308 | creating-the-data-control-policy | 1458 |
| OOD02 | off-domain | -3.793 | servicenow-configuring-integration-with-xops-stories | 1467 |
| OOD06 | off-domain | -4.143 | welcome-to-the-cato-service | 1287 |
| OOD08 | off-domain | -4.644 | refreshing-cato-socket-hardware | 1206 |
| OOD01 | off-domain | -7.716 | integrating-custom-ioc-lists-with-containers | 1928 |
| OOD10 | off-domain | -9.281 | creating-file-control-rules-in-the-application-control-policy | 1373 |
| OOD07 | off-domain | -11.169 | best-practices-for-cato-event-logs-and-ingestion | 1611 |
| PC-ROADMAP | partial-coverage | 4.741 | using-the-roadmap-tracker | 1485 |
| SC-09-no-kb-coverage | partial-coverage | 4.241 | cato-clients | 1639 |

Partial-coverage rows are informational only (design section 4.3): they pass the gate because the KB covers part of the question, and declining the uncovered part (roadmap dates) is the agent's grounding duty, not the threshold's.
