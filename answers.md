# answers.md: the agent on the 35 benchmark questions

- Generated: 2026-10-03T19:36:22+00:00 by `python -m eval.run_questions`
- Code path: the chat workflow (`build_workflow(...).run_turn`), one new conversation per question, caller netops@northwind-logistics.com (ACC-1001, Premium)
- KB snapshot date: 2026-09-29T10:35:47Z
- Totals: 614 s, 768791 tokens, $0.0941

## Q01

**Question:** What is the effective MTU over the Socket-to-PoP DTLS tunnel, and what does the Socket do with an oversized WAN packet that has the DF bit set?

**Answer:**

The effective MTU over the Socket-to-PoP DTLS tunnel is 1383 bytes; DTLS overhead reduces the typical 1500-byte Ethernet MTU to this value. [kb:socket-mtu-and-dtls-tunnels#overview]

For an oversized WAN packet with DF set, the Socket sends an ICMP Fragmentation Needed message to the sender with the acceptable MTU, prompting the sender to fragment the packet accordingly. [kb:socket-mtu-and-dtls-tunnels#df-set]

I opened ticket TCK-20264254 for you.

**Citations:**
- Socket MTU and DTLS Tunnels › Overview (`socket-mtu-and-dtls-tunnels#overview`) https://knowledge.catonetworks.com/docs/socket-mtu-and-dtls-tunnels
- Socket MTU and DTLS Tunnels › DF Set (`socket-mtu-and-dtls-tunnels#df-set`) https://knowledge.catonetworks.com/docs/socket-mtu-and-dtls-tunnels

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `socket-mtu-and-dtls-tunnels#df-set` | 0.0164 | 8.31 |
| 2 | `socket-mtu-and-dtls-tunnels#off-cloud-traffic` | 0.0000 | 8.31 |
| 3 | `socket-mtu-and-dtls-tunnels#overview` | 0.0161 | 7.92 |
| 4 | `advanced-configurations-for-a-site#configuring-the-mtu-for-dtls-tunnels-to-the-cato-cloud` | 0.0164 | 5.76 |
| 5 | `advanced-configurations-for-a-site#configuring-recovery-via-internet-for-a-site` | 0.0000 | 5.76 |

**Latency / cost:** 17612 ms, 21018+642 tokens, $0.002497

## Q02

**Question:** Do Cato Sockets support jumbo frames on LAN ports? What happens to a 9000-byte frame received on a LAN port?

**Answer:**

No. Cato Sockets do not support jumbo frames on LAN ports. For a 9000-byte packet received on a LAN port, the Socket checks the Do Not Fragment (DF) bit: if DF is not set, it accepts and fragments the packet to meet the 1500-byte limit; if DF is set, it drops the packet and sends an ICMP Fragmentation Needed message to the sender. [kb:socket-mtu-and-dtls-tunnels#socket-lan-ports-and-jumbo-frames]

I opened ticket TCK-20264255 for you.

**Citations:**
- Socket MTU and DTLS Tunnels › Socket LAN Ports and Jumbo Frames (`socket-mtu-and-dtls-tunnels#socket-lan-ports-and-jumbo-frames`) https://knowledge.catonetworks.com/docs/socket-mtu-and-dtls-tunnels

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `socket-mtu-and-dtls-tunnels#socket-lan-ports-and-jumbo-frames` | 0.0164 | 8.31 |
| 2 | `socket-mtu-and-dtls-tunnels#df-not-set` | 0.0000 | 8.31 |
| 3 | `socket-mtu-and-dtls-tunnels#mtu-behavior-with-multiple-active-wan-links` | 0.0000 | 8.31 |
| 4 | `socket-mtu-and-dtls-tunnels#off-cloud-traffic` | 0.0000 | 8.31 |
| 5 | `socket-mtu-and-dtls-tunnels#configuring-the-mtu-for-a-specific-socket-site` | 0.0000 | 8.31 |

**Latency / cost:** 14031 ms, 14232+751 tokens, $0.001931

## Q03

**Question:** A Socket site has two active WAN links with discovered MTUs of 1450 and 1383 bytes. Which MTU is used downstream, and do passive links affect it?

**Answer:**

For downstream traffic, the PoP uses the lowest MTU discovered across the active WAN links. With discovered MTUs of 1450 and 1383 bytes, the downstream MTU is 1383 bytes. Passive WAN links do not influence the MTU used for active tunnels. [kb:socket-mtu-and-dtls-tunnels#mtu-behavior-with-multiple-active-wan-links]

I opened ticket TCK-20264256 for you.

**Citations:**
- Socket MTU and DTLS Tunnels › MTU Behavior with Multiple Active WAN Links (`socket-mtu-and-dtls-tunnels#mtu-behavior-with-multiple-active-wan-links`) https://knowledge.catonetworks.com/docs/socket-mtu-and-dtls-tunnels

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `socket-mtu-and-dtls-tunnels#mtu-behavior-with-multiple-active-wan-links` | 0.0315 | 7.95 |
| 2 | `socket-mtu-and-dtls-tunnels#configuring-the-mtu-for-a-specific-socket-site` | 0.0000 | 7.95 |
| 3 | `socket-mtu-and-dtls-tunnels#socket-lan-ports-and-jumbo-frames` | 0.0000 | 7.95 |
| 4 | `socket-mtu-and-dtls-tunnels#off-cloud-traffic` | 0.0000 | 7.95 |
| 5 | `understanding-acceptable-and-unacceptable-sla-for-sites#overview` | 0.0286 | 5.66 |

**Latency / cost:** 12635 ms, 17267+618 tokens, $0.002243

## Q04

**Question:** What are the default BGP Hold Time and keep-alive interval for a Cato site, and what happens if the two neighbors are configured with different Hold Times?

**Answer:**

For a Cato site, the default BGP Hold Time is 60 seconds and the default keep-alive interval is 20 seconds. The recommended keep-alive interval is one-third of the Hold Time. [kb:configuring-bgp-neighbors-for-a-cato-socket#advanced-bgp-settings]

If the neighbors have different Hold Times, the smaller value is used for the pair, so both neighbors use the same Hold Time. [kb:configuring-bgp-neighbors-for-a-cato-socket#advanced-bgp-settings]

I opened ticket TCK-20264257 for you.

**Citations:**
- Configuring BGP Neighbors for a Cato Socket › Advanced BGP Settings (`configuring-bgp-neighbors-for-a-cato-socket#advanced-bgp-settings`) https://knowledge.catonetworks.com/docs/configuring-bgp-neighbors-for-a-cato-socket

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `configuring-bgp-neighbors-for-a-cato-socket#advanced-bgp-settings` | 0.0328 | 6.49 |
| 2 | `configuring-bgp-neighbors-for-an-ipsec-connection#advanced-bgp-settings` | 0.0323 | 6.49 |
| 3 | `configuring-bgp-neighbors-for-an-ipsec-connection#advanced-bgp-settings` | 0.0000 | 6.49 |
| 4 | `configuring-bgp-neighbors-for-a-cato-socket#advanced-bgp-settings` | 0.0000 | 6.49 |
| 5 | `configuring-bgp-neighbors-for-a-cato-socket#overview` | 0.0000 | 6.49 |

**Latency / cost:** 13211 ms, 14972+735 tokens, $0.002015

## Q05

**Question:** How many BGP routes can a Socket accept from a neighbor before the session is affected, and what are the two recommended ways to reduce the advertised routes?

**Answer:**

The BGP prefix-exhaustion playbook identifies **1,024 routes** as the route-count limit to check for a Socket, but the available guidance does not specify what happens to the BGP session when that threshold is reached. [kb:xops-network-playbook-bgp-prefix-exhaustion#check-bgp-status]

Separately, the BGP session-disconnection guidance explains that a disconnected session terminates the connection between the routers and disrupts routing-information exchange; the impact depends on redundancy and failover. It does not say that reaching the route threshold disconnects the session. [kb:xops-network-playbook-bgp-session-disconnected#overview]

The two recommended ways to reduce advertised routes are to **advertise aggregated (summarized) routes** and **filter out infrastructure, transit, or other prefixes that are not WAN-relevant**. If the advertised count remains above 1,024 after those steps, the playbook advises contacting Cato Support. [kb:xops-network-playbook-bgp-prefix-exhaustion#step-2---reduce-the-number-of-advertised-routes]

One implementation caution: changing summary-route configuration causes a hard BGP peer reset, and editing BGP filters triggers an immediate BGP session reset. [kb:working-with-bgp-summary-routes#configuring-bgp-summary-routes] [kb:working-with-bgp-filtering#overview]

I can’t confirm from the available product guidance what session behavior to expect at the route threshold, so I’m escalating that specific question for follow-up.

I opened ticket TCK-20264258 for you.

**Citations:**
- XOps Network Playbook - BGP Prefix Exhaustion › Check BGP Status (`xops-network-playbook-bgp-prefix-exhaustion#check-bgp-status`) https://knowledge.catonetworks.com/docs/xops-network-playbook-bgp-prefix-exhaustion
- XOps Network Playbook - BGP Session Disconnected › Overview (`xops-network-playbook-bgp-session-disconnected#overview`) https://knowledge.catonetworks.com/docs/xops-network-playbook-bgp-session-disconnected
- XOps Network Playbook - BGP Prefix Exhaustion › Step 2 - Reduce the number of advertised routes (`xops-network-playbook-bgp-prefix-exhaustion#step-2---reduce-the-number-of-advertised-routes`) https://knowledge.catonetworks.com/docs/xops-network-playbook-bgp-prefix-exhaustion
- Working with BGP Summary Routes › Configuring BGP Summary Routes (`working-with-bgp-summary-routes#configuring-bgp-summary-routes`) https://knowledge.catonetworks.com/docs/working-with-bgp-summary-routes
- Working with BGP Filtering › Overview (`working-with-bgp-filtering#overview`) https://knowledge.catonetworks.com/docs/working-with-bgp-filtering

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `working-with-bgp-summary-routes#understanding-bgp-summary-routes` | 0.0325 | 6.69 |
| 2 | `working-with-bgp-summary-routes#prerequisites-for-using-bgp-summary-routes` | 0.0000 | 6.69 |
| 3 | `working-with-bgp-summary-routes#bgp-summary-routes-use-cases` | 0.0000 | 6.69 |
| 4 | `working-with-bgp-summary-routes#configuring-bgp-summary-routes` | 0.0000 | 6.69 |
| 5 | `working-with-bgp-summary-routes#configuring-bgp-summary-routes` | 0.0000 | 6.69 |

**Latency / cost:** 27610 ms, 34691+2070 tokens, $0.003635

## Q06

**Question:** Which prerequisites and limits apply to BGP summary routes on Socket sites?

**Answer:**

For BGP summary routes on Socket sites:

- **Socket version:** The feature is supported on Sockets running v19.x or higher. [kb:working-with-bgp-summary-routes#prerequisites-for-using-bgp-summary-routes]
- **Route prefix length:** Each summary route must use a CIDR range from /8 through /30. [kb:working-with-bgp-summary-routes#prerequisites-for-using-bgp-summary-routes]
- **Per-peer limits:** You can configure up to 256 summary routes per BGP peer, with up to 5 communities per summary route. Communities use `ASN:community` format, with each value from 1 to 65535. [kb:working-with-bgp-summary-routes#configuring-bgp-summary-routes]

Please also note that changing BGP advertisement settings, including summary routes, triggers a hard BGP peer reset and may affect end-user experience. [kb:working-with-bgp-summary-routes#configuring-bgp-summary-routes]

I opened ticket TCK-20264259 for you.

**Citations:**
- Working with BGP Summary Routes › Prerequisites for Using BGP Summary Routes (`working-with-bgp-summary-routes#prerequisites-for-using-bgp-summary-routes`) https://knowledge.catonetworks.com/docs/working-with-bgp-summary-routes
- Working with BGP Summary Routes › Configuring BGP Summary Routes (`working-with-bgp-summary-routes#configuring-bgp-summary-routes`) https://knowledge.catonetworks.com/docs/working-with-bgp-summary-routes

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `working-with-bgp-summary-routes#prerequisites-for-using-bgp-summary-routes` | 0.0164 | 5.15 |
| 2 | `working-with-bgp-summary-routes#overview` | 0.0000 | 5.15 |
| 3 | `working-with-bgp-summary-routes#configuring-bgp-summary-routes` | 0.0000 | 5.15 |
| 4 | `working-with-bgp-summary-routes#bgp-summary-routes-use-cases` | 0.0298 | 4.36 |
| 5 | `working-with-bgp-summary-routes#understanding-bgp-summary-routes` | 0.0310 | 4.27 |

**Latency / cost:** 17209 ms, 15714+1011 tokens, $0.002244

## Q07

**Question:** What are the default BFD timers Cato recommends for an IPsec site versus a Cloud Interconnect site, and what must you do after changing BFD timers?

**Answer:**

Cato’s recommended defaults are **1,000 ms transmit, 1,000 ms receive, and a multiplier of 5** for an IPsec site; for a Cloud Interconnect site, they are **500 ms transmit, 500 ms receive, and a multiplier of 3**. The IPsec values are generally suited to internet connections, while the Cloud Interconnect values are generally suited to L2 connections. [kb:configuring-bfd-for-bgp-neighbors#using-bfd-for-ipsec-sites] [kb:configuring-bfd-for-bgp-neighbors#using-bfd-for-cloud-interconnect-sites]

After changing BFD timers, disable the BFD session and then enable it again so the changes take effect; otherwise, the changes are ignored. [kb:configuring-bfd-for-bgp-neighbors#using-bfd-for-ipsec-sites]

I opened ticket TCK-20264260 for you.

**Citations:**
- Configuring BFD for BGP Neighbors › Using BFD for IPsec Sites (`configuring-bfd-for-bgp-neighbors#using-bfd-for-ipsec-sites`) https://knowledge.catonetworks.com/docs/configuring-bfd-for-bgp-neighbors
- Configuring BFD for BGP Neighbors › Using BFD for Cloud Interconnect Sites (`configuring-bfd-for-bgp-neighbors#using-bfd-for-cloud-interconnect-sites`) https://knowledge.catonetworks.com/docs/configuring-bfd-for-bgp-neighbors

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `configuring-bfd-for-bgp-neighbors#overview` | 0.0290 | 6.48 |
| 2 | `configuring-bfd-for-bgp-neighbors#configuring-bfd-for-bgp-neighbors-1` | 0.0000 | 6.48 |
| 3 | `configuring-bfd-for-bgp-neighbors#known-limitations` | 0.0000 | 6.48 |
| 4 | `configuring-bfd-for-bgp-neighbors#understanding-bfd-for-bgp-enabled-sites` | 0.0000 | 6.48 |
| 5 | `configuring-bfd-for-bgp-neighbors#using-bfd-for-ipsec-sites` | 0.0164 | 3.83 |

**Latency / cost:** 12901 ms, 13663+724 tokens, $0.001842

## Q08

**Question:** On which site types does Cato support active BFD for BGP neighbors, and which UDP port does multi-hop BFD use?

**Answer:**

Cato supports active BFD for BGP neighbors on IPsec and Cloud Interconnect sites. BFD in passive mode is supported across all site types, including Sockets and vSockets. [kb:configuring-bfd-for-bgp-neighbors#overview]

Multi-hop BFD uses UDP port 4784. [kb:configuring-bfd-for-bgp-neighbors#overview]

I opened ticket TCK-20264261 for you.

**Citations:**
- Configuring BFD for BGP Neighbors › Overview (`configuring-bfd-for-bgp-neighbors#overview`) https://knowledge.catonetworks.com/docs/configuring-bfd-for-bgp-neighbors

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `configuring-bfd-for-bgp-neighbors#overview` | 0.0328 | 7.34 |
| 2 | `configuring-bfd-for-bgp-neighbors#configuring-bfd-for-bgp-neighbors-1` | 0.0000 | 7.34 |
| 3 | `configuring-bfd-for-bgp-neighbors#use-case` | 0.0000 | 7.34 |
| 4 | `configuring-bfd-for-bgp-neighbors#known-limitations` | 0.0000 | 7.34 |
| 5 | `configuring-bfd-for-bgp-neighbors#understanding-bfd-for-bgp-enabled-sites` | 0.0000 | 7.34 |

**Latency / cost:** 9568 ms, 13232+509 tokens, $0.001685

## Q09

**Question:** A BGP session shows Disconnected. Which CMA views does the playbook use to find the disconnect reason and to verify the route table?

**Answer:**

To identify why the BGP session disconnected, open **Home > Events** in the Cato Management Application and select the **BGP peers disconnected** preset. The matching event includes a BGP Disconnect Error Code that can help clarify the reason. [kb:xops-network-playbook-bgp-session-disconnected#clarify-bgp-session-disconnection-reason]

To verify the route table, open the **Routing Table** and search for the resource IP. Check that a matching route exists via the expected site; if there are multiple routes to the destination, compare their metrics, since lower metrics are preferred. [kb:access-to-internal-resources-troubleshooting#checking-the-cato-routing-table]

You can also use **Show BGP Status** under **Site Configuration > BGP** to check the site's BGP status and current advertisements. [kb:working-with-bgp-summary-routes#monitoring-bgp-summary-routes]

I opened ticket TCK-20264262 for you.

**Citations:**
- XOps Network Playbook - BGP Session Disconnected › Clarify BGP Session Disconnection Reason (`xops-network-playbook-bgp-session-disconnected#clarify-bgp-session-disconnection-reason`) https://knowledge.catonetworks.com/docs/xops-network-playbook-bgp-session-disconnected
- Access to Internal Resources Troubleshooting › Checking the Cato Routing Table (`access-to-internal-resources-troubleshooting#checking-the-cato-routing-table`) https://knowledge.catonetworks.com/docs/access-to-internal-resources-troubleshooting
- Working with BGP Summary Routes › Monitoring BGP Summary Routes (`working-with-bgp-summary-routes#monitoring-bgp-summary-routes`) https://knowledge.catonetworks.com/docs/working-with-bgp-summary-routes

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `working-with-bgp-summary-routes#monitoring-bgp-summary-routes` | 0.0156 | 5.15 |
| 2 | `working-with-bgp-summary-routes#configuring-bgp-summary-routes` | 0.0000 | 5.15 |
| 3 | `access-to-internal-resources-troubleshooting#checking-the-cato-routing-table` | 0.0159 | 5.05 |
| 4 | `access-to-internal-resources-troubleshooting#verifying-dns-forwarding` | 0.0000 | 5.05 |
| 5 | `access-to-internal-resources-troubleshooting#checking-ipsec-policy-based-routing` | 0.0000 | 5.05 |

**Latency / cost:** 15523 ms, 20832+930 tokens, $0.002842

## Q10

**Question:** An IPsec IKEv2 site logs NO_PROPOSAL_CHOSEN. What does it mean and how do you find exactly which parameters are being proposed?

**Answer:**

`NO_PROPOSAL_CHOSEN` means the peers could not agree on one or more IPsec security-association parameters—such as an algorithm or DH group configured in the Cato Management Application versus the remote peer’s configuration. It can occur during tunnel establishment or rekeying. [kb:ipsec-site-connectivity-troubleshooting#using-packet-captures-to-troubleshoot]

To see exactly what is being proposed, open the site’s **IPsec** tab in the Cato Management Application and review **Init** and **Auth Message Parameters**. Then download the PCAP and inspect the **IKE_AUTH** message containing the **CHILD_SAproposal**. In its **Security Association** payload, review the **Transform Payload** for the proposed encryption, integrity, PFS (DH group), and other attributes. Compare these with the firewall’s settings and adjust the configuration so they match. [kb:xops-network-playbook-ipsec-phase2-failure#no-proposal-chosen]

I opened ticket TCK-20264263 for you.

**Citations:**
- IPsec Site Connectivity Troubleshooting › Using Packet Captures to Troubleshoot (`ipsec-site-connectivity-troubleshooting#using-packet-captures-to-troubleshoot`) https://knowledge.catonetworks.com/docs/ipsec-site-connectivity-troubleshooting
- XOps Network Playbook - IPsec Phase2 Failure › No Proposal Chosen (`xops-network-playbook-ipsec-phase2-failure#no-proposal-chosen`) https://knowledge.catonetworks.com/docs/xops-network-playbook-ipsec-phase2-failure

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `xops-network-playbook-ipsec-phase2-failure#no-proposal-chosen` | 0.0304 | 4.68 |
| 2 | `xops-network-playbook-ipsec-phase2-failure#[REDACTED:HIGH_ENTROPY]` | 0.0000 | 4.68 |
| 3 | `xops-network-playbook-ipsec-phase2-failure#no-proposal-chosen` | 0.0000 | 4.68 |
| 4 | `xops-network-playbook-ipsec-phase2-failure#ts-unacceptable` | 0.0000 | 4.68 |
| 5 | `xops-network-playbook-ipsec-phase2-failure#ts-unacceptable` | 0.0000 | 4.68 |

**Latency / cost:** 17116 ms, 14213+949 tokens, $0.002027

## Q11

**Question:** Why does a Cisco ASA return TS_UNACCEPTABLE to a Cato IPsec proposal, and how can it be fixed?

**Answer:**

A Cisco ASA can return `TS_UNACCEPTABLE` because Cato may send multiple traffic selectors (TS) in one payload when creating a child SA, while some Cisco ASAs support only one TS per child SA. [kb:configuring-ipsec-ikev2-sites#sending-a-single-traffic-selector-for-ikev2-sites]

To check for a selector mismatch, download the PCAP from the site's IPsec tab in the Cato Management Application. Find the last `TS_UNACCEPTABLE` response, then review the earlier `IKE_AUTH_MID` packets and compare the initiator and responder traffic-selector ranges with the ranges in the site's IPsec Routing tab. Add or remove ranges so the configured ranges match. [kb:xops-network-playbook-ipsec-phase2-failure#ts-unacceptable]

If the ranges match and this is the ASA single-selector interoperability case, enable **IKEv2 Send Single TS per Payload** in the account's advanced configuration, or enable the equivalent configuration for the specific IPsec IKEv2 site under **Site Configuration > Advanced Configuration**. This setting sends one TS in each child SA; it is disabled by default. [kb:working-with-advanced-configuration-for-the-account#ikev2-sites-sending-a-single-ts-per-payload] [kb:configuring-ipsec-ikev2-sites#sending-a-single-traffic-selector-for-ikev2-sites]

I opened ticket TCK-20264264 for you.

**Citations:**
- Configuring IPsec IKEv2 Sites › Sending a Single Traffic Selector for IKEv2 Sites (`configuring-ipsec-ikev2-sites#sending-a-single-traffic-selector-for-ikev2-sites`) https://knowledge.catonetworks.com/docs/configuring-ipsec-ikev2-sites
- XOps Network Playbook - IPsec Phase2 Failure › TS UNACCEPTABLE (`xops-network-playbook-ipsec-phase2-failure#ts-unacceptable`) https://knowledge.catonetworks.com/docs/xops-network-playbook-ipsec-phase2-failure
- Working with Advanced Configuration for the Account › IKEv2 Sites Sending a Single TS per Payload (`working-with-advanced-configuration-for-the-account#ikev2-sites-sending-a-single-ts-per-payload`) https://knowledge.catonetworks.com/docs/working-with-advanced-configuration-for-the-account

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `configuring-ipsec-ikev2-sites#sending-a-single-traffic-selector-for-ikev2-sites` | 0.0164 | 7.55 |
| 2 | `configuring-ipsec-ikev2-sites#default-ikev2-parameters-for-the-site` | 0.0000 | 7.55 |
| 3 | `configuring-ipsec-ikev2-sites#connecting-two-tunnels-to-an-aws-vpc-for-ha` | 0.0000 | 7.55 |
| 4 | `configuring-ipsec-ikev2-sites#known-limitations` | 0.0000 | 7.55 |
| 5 | `xops-network-playbook-ipsec-phase2-failure#ts-unacceptable` | 0.0323 | 7.15 |

**Latency / cost:** 15627 ms, 18479+1019 tokens, $0.002595

## Q12

**Question:** Which IPsec encryption algorithms does Cato recommend for sites with 100 Mbps or more, and why?

**Answer:**

For an IPsec site with bandwidth of 100 Mbps or more, Cato recommends using only AES 128 GCM-16 or AES 256 GCM-16. AES CBC is intended only for sites below 100 Mbps. Cato recommends GCM for higher-throughput traffic because it is more efficient and scalable than CBC, supporting better performance and reliability [kb:cato-cloud-thresholds-and-limits#supported-encryption-algorithms-based-on-ipsec-site-bandwidth].

Use the same encryption algorithm on both peers, and avoid enabling extra algorithms you do not use; having multiple choices can take longer to establish the connection [kb:recommendations-for-ipsec-connections#selecting-specific-encryption-algorithms]. I’ve opened a support ticket to track your question.

I opened ticket TCK-20264265 for you.

**Citations:**
- Cato Cloud Thresholds and Limits › Supported Encryption Algorithms Based on IPsec Site Bandwidth (`cato-cloud-thresholds-and-limits#supported-encryption-algorithms-based-on-ipsec-site-bandwidth`) https://knowledge.catonetworks.com/docs/cato-cloud-thresholds-and-limits
- Recommendations for IPsec Connections › Selecting Specific Encryption Algorithms (`recommendations-for-ipsec-connections#selecting-specific-encryption-algorithms`) https://knowledge.catonetworks.com/docs/recommendations-for-ipsec-connections

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `cato-cloud-thresholds-and-limits#supported-encryption-algorithms-based-on-ipsec-site-bandwidth` | 0.0164 | 6.94 |
| 2 | `cato-cloud-thresholds-and-limits#alert-limits-per-alert-type` | 0.0000 | 6.94 |
| 3 | `cato-cloud-thresholds-and-limits#supported-throughput-for-cato-sites` | 0.0000 | 6.94 |
| 4 | `cato-cloud-thresholds-and-limits#throughput-for-the-socket-sites` | 0.0000 | 6.94 |
| 5 | `cato-cloud-thresholds-and-limits#throughput-for-the-socket-sites` | 0.0000 | 6.94 |

**Latency / cost:** 13783 ms, 18340+802 tokens, $0.002467

## Q13

**Question:** Why does Cato recommend selecting 'Initiate connection by Cato' for IKEv2 sites?

**Answer:**

Cato recommends enabling **Initiate connection by Cato** because edge devices often wait a long time between reconnect attempts. If the edge device initiates, VPN negotiation can therefore take longer; when Cato initiates, negotiation is faster and the tunnel can be restored without waiting for the device to start the attempt. [kb:recommendations-for-ipsec-connections#use-cato-as-a-connection-initiator] The setting is enabled by default for IKEv2 and is intended to minimize downtime. [kb:configuring-sites-with-ipsec-connections#configuring-ikev2-settings]

This is a recommendation rather than a requirement: ensure the IKEv2 parameters are supported by and match your peer device. [kb:recommendations-for-ipsec-connections#using-ikev1-or-ikev2]

I opened ticket TCK-20264266 for you.

**Citations:**
- Recommendations for IPsec Connections › Use Cato as a Connection Initiator (`recommendations-for-ipsec-connections#use-cato-as-a-connection-initiator`) https://knowledge.catonetworks.com/docs/recommendations-for-ipsec-connections
- Configuring Sites with IPsec Connections › Configuring IKEv2 Settings (`configuring-sites-with-ipsec-connections#configuring-ikev2-settings`) https://knowledge.catonetworks.com/docs/configuring-sites-with-ipsec-connections
- Recommendations for IPsec Connections › Using IKEv1 or IKEv2 (`recommendations-for-ipsec-connections#using-ikev1-or-ikev2`) https://knowledge.catonetworks.com/docs/recommendations-for-ipsec-connections

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `recommendations-for-ipsec-connections#use-cato-as-a-connection-initiator` | 0.0164 | 8.57 |
| 2 | `recommendations-for-ipsec-connections#using-ikev1-or-ikev2` | 0.0000 | 8.57 |
| 3 | `recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers` | 0.0000 | 8.57 |
| 4 | `recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers` | 0.0000 | 8.57 |
| 5 | `recommendations-for-ipsec-connections#select-the-exact-configuration-settings` | 0.0000 | 8.57 |

**Latency / cost:** 13150 ms, 18513+745 tokens, $0.002460

## Q14

**Question:** What is the maximum length of the IPsec pre-shared key, and what is lost when a site's Connection Type is changed from IKEv1 to IKEv2?

**Answer:**

The IPsec pre-shared key can be up to 64 characters for both IKEv1 and IKEv2 [kb:cato-ipsec-guide-ikev1-vs-ikev2#similarities-between-ikev2-and-ikev1].

When you change a site's Connection Type from IKEv1 to IKEv2, its Native Range and other configured networks are lost. You’ll need to enter the Native Range and remote networks again in the Networks settings [kb:cato-ipsec-guide-ikev1-vs-ikev2#switching-from-ikev1-to-ikev2-in-the-cato-management-application].

I opened ticket TCK-20264267 for you.

**Citations:**
- Cato IPsec Guide: IKEv1 vs IKEv2 › Similarities Between IKEv2 and IKEv1 (`cato-ipsec-guide-ikev1-vs-ikev2#similarities-between-ikev2-and-ikev1`) https://knowledge.catonetworks.com/docs/cato-ipsec-guide-ikev1-vs-ikev2
- Cato IPsec Guide: IKEv1 vs IKEv2 › Switching from IKEv1 to IKEv2 in the Cato Management Application (`cato-ipsec-guide-ikev1-vs-ikev2#switching-from-ikev1-to-ikev2-in-the-cato-management-application`) https://knowledge.catonetworks.com/docs/cato-ipsec-guide-ikev1-vs-ikev2

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `cato-ipsec-guide-ikev1-vs-ikev2#switching-from-ikev1-to-ikev2-in-the-cato-management-application` | 0.0304 | 7.34 |
| 2 | `cato-ipsec-guide-ikev1-vs-ikev2#switching-from-ikev1-to-ikev2-in-the-cato-management-application` | 0.0000 | 7.34 |
| 3 | `cato-ipsec-guide-ikev1-vs-ikev2#switching-from-ikev1-to-ikev2-in-the-cato-management-application` | 0.0000 | 7.34 |
| 4 | `cato-ipsec-guide-ikev1-vs-ikev2#ikev2-the-final-frontier` | 0.0000 | 7.34 |
| 5 | `cato-ipsec-guide-ikev1-vs-ikev2#similarities-between-ikev2-and-ikev1` | 0.0301 | 6.80 |

**Latency / cost:** 17112 ms, 31141+759 tokens, $0.003339

## Q15

**Question:** A tunnel to Azure comes up but fails at rekey. What Azure behaviour around PFS/DH groups explains this?

**Answer:**

Azure behaves differently depending on which peer initiates the Child SA (ESP SA) rekey. When Azure initiates, it does not send a DH group by default. If a DH group is configured in Cato’s Auth Message Parameters, Cato can respond with “No proposal chosen,” causing the rekeyed SA to fail. When Cato initiates instead, Azure accepts a DH group from the peer if it is one Azure supports. [kb:recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers]

For compatibility, either set the DH group to **None** in Cato’s IKEv2 Auth Message Parameters, which disables PFS, or configure an Azure custom policy with the same PFS group as Cato’s configured DH group. A DH group mismatch can prevent the tunnel from connecting, so the groups must match when PFS is enabled. [kb:recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers] [kb:recommendations-for-ipsec-connections#selecting-a-suitable-diffie-helman-group]

I opened ticket TCK-20264268 for you.

**Citations:**
- Recommendations for IPsec Connections › Default IPsec Connectivity Settings for Cloud Providers (`recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers`) https://knowledge.catonetworks.com/docs/recommendations-for-ipsec-connections
- Recommendations for IPsec Connections › Selecting a Suitable Diffie-Helman Group (`recommendations-for-ipsec-connections#selecting-a-suitable-diffie-helman-group`) https://knowledge.catonetworks.com/docs/recommendations-for-ipsec-connections

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers` | 0.0328 | 5.81 |
| 2 | `recommendations-for-ipsec-connections#use-cato-as-a-connection-initiator` | 0.0000 | 5.81 |
| 3 | `recommendations-for-ipsec-connections#default-ipsec-connectivity-settings-for-cloud-providers` | 0.0000 | 5.81 |
| 4 | `recommendations-for-ipsec-connections#select-the-exact-configuration-settings` | 0.0000 | 5.81 |
| 5 | `recommendations-for-ipsec-connections#verifying-the-ipsec-connection` | 0.0000 | 5.81 |

**Latency / cost:** 13479 ms, 14433+883 tokens, $0.002022

## Q16

**Question:** What are the requirements for enabling IP Overlapping between sites, and what is the default Cato system range?

**Answer:**

To enable IP Overlapping between sites, the account must meet these requirements: it must not use Static Range Translation; one overlapping range must be smaller and fully contained within the other; all Sockets in the account must be version 6.1 or later; each site must have a unique IP address for its Native Range; and neither the IP range for remote access users nor the Cato system range may be contained within an overlapping range. The default Cato system range is **10.254.254.0/24**. [kb:configuring-your-account-to-support-ip-overlapping#requirements-for-ip-overlapping]

You can enable the feature in **Resources > System Settings**: select **Enable IP Overlapping between sites**, then click **Save**. Note that enabling it is a permanent account change; the guide says to contact Support if you need it disabled. [kb:configuring-your-account-to-support-ip-overlapping#enabling-ip-overlapping-for-the-account]

I opened ticket TCK-20264269 for you.

**Citations:**
- Configuring Your Account to Support IP Overlapping › Requirements for IP Overlapping (`configuring-your-account-to-support-ip-overlapping#requirements-for-ip-overlapping`) https://knowledge.catonetworks.com/docs/configuring-your-account-to-support-ip-overlapping
- Configuring Your Account to Support IP Overlapping › Enabling IP Overlapping for the Account (`configuring-your-account-to-support-ip-overlapping#enabling-ip-overlapping-for-the-account`) https://knowledge.catonetworks.com/docs/configuring-your-account-to-support-ip-overlapping

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `configuring-your-account-to-support-ip-overlapping#requirements-for-ip-overlapping` | 0.0164 | 7.90 |
| 2 | `product-update-march-6th-2023#new-features--enhancements` | 0.0161 | 6.75 |
| 3 | `product-update-march-6th-2023#new-features--enhancements` | 0.0000 | 6.75 |
| 4 | `product-update-march-6th-2023#pop-announcements` | 0.0000 | 6.75 |
| 5 | `product-update-march-6th-2023#security-updates` | 0.0000 | 6.75 |

**Latency / cost:** 13338 ms, 11225+828 tokens, $0.001594

## Q17

**Question:** Which alternate UDP port can DTLS tunnels use, when is it recommended, and what are the version prerequisites?

**Answer:**

The alternate DTLS UDP port is **1337**. Cato recommends configuring it for accounts with Socket sites and Client users in China, where DTLS on UDP 443 can experience connectivity issues such as packet loss. By default, UDP 443 is preferred and tunnels fall back to 1337 when connectivity issues occur; enabling the account setting makes 1337 preferred, with 443 as fallback. The setting applies to Socket sites and Client users located in China [kb:using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#overview].

Prerequisites: Socket sites need **Socket v26 or later**; Client traffic needs **Windows Client v6.4 or later**. This Client feature is supported only on Windows; Clients on other operating systems continue to prefer UDP 443 [kb:using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#prerequisites] [kb:using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#known-limitations].

You can enable it account-wide in **Resources > System Settings**, under **Alternative DTLS Port**. Socket tunnels reconnect when the setting is enabled, which may briefly affect connectivity [kb:using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#configuring-the-alternate-dtls-udp-port].

I opened ticket TCK-20264270 for you.

**Citations:**
- Using an Alternate UDP Port for Socket and Client DTLS Traffic › Overview (`using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#overview`) https://knowledge.catonetworks.com/docs/using-an-alternate-udp-port-for-socket-and-client-dtls-traffic
- Using an Alternate UDP Port for Socket and Client DTLS Traffic › Prerequisites (`using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#prerequisites`) https://knowledge.catonetworks.com/docs/using-an-alternate-udp-port-for-socket-and-client-dtls-traffic
- Using an Alternate UDP Port for Socket and Client DTLS Traffic › Known Limitations (`using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#known-limitations`) https://knowledge.catonetworks.com/docs/using-an-alternate-udp-port-for-socket-and-client-dtls-traffic
- Using an Alternate UDP Port for Socket and Client DTLS Traffic › Configuring the Alternate DTLS UDP Port (`using-an-alternate-udp-port-for-socket-and-client-dtls-traffic#configuring-the-alternate-dtls-udp-port`) https://knowledge.catonetworks.com/docs/using-an-alternate-udp-port-for-socket-and-client-dtls-traffic

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `understanding-cato-networking-in-china#udp-port-1337-for-china-socket-and-client-dtls-traffic` | 0.0315 | 5.64 |
| 2 | `understanding-cato-networking-in-china#egressing-traffic-in-china` | 0.0000 | 5.64 |
| 3 | `understanding-cato-networking-in-china#licensing` | 0.0000 | 5.64 |
| 4 | `understanding-cato-networking-in-china#qos-for-china-sites` | 0.0000 | 5.64 |
| 5 | `understanding-cato-networking-in-china#video-conferencing-using-percentage-based-profiles` | 0.0000 | 5.64 |

**Latency / cost:** 16831 ms, 22631+934 tokens, $0.002688

## Q18

**Question:** Why might throughput drop for a Socket placed behind a third-party firewall, and what is the recommended fix?

**Answer:**

Reduced throughput can occur when a third-party firewall’s UDP Flooding protection limits traffic carried over the Cato DTLS tunnels; this protection is often enabled by default on firewalls. [kb:performance-troubleshooting-socket-behind-a-third-party-firewall#challenge]

Cato recommends disabling UDP Flooding protection on the firewall, then running a speed test to compare throughput with the protection disabled. [kb:performance-troubleshooting-socket-behind-a-third-party-firewall#solution]

I opened ticket TCK-20264271 for you.

**Citations:**
- Performance Troubleshooting: Socket Behind a Third-Party Firewall › Challenge (`performance-troubleshooting-socket-behind-a-third-party-firewall#challenge`) https://knowledge.catonetworks.com/docs/performance-troubleshooting-socket-behind-a-third-party-firewall
- Performance Troubleshooting: Socket Behind a Third-Party Firewall › Solution (`performance-troubleshooting-socket-behind-a-third-party-firewall#solution`) https://knowledge.catonetworks.com/docs/performance-troubleshooting-socket-behind-a-third-party-firewall

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `performance-troubleshooting-socket-behind-a-third-party-firewall#challenge` | 0.0159 | 5.75 |
| 2 | `performance-troubleshooting-socket-behind-a-third-party-firewall#solution` | 0.0000 | 5.75 |
| 3 | `cato-sockets#performance-troubleshooting-socket-behind-a-third-party-firewallhttpsknowledgecatonetworkscomdocsperformance-troubleshooting-socket-behind-a-third-party-firewallmd` | 0.0161 | 5.19 |
| 4 | `cato-sockets#assigning-a-static-ip-to-a-sockethttpsknowledgecatonetworkscomdocsassigning-a-static-ip-to-a-socketmd` | 0.0000 | 5.19 |
| 5 | `cato-sockets#remotely-pinging-the-socket-interfacehttpsknowledgecatonetworkscomdocsremotely-pinging-the-socket-interfacemd` | 0.0000 | 5.19 |

**Latency / cost:** 13531 ms, 15635+630 tokens, $0.002043

## Q19

**Question:** How does the secondary Socket decide to take over in a Socket HA pair, and what does it do right after taking over?

**Answer:**

The secondary Socket takes over when it stops receiving HA keepalive messages from the primary for more than three seconds; it then changes its status to Master. A primary failure can include a general Socket failure or loss of power, loss of VRRP connectivity, or no Internet connectivity for more than ten seconds. A LAN-side connectivity loss by itself does not trigger failover unless VRRP advertisements are exchanged across the LAN link. [kb:what-is-socket-ha#failover-due-to-keepalive-failure] [kb:what-is-socket-ha#failover-due-to-primary-socket-failure]

After taking over, the Cato Cloud shifts traffic from the primary’s tunnels to the secondary’s WAN tunnels. The PoP maintains flow and NAT state to help user applications continue operating through the failover. [kb:what-is-socket-ha#ha-socket-connectivity-to-the-cato-cloud]

I opened ticket TCK-20264272 for you.

**Citations:**
- What is Socket HA › Failover due to Keepalive Failure (`what-is-socket-ha#failover-due-to-keepalive-failure`) https://knowledge.catonetworks.com/docs/what-is-socket-ha
- What is Socket HA › Failover due to Primary Socket Failure (`what-is-socket-ha#failover-due-to-primary-socket-failure`) https://knowledge.catonetworks.com/docs/what-is-socket-ha
- What is Socket HA › HA Socket Connectivity to the Cato Cloud (`what-is-socket-ha#ha-socket-connectivity-to-the-cato-cloud`) https://knowledge.catonetworks.com/docs/what-is-socket-ha

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `what-is-socket-ha#failover-due-to-keepalive-failure` | 0.0149 | 6.27 |
| 2 | `what-is-socket-ha#failover-due-to-primary-socket-failure` | 0.0000 | 6.27 |
| 3 | `what-is-socket-ha#monitoring-socket-high-availability` | 0.0000 | 6.27 |
| 4 | `what-is-socket-ha#showing-the-socket-ha-status` | 0.0000 | 6.27 |
| 5 | `what-is-socket-ha#ha-socket-connectivity-to-the-cato-cloud` | 0.0149 | 5.99 |

**Latency / cost:** 16512 ms, 23565+851 tokens, $0.003144

## Q20

**Question:** What is an HA split-brain condition, how do you recognise it in CMA, and which Socket carries traffic while it lasts?

**Answer:**

A Socket HA split-brain condition is when both the primary and secondary Sockets believe they are Master at the same time. It can happen when a LAN connectivity problem prevents HA keepalive messages from reaching the secondary Socket. [kb:what-is-socket-ha#socket-ha-and-split-brain-condition]

In CMA, check the Socket page: both Sockets appear with status **Master**, **Keepalive** shows **Failed**, and HA **Status** shows **NOT READY**. [kb:what-is-socket-ha#socket-ha-and-split-brain-condition]

While the split-brain condition lasts, the secondary Socket handles site traffic. For downstream traffic, the PoP detects the secondary as Master and prefers its tunnels; for upstream traffic, the secondary sends a GARP message so the LAN updates its ARP and MAC tables to direct traffic to it. [kb:what-is-socket-ha#site-traffic-during-split-brain-condition]

I opened ticket TCK-20264273 for you.

**Citations:**
- What is Socket HA › Socket HA and Split-Brain Condition (`what-is-socket-ha#socket-ha-and-split-brain-condition`) https://knowledge.catonetworks.com/docs/what-is-socket-ha
- What is Socket HA › Site Traffic During Split-Brain Condition (`what-is-socket-ha#site-traffic-during-split-brain-condition`) https://knowledge.catonetworks.com/docs/what-is-socket-ha

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `what-is-socket-ha#site-traffic-during-split-brain-condition` | 0.0164 | 4.64 |
| 2 | `what-is-socket-ha#socket-ha-and-split-brain-condition` | 0.0000 | 4.64 |
| 3 | `what-is-socket-ha#ha-socket-connectivity-to-the-cato-cloud` | 0.0000 | 4.64 |
| 4 | `what-is-socket-ha#ha-socket-connectivity-to-the-cato-cloud` | 0.0000 | 4.64 |
| 5 | `what-is-socket-ha#lan-connectivity-and-socket-ha` | 0.0000 | 4.64 |

**Latency / cost:** 16066 ms, 18908+854 tokens, $0.002563

## Q21

**Question:** Can an X1600 and an X1600 LTE Socket form an HA pair? What about X1500 and X1500B?

**Answer:**

For Socket HA, an X1600 and an X1600 LTE are not a supported pair: the guidance requires the same Socket type and does not support mixing types [kb:what-is-socket-ha#socket-high-availability-and-different-socket-models].

An X1500 and an X1500B are supported together; the supported X1500 combinations include any two X1500 A/B/C models [kb:what-is-socket-ha#socket-high-availability-and-different-socket-models].

I opened ticket TCK-20264274 for you.

**Citations:**
- What is Socket HA › Socket High Availability and Different Socket Models (`what-is-socket-ha#socket-high-availability-and-different-socket-models`) https://knowledge.catonetworks.com/docs/what-is-socket-ha

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `what-is-socket-ha#socket-high-availability-and-different-socket-models` | 0.0164 | 7.71 |
| 2 | `what-is-socket-ha#overview-of-socket-high-availability-for-a-site` | 0.0000 | 7.71 |
| 3 | `what-is-socket-ha#understanding-socket-high-availability-and-failover` | 0.0000 | 7.71 |
| 4 | `what-is-socket-ha#understanding-socket-high-availability-and-failover` | 0.0000 | 7.71 |
| 5 | `what-is-socket-ha#sample-socket-ha-failover` | 0.0000 | 7.71 |

**Latency / cost:** 17501 ms, 23639+996 tokens, $0.003226

## Q22

**Question:** What are the prerequisites for triggering a manual HA failover from CMA, and what status is expected about two minutes later?

**Answer:**

Before triggering manual HA failover in CMA, confirm that both Sockets are running Socket version 24 or higher and that the HA state is **Ready** [kb:manually-activate-socket-ha-failover#prerequisites]. Ensure onsite Socket personnel are available in case physical access is needed [kb:manually-activate-socket-ha-failover#overview].

In CMA, select **Socket > Actions > Activate Manual HA Failover**. Wait approximately 120 seconds, then refresh the Socket page [kb:manually-activate-socket-ha-failover#activating-manual-ha-failover]. The expected status is **Not Ready (In HA Failover)**; both Sockets may appear as Master, indicating the Secondary has taken over. This is expected during manual failover [kb:manually-activate-socket-ha-failover#how-manual-failover-works].

Do not leave the site in manual failover longer than necessary; deactivate manual failover to return control to the Primary Socket [kb:manually-activate-socket-ha-failover#best-practices] [kb:manually-activate-socket-ha-failover#reverting-to-the-primary-socket].

**Citations:**
- Manually Activate Socket HA Failover › Prerequisites (`manually-activate-socket-ha-failover#prerequisites`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover
- Manually Activate Socket HA Failover › Overview (`manually-activate-socket-ha-failover#overview`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover
- Manually Activate Socket HA Failover › Activating Manual HA Failover (`manually-activate-socket-ha-failover#activating-manual-ha-failover`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover
- Manually Activate Socket HA Failover › How Manual Failover Works (`manually-activate-socket-ha-failover#how-manual-failover-works`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover
- Manually Activate Socket HA Failover › Best Practices (`manually-activate-socket-ha-failover#best-practices`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover
- Manually Activate Socket HA Failover › Reverting to the Primary Socket (`manually-activate-socket-ha-failover#reverting-to-the-primary-socket`) https://knowledge.catonetworks.com/docs/manually-activate-socket-ha-failover

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `manually-activate-socket-ha-failover#how-manual-failover-works` | 0.0156 | 6.61 |
| 2 | `manually-activate-socket-ha-failover#best-practices` | 0.0000 | 6.61 |
| 3 | `manually-activate-socket-ha-failover#activating-manual-ha-failover` | 0.0000 | 6.61 |
| 4 | `manually-activate-socket-ha-failover#overview` | 0.0302 | 6.55 |
| 5 | `manually-activate-socket-ha-failover#prerequisites` | 0.0164 | 5.51 |

**Latency / cost:** 19674 ms, 17362+1114 tokens, $0.002500

## Q23

**Question:** Which conditions generate an 'HA Not Ready' connectivity event, and when is 'HA Ready' generated afterwards?

**Answer:**

The documentation lists these conditions for a Socket HA Not Ready indication: Connected is not ready for 5 minutes; Keepalive is not ready for 60 minutes; Compatible version is not ready for 60 minutes; or failover to the secondary Socket persists for 60 minutes [kb:reviewing-site-operations-stories#site-operations-story-indications]. The HA troubleshooting overview also identifies a Socket disconnected from Cato, incompatible Socket versions, and HA keepalive failure as scenarios associated with Not Ready status [kb:xops-network-playbook-ha-status-is-not-ready#overview].

The retrieved guidance does not specify the condition or timing for a follow-up “HA Ready” connectivity event, so I can’t confirm when that event is generated from these materials [kb:reviewing-site-operations-stories#site-operations-story-indications]. I’ve opened a support case to have the event behavior checked, and am routing this question to a support specialist because the available product guidance does not answer that part.

I opened ticket TCK-20264275 for you.

**Citations:**
- Reviewing Site Operations Stories › Site Operations Story Indications (`reviewing-site-operations-stories#site-operations-story-indications`) https://knowledge.catonetworks.com/docs/reviewing-site-operations-stories
- XOps Network Playbook - HA Status Is Not Ready › Overview (`xops-network-playbook-ha-status-is-not-ready#overview`) https://knowledge.catonetworks.com/docs/xops-network-playbook-ha-status-is-not-ready

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `reviewing-site-operations-stories#site-operations-story-indications` | 0.0274 | 6.73 |
| 2 | `reviewing-site-operations-stories#site-operations-story-indications` | 0.0000 | 6.73 |
| 3 | `reviewing-site-operations-stories#understanding-the-site-operations-story-lifecycle` | 0.0000 | 6.73 |
| 4 | `reviewing-site-operations-stories#understanding-the-site-operations-story-lifecycle` | 0.0000 | 6.73 |
| 5 | `reviewing-site-operations-stories#example-use-case` | 0.0000 | 6.73 |

**Latency / cost:** 21368 ms, 19861+1260 tokens, $0.002471

## Q24

**Question:** After how long is a 'Disconnected' connectivity event generated for an active link, and after how long is 'Connected' generated?

**Answer:**

For an active link, a **Disconnected** event is generated after the tunnel to the PoP has been disconnected for more than 2.5 minutes. A **Connected** event is generated after the tunnel has been connected to the PoP for 30 seconds, provided the link role is Active (precedence 1). [kb:monitoring-your-site-with-connectivity-events#overview-of-connectivity-event-types]

One exception: if the link reconnects within 2.5 minutes of a disconnection, the event is **Reconnected** rather than **Connected**. [kb:monitoring-your-site-with-connectivity-events#overview-of-connectivity-event-types]

I opened ticket TCK-20264276 for you.

**Citations:**
- Monitoring Your Site with Connectivity Events › Overview of Connectivity Event Types (`monitoring-your-site-with-connectivity-events#overview-of-connectivity-event-types`) https://knowledge.catonetworks.com/docs/monitoring-your-site-with-connectivity-events

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `monitoring-your-site-with-connectivity-events#overview-of-connectivity-event-types` | 0.0315 | 4.84 |
| 2 | `monitoring-your-site-with-connectivity-events#sites-with-multiple-links` | 0.0000 | 4.84 |
| 3 | `monitoring-your-site-with-connectivity-events#overview-of-connectivity-event-types` | 0.0000 | 4.84 |
| 4 | `monitoring-your-site-with-connectivity-events#enabling-connectivity-alerts` | 0.0000 | 4.84 |
| 5 | `working-with-link-health-rules#configuring-a-connectivity-health-rule` | 0.0325 | 3.72 |

**Latency / cost:** 16180 ms, 19243+781 tokens, $0.002569

## Q25

**Question:** When all active links have unacceptable SLA, how does the Socket evaluate moving to another PoP, and how long does the evaluation take?

**Answer:**

During the evaluation period, the Socket first uses its remedy actions: in active/active mode, new flows use the best-quality link and existing flows gradually move to it; in active/passive mode, the passive link is activated and flows shift over gradually. If those actions do not resolve the issue and all active links still have unacceptable SLA, the Socket connects to a different PoP. [kb:understanding-acceptable-and-unacceptable-sla-for-sites#example-of-remedy-actions-for-unacceptable-sla] [kb:understanding-acceptable-and-unacceptable-sla-for-sites#example-of-connecting-to-a-different-pop-for-unacceptable-connectivity-sla]

At each new PoP, the Socket runs an initial SLA evaluation that takes **40–50 seconds**: the SLA is checked every **10 seconds** during a **40-second** evaluation period, accounting for the 40–50-second total. If the links meet acceptable SLA, the Socket stays on that PoP; if not, it tries another PoP and repeats the evaluation. If it cannot find a PoP with acceptable SLA, it returns to the original PoP. This behavior applies to both active/active and active/passive deployments. [kb:understanding-acceptable-and-unacceptable-sla-for-sites#example-of-connecting-to-a-different-pop-for-unacceptable-connectivity-sla]

I opened ticket TCK-20264277 for you.

**Citations:**
- Understanding Acceptable and Unacceptable SLA for Sites › Example of Remedy Actions for Unacceptable SLA (`understanding-acceptable-and-unacceptable-sla-for-sites#example-of-remedy-actions-for-unacceptable-sla`) https://knowledge.catonetworks.com/docs/understanding-acceptable-and-unacceptable-sla-for-sites
- Understanding Acceptable and Unacceptable SLA for Sites › Example of Connecting to a Different PoP for Unacceptable Connectivity SLA (`understanding-acceptable-and-unacceptable-sla-for-sites#example-of-connecting-to-a-different-pop-for-unacceptable-connectivity-sla`) https://knowledge.catonetworks.com/docs/understanding-acceptable-and-unacceptable-sla-for-sites

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `understanding-acceptable-and-unacceptable-sla-for-sites#example-of-connecting-to-a-different-pop-for-unacceptable-connectivity-sla` | 0.0328 | 8.32 |
| 2 | `understanding-acceptable-and-unacceptable-sla-for-sites#example-of-remedy-actions-for-unacceptable-sla` | 0.0000 | 8.32 |
| 3 | `understanding-acceptable-and-unacceptable-sla-for-sites#example-of-connecting-to-a-different-pop-for-unacceptable-connectivity-sla` | 0.0000 | 8.32 |
| 4 | `understanding-acceptable-and-unacceptable-sla-for-sites#reconnecting-to-the-original-pop` | 0.0000 | 8.32 |
| 5 | `understanding-acceptable-and-unacceptable-sla-for-sites#example-of-remedy-actions-for-unacceptable-sla` | 0.0159 | 6.29 |

**Latency / cost:** 20438 ms, 19905+1274 tokens, $0.002898

## Q26

**Question:** What does Last Mile Monitoring probe by default, how many probes can a rule carry, and what is the default probe interval?

**Answer:**

By default, Last Mile Monitoring checks ISP-link quality to **facebook.com, google.com, and amazon.com**; predefined probes also cover several destinations in China and globally. [kb:last-mile-monitoring-probes-and-connectivity#overview] [kb:last-mile-monitoring-probes-and-connectivity#define-a-probe]

A policy rule can carry **up to 5 probes** (and must have at least one). [kb:last-mile-monitoring-probes-and-connectivity#configure-a-last-mile-monitoring-policy-rule]

The default probe interval is **60 seconds**. [kb:last-mile-monitoring-probes-and-connectivity#define-a-probe]

I opened ticket TCK-20264278 for you.

**Citations:**
- Last Mile Monitoring Probes and Connectivity › Overview (`last-mile-monitoring-probes-and-connectivity#overview`) https://knowledge.catonetworks.com/docs/last-mile-monitoring-probes-and-connectivity
- Last Mile Monitoring Probes and Connectivity › Define a Probe (`last-mile-monitoring-probes-and-connectivity#define-a-probe`) https://knowledge.catonetworks.com/docs/last-mile-monitoring-probes-and-connectivity
- Last Mile Monitoring Probes and Connectivity › Configure a Last Mile Monitoring Policy Rule (`last-mile-monitoring-probes-and-connectivity#configure-a-last-mile-monitoring-policy-rule`) https://knowledge.catonetworks.com/docs/last-mile-monitoring-probes-and-connectivity

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `last-mile-monitoring-probes-and-connectivity#define-a-probe` | 0.0299 | 4.09 |
| 2 | `last-mile-monitoring-probes-and-connectivity#configuring-the-last-mile-monitoring-probe-policy` | 0.0000 | 4.09 |
| 3 | `last-mile-monitoring-probes-and-connectivity#configure-a-last-mile-monitoring-policy-rule` | 0.0000 | 4.09 |
| 4 | `last-mile-monitoring-probes-and-connectivity#overview` | 0.0139 | 2.20 |
| 5 | `last-mile-monitoring-probes-and-connectivity#enabling-the-last-mile-monitoring-probes-policy` | 0.0304 | 1.63 |

**Latency / cost:** 13360 ms, 9834+735 tokens, $0.001373

## Q27

**Question:** Which KPIs can a Link Quality rule monitor, and what should you export from a Link Quality SLA story to raise a case with the ISP?

**Answer:**

A Link Quality rule can monitor packet loss, jitter, latency, and congestion. [kb:xops-network-playbook-link-quality-sla#overview]

For an ISP case, open the Link quality SLA story in Stories Workbench, then use its **Actions** menu and choose **Export data to ISP template**. Select the incident by its timestamp and the relevant link, then click **Retrieve**. The results include Traceroute and ICMP test data; you can copy the retrieved data from the Underlay Raw Data panel to share with the ISP. [kb:retrieving-diagnostic-data-with-site-operations-story-actions#retrieving-and-exporting-traceroute-and-icmp-results]

I opened ticket TCK-20264279 for you.

**Citations:**
- XOps Network Playbook - Link Quality SLA › Overview (`xops-network-playbook-link-quality-sla#overview`) https://knowledge.catonetworks.com/docs/xops-network-playbook-link-quality-sla
- Retrieving Diagnostic Data with Site Operations Story Actions › Retrieving and Exporting Traceroute and ICMP Results (`retrieving-diagnostic-data-with-site-operations-story-actions#retrieving-and-exporting-traceroute-and-icmp-results`) https://knowledge.catonetworks.com/docs/retrieving-diagnostic-data-with-site-operations-story-actions

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `xops-network-playbook-link-quality-sla#overview` | 0.0308 | 4.70 |
| 2 | `xops-network-playbook-link-quality-sla#[REDACTED:HIGH_ENTROPY]` | 0.0000 | 4.70 |
| 3 | `xops-network-playbook-link-quality-sla#[REDACTED:HIGH_ENTROPY]` | 0.0000 | 4.70 |
| 4 | `xops-network-playbook-link-quality-sla#reviewing-site-network-analytics` | 0.0000 | 4.70 |
| 5 | `xops-network-playbook-link-quality-sla#[REDACTED:HIGH_ENTROPY]` | 0.0000 | 4.70 |

**Latency / cost:** 13288 ms, 18744+610 tokens, $0.002421

## Q28

**Question:** After a Socket upgrade the site is down and events show 'No open tunnel after grace time'. How long is the grace period, and what must be done before rebooting the Socket?

**Answer:**

The “No open tunnel after grace time” upgrade event means the Socket was reported offline after the 17-minute upgrade period ended [kb:socket-upgrade-failure-troubleshooting#analyzing-cma-events-15]. Separately, after firmware installation the Socket has a 10-minute stability-check period; it needs to maintain internet access during that period [kb:socket-upgrade-failure-troubleshooting#troubleshooting-failures-after-the-upgrade].

Before rebooting, collect and save the Socket’s console logs whenever possible. On physical Sockets, the logs are lost after reboot, and they are important for root-cause analysis [kb:socket-upgrade-failure-troubleshooting#resolving-inaccessible-socket-after-an-upgrade] [kb:xops-network-playbook-socket-offline-after-upgrade#step-3---resolving-socket-inaccessible-after-an-upgrade].

The latest anomaly telemetry says “Packet loss 31% on WAN1 for 2 minutes [link=WAN1]” at 13:00Z on August 28, while the latest status snapshots for both tracked sites say “connected” at 16:59:30Z [telemetry:get_events] [telemetry:get_site_status].

Which site is affected?

I opened ticket TCK-20264280 for you.

**Citations:**
- Socket Upgrade Failure Troubleshooting › Analyzing CMA Events (`socket-upgrade-failure-troubleshooting#analyzing-cma-events-15`) https://knowledge.catonetworks.com/docs/socket-upgrade-failure-troubleshooting
- Socket Upgrade Failure Troubleshooting › Troubleshooting Failures After the Upgrade (`socket-upgrade-failure-troubleshooting#troubleshooting-failures-after-the-upgrade`) https://knowledge.catonetworks.com/docs/socket-upgrade-failure-troubleshooting
- Socket Upgrade Failure Troubleshooting › Resolving Inaccessible Socket after an Upgrade (`socket-upgrade-failure-troubleshooting#resolving-inaccessible-socket-after-an-upgrade`) https://knowledge.catonetworks.com/docs/socket-upgrade-failure-troubleshooting
- XOps Network Playbook - Socket Offline After Upgrade › Step 3 - Resolving Socket Inaccessible after an upgrade (`xops-network-playbook-socket-offline-after-upgrade#step-3---resolving-socket-inaccessible-after-an-upgrade`) https://knowledge.catonetworks.com/docs/xops-network-playbook-socket-offline-after-upgrade

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `socket-upgrade-failure-troubleshooting#analyzing-cma-events-15` | 0.0161 | 8.04 |
| 2 | `socket-upgrade-failure-troubleshooting#manual-socket-upgrade-and-rescheduling` | 0.0000 | 8.04 |
| 3 | `socket-upgrade-failure-troubleshooting#cma-manual-upgrade` | 0.0000 | 8.04 |
| 4 | `socket-upgrade-failure-troubleshooting#resolving-inaccessible-socket-after-an-upgrade` | 0.0000 | 8.04 |
| 5 | `socket-upgrade-failure-troubleshooting#resolving-inaccessible-socket-after-an-upgrade` | 0.0000 | 8.04 |

**Latency / cost:** 46676 ms, 57552+3643 tokens, $0.006492

## Q29

**Question:** What connectivity requirement about upstream TLS inspection applies to Socket upgrades, and which ports must be connected for a gradual upgrade on an X1700?

**Answer:**

For Socket upgrades, HTTPS traffic from the Socket’s WAN IP must be excluded from upstream SSL/TLS inspection; otherwise the upgrade can fail. [kb:connectivity-requirements-for-socket-upgrades#connectivity-requirements-for-socket-upgrades-1]

For a gradual X1700 upgrade, connect **Port 1** or **Port 9** (if the add-on card is installed) to the Cato Cloud. [kb:connectivity-requirements-for-socket-upgrades#connectivity-requirements-for-socket-upgrades-1]

I opened ticket TCK-20264281 for you.

**Citations:**
- Connectivity Requirements for Socket Upgrades › Connectivity Requirements for Socket Upgrades (`connectivity-requirements-for-socket-upgrades#connectivity-requirements-for-socket-upgrades-1`) https://knowledge.catonetworks.com/docs/connectivity-requirements-for-socket-upgrades

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `connectivity-requirements-for-socket-upgrades#connectivity-requirements-for-socket-upgrades-1` | 0.0306 | 6.73 |
| 2 | `connectivity-requirements-for-socket-upgrades#connectivity-requirements-for-socket-upgrades` | 0.0000 | 6.73 |
| 3 | `socket-version-25-0-release-notes#resolved-issues` | 0.0149 | 3.79 |
| 4 | `socket-version-25-0-release-notes#resolved-issues` | 0.0000 | 3.79 |
| 5 | `socket-version-25-0-release-notes#resolved-issues` | 0.0000 | 3.79 |

**Latency / cost:** 23229 ms, 18428+694 tokens, $0.002424

## Q30

**Question:** A pinned banking app breaks with TLS inspection on. What does Cato recommend, and which operating systems are bypassed from TLS inspection automatically?

**Answer:**

For a banking app that uses certificate pinning, Cato recommends a narrowly scoped TLS Inspection bypass for the app rather than disabling inspection globally. You can first test with a bypass for one user or source IP; if the app works, add a targeted exclusion for its domain/FQDN. If the app enforces pinning or strict TLS requirements, TLS Inspection cannot be applied to that traffic, so leave it bypassed. [kb:tls-inspection-troubleshooting#troubleshooting-failing-application] [kb:best-practices-for-tls-inspection#how-to-handle-applications-that-use-certificate-pinning]

TLS Inspection is bypassed by default for Android, Linux, and unidentified/unknown operating systems. [kb:best-practices-for-tls-inspection#excluding-items-from-tls-inspection]

I opened ticket TCK-20264282 for you.

**Citations:**
- TLS Inspection Troubleshooting › Troubleshooting Failing Application (`tls-inspection-troubleshooting#troubleshooting-failing-application`) https://knowledge.catonetworks.com/docs/tls-inspection-troubleshooting
- Best Practices for TLS Inspection › How to Handle Applications that Use Certificate Pinning? (`best-practices-for-tls-inspection#how-to-handle-applications-that-use-certificate-pinning`) https://knowledge.catonetworks.com/docs/best-practices-for-tls-inspection
- Best Practices for TLS Inspection › Excluding Items from TLS Inspection (`best-practices-for-tls-inspection#excluding-items-from-tls-inspection`) https://knowledge.catonetworks.com/docs/best-practices-for-tls-inspection

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `best-practices-for-tls-inspection#excluding-items-from-tls-inspection` | 0.0308 | 7.25 |
| 2 | `best-practices-for-tls-inspection#decrypting-traffic-with-cato-certificate` | 0.0000 | 7.25 |
| 3 | `best-practices-for-tls-inspection#enabling-tls-inspection-to-improve-security` | 0.0000 | 7.25 |
| 4 | `tls-inspection-troubleshooting#troubleshooting-os-specific-tls-issues-expected-limitations` | 0.0269 | 7.24 |
| 5 | `tls-inspection-troubleshooting#unsupported-protocols-and-legacy-systems` | 0.0000 | 7.24 |

**Latency / cost:** 14185 ms, 24162+716 tokens, $0.003154

## Q31

**Question:** Users see certificate warnings when opening blocked HTTPS sites even though TLS inspection is disabled. Why, and what fixes it?

**Answer:**

This is expected for blocked HTTPS sites: Cato intercepts the TLS connection so it can display the block page, even when TLS Inspection is disabled. If the Cato Certificate is not trusted by the user’s computer or browser, the browser warns about the certificate instead of showing the block page. [kb:certificate-warnings-with-blocked-https-websites#certificate-warnings-with-blocked-https-websites-1]

To fix the warning while keeping the site blocked, install the Cato Certificate on the affected users’ computers or browsers. See [How to Install the Cato Certificate](https://knowledge.catonetworks.com/v1/docs/how-to-install-the-cato-certificate). [kb:certificate-warnings-with-blocked-https-websites#certificate-warnings-with-blocked-https-websites-1]

I opened ticket TCK-20264283 for you.

**Citations:**
- Certificate Warnings with Blocked HTTPS Websites › Certificate Warnings with Blocked HTTPS Websites (`certificate-warnings-with-blocked-https-websites#certificate-warnings-with-blocked-https-websites-1`) https://knowledge.catonetworks.com/docs/certificate-warnings-with-blocked-https-websites

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `certificate-warnings-with-blocked-https-websites#certificate-warnings-with-blocked-https-websites-1` | 0.0271 | 8.00 |
| 2 | `certificate-warnings-with-blocked-https-websites#certificate-warnings-with-blocked-https-websites-1` | 0.0000 | 8.00 |
| 3 | `accessing-an-untrusted-website-is-blocked-even-though-tls-inspection-is-disabled#troubleshooting` | 0.0156 | 6.27 |
| 4 | `accessing-an-untrusted-website-is-blocked-even-though-tls-inspection-is-disabled#environment` | 0.0000 | 6.27 |
| 5 | `accessing-an-untrusted-website-is-blocked-even-though-tls-inspection-is-disabled#troubleshooting` | 0.0000 | 6.27 |

**Latency / cost:** 16602 ms, 15043+1053 tokens, $0.002183

## Q32

**Question:** How do IPS allowlist rules differ from firewall rules in matching, and how can a rule be created directly from a block event?

**Answer:**

IPS allowlist matching differs from firewall matching: every IPS allowlist rule that matches is applied, so a connection matching multiple rules can generate a separate event for each matching rule. WAN and Internet firewall rules are evaluated in order; the first matching rule determines the action, and evaluation stops there. [kb:allowlisting-ips-signatures#working-with-the-ips-allowlist-rulebase] [kb:recommendations-for-internet-and-wan-firewall-policies#ordering-the-firewall-rules]

To create an IPS allowlist rule from a block event:
1. Go to **Home > Events**, select the **IPS** preset, find and expand the event for the blocked traffic.
2. Click the linked signature ID to open **New Allow List**. Its settings are based on the event data.
3. Review the rule. Its **Scope** matches the event’s traffic direction and cannot be changed. In **Track**, you can choose whether to generate an event and email notification when the signature is allowed.
4. Click **Save**. The rule is added to the IPS allowlist rulebase; you can view it under **Security > IPS > Allow List**. [kb:allowlisting-ips-signatures#creating-an-ips-allowlist-rule-from-a-block-event]

I’ve opened a support ticket to track your question.

I opened ticket TCK-20264284 for you.

**Citations:**
- Allowlisting IPS Signatures › Working with the IPS Allowlist Rulebase (`allowlisting-ips-signatures#working-with-the-ips-allowlist-rulebase`) https://knowledge.catonetworks.com/docs/allowlisting-ips-signatures
- Recommendations for Internet and WAN Firewall Policies › Ordering the Firewall Rules (`recommendations-for-internet-and-wan-firewall-policies#ordering-the-firewall-rules`) https://knowledge.catonetworks.com/docs/recommendations-for-internet-and-wan-firewall-policies
- Allowlisting IPS Signatures › Creating an IPS Allowlist Rule from a Block Event (`allowlisting-ips-signatures#creating-an-ips-allowlist-rule-from-a-block-event`) https://knowledge.catonetworks.com/docs/allowlisting-ips-signatures

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `allowlisting-ips-signatures#creating-an-ips-allowlist-rule-from-a-block-event` | 0.0323 | 10.08 |
| 2 | `allowlisting-ips-signatures#creating-an-ips-allowlist-rule-from-a-block-event` | 0.0000 | 10.08 |
| 3 | `allowlisting-ips-signatures#managing-ips-allowlist-rules` | 0.0000 | 10.08 |
| 4 | `allowlisting-ips-signatures#showing-the-ips-allowlist-rulebase` | 0.0000 | 10.08 |
| 5 | `customizing-the-dns-protections-for-ips#allowlisting-dns-traffic` | 0.0147 | 9.28 |

**Latency / cost:** 15697 ms, 24138+1021 tokens, $0.003301

## Q33

**Question:** How many egress public IPs are included in an account's default license, and what does Cato recommend for VoIP egress rules?

**Answer:**

The default account license includes 3 unique Cato-allocated public IPs, usable by any PoP. You can allocate them under **Network > IP Allocation**; if you need additional IPs, contact your partner or Sales Engineer. [kb:how-to-configure-a-network-rule-to-egress-traffic#allocating-ips-for-your-account]

For VoIP, Cato recommends a network rule with a NAT IP so SIP call setup and RTP voice traffic use the same egress IP; for RingCentral, choose a Cato PoP physically closest to a RingCentral PoP. The guide also recommends enabling Packet Loss Mitigation for that RingCentral rule. [kb:how-to-integrate-ringcentral-with-cato-networks#configuring-a-network-rule]

If SIP traffic must always use the same egress IP, enable **Preferred IP for SIP Traffic** in account advanced settings. For another VoIP protocol that requires a consistent egress IP, contact Cato Support. [kb:network-rule-evaluation-troubleshooting#egress-pop-selection-change]

I opened ticket TCK-20264285 for you.

**Citations:**
- How to Configure a Network Rule to Egress Traffic › Allocating IPs for your Account (`how-to-configure-a-network-rule-to-egress-traffic#allocating-ips-for-your-account`) https://knowledge.catonetworks.com/docs/how-to-configure-a-network-rule-to-egress-traffic
- How to Integrate RingCentral with Cato Networks › Configuring a Network Rule (`how-to-integrate-ringcentral-with-cato-networks#configuring-a-network-rule`) https://knowledge.catonetworks.com/docs/how-to-integrate-ringcentral-with-cato-networks
- Network Rule Evaluation Troubleshooting › Egress PoP Selection Change (`network-rule-evaluation-troubleshooting#egress-pop-selection-change`) https://knowledge.catonetworks.com/docs/network-rule-evaluation-troubleshooting

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `how-to-configure-a-network-rule-to-egress-traffic#allocating-ips-for-your-account` | 0.0164 | 7.52 |
| 2 | `how-to-configure-a-network-rule-to-egress-traffic#configuring-a-network-rule-to-egress-traffic` | 0.0000 | 7.52 |
| 3 | `how-to-configure-a-network-rule-to-egress-traffic#egressing-traffic-for-static-hosts-optional` | 0.0000 | 7.52 |
| 4 | `how-to-configure-a-network-rule-to-egress-traffic#egressing-traffic-for-static-hosts-optional` | 0.0000 | 7.52 |
| 5 | `how-to-configure-a-network-rule-to-egress-traffic#configuring-a-network-rule-to-egress-traffic-to-a-static-ip` | 0.0000 | 7.52 |

**Latency / cost:** 16736 ms, 24611+963 tokens, $0.003331

## Q34

**Question:** How long is a Cato MFA token valid, and when does Cato ask for the code again on a trusted device?

**Answer:**

A Cato MFA code is based on a 30-second time window, with an approximately 3½-minute grace period to give you time to enter it. A code requested again within the same 30-second window may be the same; a request in the next window may return a different code. [kb:how-cato-mfa-and-expiration-mechanism-works#how-cato-mfa-and-expiration-mechanism-works-1]

On a trusted device, Cato asks for the code again when the configured Token Validity duration expires, or if the device’s geolocation changes to a different country. The duration is configured by an administrator in the authentication policy; with Always Prompt, MFA is required whenever the user connects. [kb:configuring-the-authentication-policy-for-cato-clients#configuring-the-authentication-policy-for-all-users] A device is trusted when the user selects “Don’t ask me again on this device/computer” during sign-in. [kb:managing-sdp-clients-with-the-cato-user-portal#working-with-trusted-devices]

I opened ticket TCK-20264286 for you.

**Citations:**
- How Cato MFA and Expiration Mechanism Works › How Cato MFA and Expiration Mechanism Works (`how-cato-mfa-and-expiration-mechanism-works#how-cato-mfa-and-expiration-mechanism-works-1`) https://knowledge.catonetworks.com/docs/how-cato-mfa-and-expiration-mechanism-works
- Configuring the Authentication Policy for Cato Clients › Configuring the Authentication Policy for All Users (`configuring-the-authentication-policy-for-cato-clients#configuring-the-authentication-policy-for-all-users`) https://knowledge.catonetworks.com/docs/configuring-the-authentication-policy-for-cato-clients
- Managing SDP Clients with the Cato User Portal › Working with Trusted Devices (`managing-sdp-clients-with-the-cato-user-portal#working-with-trusted-devices`) https://knowledge.catonetworks.com/docs/managing-sdp-clients-with-the-cato-user-portal

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `managing-sdp-clients-with-the-cato-user-portal#working-with-trusted-devices` | 0.0328 | 6.13 |
| 2 | `managing-sdp-clients-with-the-cato-user-portal#resetting-the-password-with-multiple-accounts` | 0.0000 | 6.13 |
| 3 | `managing-sdp-clients-with-the-cato-user-portal#showing-the-trusted-devices` | 0.0000 | 6.13 |
| 4 | `managing-sdp-clients-with-the-cato-user-portal#changing-the-mfa-settings` | 0.0000 | 6.13 |
| 5 | `configuring-the-authentication-policy-for-cato-clients#configuring-the-authentication-policy-for-all-users` | 0.0308 | 6.07 |

**Latency / cost:** 16415 ms, 22459+1037 tokens, $0.003099

## Q35

**Question:** Scheduled SCIM provisioning failed overnight. What are the playbook's three troubleshooting moves?

**Answer:**

The playbook describes three high-level moves: verify that the SCIM sync failure is still occurring, troubleshoot the cause, then confirm that the issue is resolved [kb:xops-network-playbook-scim-provisioning-failed#overview] [kb:xops-network-playbooks-1#xops-network-playbook---scim-provisioning-failedhttpsknowledgecatonetworkscomdocsxops-network-playbook-scim-provisioning-failedmd].

1. **Verify the failure:** Check the Stories Workbench using the Network Operations preset and the “Indication Contains SCIM” filter, then inspect the story details; alternatively, check the Event Dashboard for SCIM Provisioning events marked Failed [kb:xops-network-playbook-scim-provisioning-failed#using-the-story-drill-down] [kb:xops-network-playbook-scim-provisioning-failed#using-the-event].
2. **Troubleshoot:** Run a provision-on-demand test from your IdP for an assigned user or group. If it succeeds, check whether a provider interruption or Cato maintenance coincided with the scheduled sync; if it fails too, review recent configuration changes [kb:xops-network-playbook-scim-provisioning-failed#perform-on-demand-provisioning].
3. **Confirm resolution:** Verify that the SCIM sync is no longer failing and the issue is resolved [kb:xops-network-playbook-scim-provisioning-failed#overview]. The material available here gives these high-level stages, but not enough detail to verify every item in a complete three-move workflow.

I opened ticket TCK-20264287 for you.

**Citations:**
- XOps Network Playbook - SCIM Provisioning Failed › Overview (`xops-network-playbook-scim-provisioning-failed#overview`) https://knowledge.catonetworks.com/docs/xops-network-playbook-scim-provisioning-failed
- XOps Network Playbooks › [XOps Network Playbook - SCIM Provisioning Failed](https://knowledge.catonetworks.com/docs/xops-network-playbook-scim-provisioning-failed.md) (`xops-network-playbooks-1#xops-network-playbook---scim-provisioning-failedhttpsknowledgecatonetworkscomdocsxops-network-playbook-scim-provisioning-failedmd`) https://knowledge.catonetworks.com/docs/xops-network-playbooks-1
- XOps Network Playbook - SCIM Provisioning Failed › Using the Story Drill-down (`xops-network-playbook-scim-provisioning-failed#using-the-story-drill-down`) https://knowledge.catonetworks.com/docs/xops-network-playbook-scim-provisioning-failed
- XOps Network Playbook - SCIM Provisioning Failed › Using the Event (`xops-network-playbook-scim-provisioning-failed#using-the-event`) https://knowledge.catonetworks.com/docs/xops-network-playbook-scim-provisioning-failed
- XOps Network Playbook - SCIM Provisioning Failed › Perform On-Demand Provisioning (`xops-network-playbook-scim-provisioning-failed#perform-on-demand-provisioning`) https://knowledge.catonetworks.com/docs/xops-network-playbook-scim-provisioning-failed

**Top retrieved chunks:**

| Rank | Passage | RRF | Rerank |
|---|---|---|---|
| 1 | `xops-network-playbook-scim-provisioning-failed#[REDACTED:HIGH_ENTROPY]` | 0.0164 | 7.28 |
| 2 | `xops-network-playbook-scim-provisioning-failed#overview` | 0.0000 | 7.28 |
| 3 | `xops-network-playbook-scim-provisioning-failed#[REDACTED:HIGH_ENTROPY]` | 0.0000 | 7.28 |
| 4 | `xops-network-playbook-scim-provisioning-failed#using-the-story-drill-down` | 0.0000 | 7.28 |
| 5 | `xops-network-playbook-scim-provisioning-failed#using-the-event` | 0.0000 | 7.28 |

**Latency / cost:** 35569 ms, 45434+2531 tokens, $0.004733
