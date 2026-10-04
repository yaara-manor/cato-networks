# Retrieval quality on the 35 benchmark questions

- Generated: 2026-10-03T19:25:49+00:00 by `python -m eval.retrieval_metrics`
- Questions scored: 28 of 35. Not scored (no passage graded as answering them): Q05, Q07, Q09, Q14, Q20, Q27, Q32
- Ranking measured: `RetrievalService.search_kb(question text, top_k=10)` (hybrid fusion, then the cross-encoder reranker). It is the retrieval stage alone, not the agent's own LLM-written queries.

## How the gold answers were obtained

The brief keeps the answer keys with the reviewers, so these numbers rest on our own labels:

- Gold articles come from `experiments/cache/judgments.json`: an **LLM judge** graded passages 0, 1 or 2 per question. A gold article is one with at least one passage graded 2.
- Only passages that the experiments' retrieval variants surfaced were graded (a pool, about 34 per question), so a relevant article that no variant surfaced is missing from the gold set. Unjudged articles count as non-relevant.
- The judge is not a human, so the figures measure agreement with it, not with the reviewers' keys.
- Recall and MRR are per **article**: a hit is any passage of a gold article.
- The judge is generous: 2.2 gold articles per question on average, against the one or two the brief describes. That makes recall conservative; MRR (first relevant article) is the steadier figure.

## Results

| Metric | Value |
|---|---|
| Recall@1 | 0.54 |
| Recall@3 | 0.70 |
| Recall@5 | 0.75 |
| MRR | 0.91 |

## Failure analysis

Questions whose gold articles are not all in the top 5: 13 of 28.

### Q10

- Question: An IPsec IKEv2 site logs NO_PROPOSAL_CHOSEN. What does it mean and how do you find exactly which parameters are being proposed?
- Gold: ipsec-site-connectivity-troubleshooting
- Gold found in the top 10: none
- Top 3 returned: xops-network-playbook-ipsec-phase2-failure (3.9), xops-network-playbook-ipsec-phase2-failure (2.1), configuring-ipsec-ikev2-sites (-1.4)

### Q12

- Question: Which IPsec encryption algorithms does Cato recommend for sites with 100 Mbps or more, and why?
- Gold: cato-cloud-thresholds-and-limits, configuring-ipsec-ikev2-sites, product-update-february-6th-2023, recommendations-for-ipsec-connections
- Gold found in the top 10: cato-cloud-thresholds-and-limits, recommendations-for-ipsec-connections, configuring-ipsec-ikev2-sites
- Top 3 returned: cato-cloud-thresholds-and-limits (8.0), recommendations-for-ipsec-connections (7.1), configuring-ipsec-ikev1-sites (6.3)

### Q13

- Question: Why does Cato recommend selecting 'Initiate connection by Cato' for IKEv2 sites?
- Gold: cato-ipsec-guide-ikev1-vs-ikev2, configuring-sites-with-ipsec-connections, recommendations-for-ipsec-connections
- Gold found in the top 10: recommendations-for-ipsec-connections, configuring-sites-with-ipsec-connections
- Top 3 returned: recommendations-for-ipsec-connections (7.9), configuring-sites-with-ipsec-connections (6.7), selecting-the-connection-type-for-a-site (6.6)

### Q17

- Question: Which alternate UDP port can DTLS tunnels use, when is it recommended, and what are the version prerequisites?
- Gold: setting-a-different-port-to-connect-to-the-cato-pop, using-an-alternate-udp-port-for-socket-and-client-dtls-traffic
- Gold found in the top 10: using-an-alternate-udp-port-for-socket-and-client-dtls-traffic, setting-a-different-port-to-connect-to-the-cato-pop
- Top 3 returned: understanding-cato-networking-in-china (6.4), using-an-alternate-udp-port-for-socket-and-client-dtls-traffic (5.6), using-an-alternate-udp-port-for-socket-and-client-dtls-traffic (3.3)

### Q18

- Question: Why might throughput drop for a Socket placed behind a third-party firewall, and what is the recommended fix?
- Gold: cato-clients, packet-loss-mitigation-for-multi-tunnel-links, performance-troubleshooting-socket-behind-a-third-party-firewall, troubleshooting-scenarios-for-issues-with-the-cato-client
- Gold found in the top 10: performance-troubleshooting-socket-behind-a-third-party-firewall
- Top 3 returned: performance-troubleshooting-socket-behind-a-third-party-firewall (4.2), cato-sockets (3.8), what-is-the-socket-next-gen-lan-firewall (2.5)

### Q19

- Question: How does the secondary Socket decide to take over in a Socket HA pair, and what does it do right after taking over?
- Gold: managing-sockets, understanding-cato-s-managed-socket-upgrade-service, what-is-socket-ha
- Gold found in the top 10: what-is-socket-ha, understanding-cato-s-managed-socket-upgrade-service
- Top 3 returned: what-is-socket-ha (4.3), what-is-socket-ha (3.9), what-is-socket-ha (3.2)

