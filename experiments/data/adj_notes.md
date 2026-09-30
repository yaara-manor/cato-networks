# ADJ verification notes

Method: SQL text searches over `passages.body` (ilike / regex `~*`, 14,109 passages) for the distinctive terms of each
question, read the nearest hits, plus a look at the top-3 of R0 (lexical) and R3 (current pipeline) for each question.
"Near-miss" = the KB has a generic article on the topic but nothing that answers the specific ask.

| id | question (short) | searches (hits) | verdict |
|----|------------------|-----------------|---------|
| ADJ01 | Ubiquiti UniFi Dream Machine Pro IKEv2 tunnel to Cato | `Ubiquiti` 0, `Dream Machine` 0. Near-miss: generic IKEv2 site and other vendors' (Cisco, Fortigate, VMware Edge) IPsec guides | unanswerable |
| ADJ02 | list price per Mbps, 500 Mbps, 3-year | `per Mbps` 0, `discount` 0, `price` 2 (shipping "Quote ID" field; Cloud Interconnect "fixed-price" remark), `\$ ?[0-9]+` 1 (a CLI snippet). Product catalog and license articles describe license types, no prices | unanswerable |
| ADJ03 | Socket X1900 release date / 100G WAN | `X1900` 0, `X1800\|X2000\|X2500` 0. KB has X1500/X1600/X1700 only (X1700C 2x100G add-on, but no X1900, no roadmap) | unanswerable |
| ADJ04 | SonicWall NSa 3700 IKEv2 to Cato | `SonicWall` 0 (the `NSa` ilike hits are substrings of other words). Near-miss: Fortigate/Cisco guides | unanswerable |
| ADJ05 | early termination fee on cancel | `early termination` 0, `termination fee\|penalt\|early exit` 0, `minimum term` 0. `cancel` (11) are UI cancel buttons; `renewal` hits cover Socket hardware refresh only. product-specific-terms covers ILMM/ZTNA/hardware delivery, no cancellation fees | unanswerable |
| ADJ06 | MikroTik RouterOS v7 BGP to Socket | `MikroTik\|RouterOS` 0. Near-miss: generic Socket BGP neighbor article (vendor-neutral, no RouterOS syntax) | unanswerable |
| ADJ07 | Juniper SRX chassis cluster behind Socket HA | `SRX\|Junos` 0, `chassis` 1 (unrelated). `Juniper` hits are Juniper Mist AP events only. Near-miss: what-is-socket-ha | unanswerable |
| ADJ08 | X1600 Wi-Fi max EIRP / antenna gain dBi | `dBi\|EIRP` 0; `dBm` hits are client RSSI scoring and cellular signal tables; antenna hits are LTE/5G antenna kit catalog lines. X1600 WiFi FAQ gives Wi-Fi 6, 2.4+5 GHz, 4 SSIDs only (this is why an earlier draft "Wi-Fi 7 / 6 GHz" was REJECTED: the FAQ answers it) | unanswerable |
| ADJ09 | exact ML-KEM parameter set (512/768/1024) for Client PQC | `ML-?KEM\|Kyber` 0; in the PQC articles (`what-is-pqc-for-the-cato-client`, `-for-ipsec-tunnels`) `512\|768\|1024\|X25519\|Kyber\|lattice` 0 hits: they only say "post-quantum key exchange". An earlier draft asking "when will PQC ship for the Client" was REJECTED: PQC for Client exists (Windows v6.0+) | unanswerable (strong near-miss, topic covered, parameter set not) |
| ADJ10 | Windows Client 9.2 release notes | Windows Client versions in the KB are 4.7 .. 6.16 (regex `Windows Client (v\|version )?N.N`); no 9.x. Near-miss: client release summaries / EOS policy | unanswerable (version does not exist) |
| ADJ11 | Barracuda CloudGen F-Series IPsec to Cato | `Barracuda\|CloudGen` 0. Near-miss: Fortigate/Cisco guides | unanswerable |
| ADJ12 | PoP locations scheduled for Q1 2027 | `Q[1-4] 2027\|in 2027` 0, `X PoP will open/scheduled` hits are unrelated (open a pane etc). Product-update articles announce PoPs already available / "shortly" (e.g. Lagos, 2025) but nothing for 2027 | unanswerable |

Caveats: ADJ09 and ADJ12 are the weakest (closest topical coverage); the pooled LLM judging stage (gold labels) is the
final arbiter of whether any passage grades 2 for these.
Rejected drafts: Wi-Fi 7/6 GHz (FAQ states Wi-Fi 6, 2.4/5 GHz), Linux ARM client release (ARM64 support documented),
Lagos PoP (documented), Zscaler chaining (17 Zscaler mentions), "when will PQC ship for Client" (exists).
