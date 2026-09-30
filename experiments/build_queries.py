"""Build data/queries.jsonl: the cost-limited 89-query subset (id,set,text,gold_hint).

89 = 35 ANS + 12 SCN + 12 ADJ + 10 OOD + 20 TKT. Reads the main repo's data/ read-only.

TKT selection (deterministic):
  1. FORCED: tickets seen as real-ticket examples of weak/wrong matches in the exploration run (12).
  2. FILL to 20: greedily pick the product_area with the fewest selected tickets so far
     (ties broken alphabetically), taking that area's lowest-numbered unselected ticket.
     This makes the subset span all 12 product areas before any area is repeated.
"""
import json
from collections import Counter
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parent / "data" / "queries.jsonl"

FORCED_TKT = [f"TCK-20264{n}" for n in (209, 239, 223, 246, 200, 229, 240, 214, 218, 228, 243, 251)]
N_TKT = 20

ADJ = [
    "How do I configure a Ubiquiti UniFi Dream Machine Pro to bring up an IKEv2 IPsec tunnel to a Cato PoP?",
    "What is the list price per Mbps for a 500 Mbps Cato site license on a three-year term?",
    "What is the planned release date for the Cato Socket X1900, and will it have 100G WAN ports?",
    "How do I set up an IPsec IKEv2 tunnel from a SonicWall NSa 3700 firewall to Cato?",
    "What early termination fee applies if we cancel our Cato subscription before the contract term ends?",
    "How do I configure MikroTik RouterOS v7 BGP peering with a Cato Socket?",
    "How do I make a Juniper SRX chassis cluster fail over correctly when it sits behind a Cato Socket HA pair?",
    "What is the maximum EIRP transmit power and antenna gain in dBi of the X1600 Wi-Fi radios?",
    "Which exact ML-KEM parameter set (512, 768 or 1024) does the Cato Client negotiate with the PoP when PQC is enabled?",
    "What changed in the Cato Windows Client version 9.2 release notes?",
    "How do I configure a Barracuda CloudGen F-Series firewall for an IPsec tunnel to a Cato PoP?",
    "Which new Cato PoP locations are scheduled to open in Q1 2027?",
]


def jl(p: Path) -> list[dict]:
    return [json.loads(line) for line in open(p) if line.strip()]


def pick_tickets(tickets: list[dict]) -> list[dict]:
    by_id = {t["ticket_id"]: t for t in tickets}
    chosen = [by_id[i] for i in FORCED_TKT]
    counts = Counter(t["product_area"] for t in chosen)
    areas = sorted({t["product_area"] for t in tickets})
    while len(chosen) < N_TKT:
        avail = [a for a in areas if any(t["product_area"] == a and t not in chosen for t in tickets)]
        a = min(avail, key=lambda x: (counts[x], x))
        nxt = min((t for t in tickets if t["product_area"] == a and t not in chosen), key=lambda t: t["ticket_id"])
        chosen.append(nxt)
        counts[a] += 1
    return chosen


def main() -> None:
    rows = []
    for d in jl(MAIN / "eval/questions.jsonl"):
        rows.append(dict(id=d["question_id"], set="ANS", text=d["question"], gold_hint=d.get("tags")))
    for d in jl(MAIN / "eval/scenarios.jsonl"):
        rows.append(dict(id=d["scenario_id"], set="SCN", text=d["opening_message"],
                         gold_hint=d["expected"].get("must_cite", [])))
    for d in pick_tickets(jl(MAIN / "tickets/tickets.jsonl")):
        rows.append(dict(id=d["ticket_id"], set="TKT", text=f'{d["subject"]}. {d["body"]}',
                         gold_hint=d.get("product_area")))
    for d in jl(MAIN / "eval/out_of_coverage.jsonl"):
        rows.append(dict(id=d["question_id"], set="OOD", text=d["question"], gold_hint=None))
    for i, t in enumerate(ADJ, 1):
        rows.append(dict(id=f"ADJ{i:02d}", set="ADJ", text=t, gold_hint=None))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), dict(Counter(r["set"] for r in rows)))
    print("TKT:", [(r["id"], r["gold_hint"]) for r in rows if r["set"] == "TKT"])


if __name__ == "__main__":
    main()