### Q22

- Question: What are the prerequisites for triggering a manual HA failover from CMA, and what status is expected about two minutes later?
- Gold: socket-site-tunnel-connectivity-troubleshooting
- Gold found in the top 10: none
- Top 3 returned: manually-activate-socket-ha-failover (6.6), manually-activate-socket-ha-failover (4.1), manually-activate-socket-ha-failover (2.2)

### Q23

- Question: Which conditions generate an 'HA Not Ready' connectivity event, and when is 'HA Ready' generated afterwards?
- Gold: configuring-ha-for-aws-vsockets, configuring-ha-for-azure-vsockets, monitoring-your-site-with-connectivity-events
- Gold found in the top 10: monitoring-your-site-with-connectivity-events, configuring-ha-for-aws-vsockets
- Top 3 returned: monitoring-your-site-with-connectivity-events (2.8), monitoring-your-site-with-connectivity-events (2.6), xops-network-playbook-ha-status-is-not-ready (2.3)

### Q25

- Question: When all active links have unacceptable SLA, how does the Socket evaluate moving to another PoP, and how long does the evaluation take?
- Gold: cato-socket-link-sla-architecture, configuring-the-connection-sla-settings-for-active-passive-socket-sites, routing-traffic-to-an-off-cloud-link, understanding-acceptable-and-unacceptable-sla-for-sites
- Gold found in the top 10: understanding-acceptable-and-unacceptable-sla-for-sites, configuring-the-connection-sla-settings-for-active-passive-socket-sites
- Top 3 returned: understanding-acceptable-and-unacceptable-sla-for-sites (7.5), understanding-acceptable-and-unacceptable-sla-for-sites (5.9), configuring-the-connection-sla-settings-for-active-passive-socket-sites (5.5)

### Q28

- Question: After a Socket upgrade the site is down and events show 'No open tunnel after grace time'. How long is the grace period, and what must be done before rebooting the Socket?
- Gold: socket-ha-status-troubleshooting, socket-upgrade-failure-troubleshooting, xops-network-playbook-socket-offline-after-upgrade
- Gold found in the top 10: socket-upgrade-failure-troubleshooting, xops-network-playbook-socket-offline-after-upgrade
- Top 3 returned: socket-upgrade-failure-troubleshooting (7.4), xops-network-playbook-socket-offline-after-upgrade (7.1), socket-upgrade-failure-troubleshooting (2.1)

### Q30

- Question: A pinned banking app breaks with TLS inspection on. What does Cato recommend, and which operating systems are bypassed from TLS inspection automatically?
- Gold: best-practices-for-tls-inspection, configuring-tls-inspection-policy-for-the-account, dlp-troubleshooting, tls-inspection-troubleshooting, using-the-tls-inspection-configuration-wizard
- Gold found in the top 10: tls-inspection-troubleshooting, configuring-tls-inspection-policy-for-the-account, using-the-tls-inspection-configuration-wizard, best-practices-for-tls-inspection
- Top 3 returned: tls-inspection-troubleshooting (4.9), tls-inspection-troubleshooting (4.6), configuring-tls-inspection-policy-for-the-account (4.2)

### Q31

- Question: Users see certificate warnings when opening blocked HTTPS sites even though TLS inspection is disabled. Why, and what fixes it?
- Gold: best-practices-for-tls-inspection, certificate-warnings-with-blocked-https-websites, installing-the-root-certificate-for-tls-inspection, tls-inspection-troubleshooting, understanding-tls-errors
- Gold found in the top 10: certificate-warnings-with-blocked-https-websites, tls-inspection-troubleshooting, installing-the-root-certificate-for-tls-inspection
- Top 3 returned: certificate-warnings-with-blocked-https-websites (7.1), accessing-an-untrusted-website-is-blocked-even-though-tls-inspection-is-disabled (5.8), tls-inspection-troubleshooting (5.5)

### Q34

- Question: How long is a Cato MFA token valid, and when does Cato ask for the code again on a trusted device?
- Gold: activating-users-with-a-registration-code, how-cato-mfa-and-expiration-mechanism-works, managing-sdp-clients-with-the-cato-user-portal, sso-session-behavior-for-windows-sdp-client
- Gold found in the top 10: how-cato-mfa-and-expiration-mechanism-works, managing-sdp-clients-with-the-cato-user-portal, sso-session-behavior-for-windows-sdp-client, activating-users-with-a-registration-code
- Top 3 returned: how-cato-mfa-and-expiration-mechanism-works (7.1), managing-sdp-clients-with-the-cato-user-portal (6.1), configuring-the-authentication-policy-for-cato-clients (5.9)
