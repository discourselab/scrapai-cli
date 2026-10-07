#!/usr/bin/env python3
"""
Classify every relationship in the DeSmog network by TYPE, using the wording
in the text immediately around each in-text link.

Input : climate-disinformation-database/relationships.jsonl (+ entities.jsonl)
Output: climate-disinformation-database/relationships_typed.jsonl
        climate-disinformation-database/relationships_typed.csv
"""
import json, re, csv
from collections import Counter

from desmog.data import D, load_entities, load_relationships

# Ordered: first match that applies is kept as the PRIMARY type; all matches
# are recorded in relationship_types.
RULES = [
    ("Founder",          r"founder|founded|co-?found|set up (?:by|the)|established by|establish(?:ed|ing) the|launched by|launch(?:ed|ing) the|formed (?:in \d+ )?by|co-?created|set-up|start(?:ed)? the|founding"),
    ("Funder/donor",     r"funder|donor|donate|donation|\bfund(?:ed|s|ing)?\b|financ(?:ed|es|ing|ial support)|backer|back(?:ed|s|ing) financ|bankroll|gave £|gave \$|\$[\d,]+|£[\d,]+|business supporter|grant(?:ed|s|ee)?|contribut(?:ed|ion)|money (?:to|from)|paid (?:by|to)|sponsor|received .* from|gave .* to"),
    ("Leadership",       r"director|director general|chief exec|\bceo\b|\bcfo\b|\bcoo\b|chairman|chairwoman|\bchair\b|\bpresident\b|vice[- ]president|party leader|\beditor|head(?:ed|s)? (?:of|the)|secretary|managing|founder and|leads?\b|led (?:by|the)|runs? the|in charge of|executive"),
    ("Advisor",          r"advis(?:or|er|ory|es|ed|ing)|consult(?:ant|ing|ed)|counsel"),
    ("Trustee",          r"trustee|board of trustees"),
    ("Board/member",     r"\bmember\b|membership|affiliat(?:ed|ion)|\bfellow\b|\bfellowship|advisory (?:board|panel|council|committee)|vice chair|board member|on the board|sits on|serves on|part of|belongs? to|associate|signatory|co-?sign"),
    ("Employee/role",    r"\bworked (?:for|at|with)|\bwork(?:s|ing)? (?:for|at)|employ(?:ed|ee|er|ment)|staff|hired|recruit(?:ed)?|appointed|joined|position (?:at|of)|role (?:at|as)|spokes(?:man|woman|person)|intern|analyst at|economist at|scientist at|serv(?:ed|es|ing) as"),
    ("Co-located/based", r"based (?:in|at)|resident of|located|headquarter|moved to|same (?:address|office|building)|share(?:s|d)? (?:an? )?(?:address|office|building|premises)|operates? (?:out of|from)|registered (?:at|to)"),
    ("Published/authored", r"published|publication|report(?:s)? by|work(?:s)? by|book by|paper by|study by|author(?:ed|s)?|wrote|writing|writ(?:es|ten)|publish(?:es|ing)|op-?ed|article(?:s)? by|column(?:ist)?|co-?authored|blog(?:ged|s)?|byline|contributed (?:an?|to) (?:article|piece|column|op)"),
    ("Partnered/event",  r"partner(?:ship|ed|s)?|in partnership|along ?side|together with|held a|co-?host|jointly|collaborat|allied with|alliance with|coalition|teamed up|work(?:ed|ing) (?:together|alongside)|joint(?:ly)?"),
    ("Spoke at/attended", r"spoke (?:at|to)|speaker|keynote|presented at|present(?:ation)? (?:at|to)|attend(?:ed|ee|ing)?|panel(?:ist|list)?|conference|summit|gave a (?:talk|speech|lecture|presentation)|address(?:ed)? the|testif(?:y|ied)|interview(?:ed)?|guest (?:on|at)|appear(?:ed|ance) (?:on|at)"),
    ("Accused/criticised", r"accus|alleg|criticis|critical of|condemn|attack(?:ed|s|ing)?|smear|denounce|slam|lambast|rebuk|dismiss(?:ed|es)?|call(?:ed|s)? .* (?:a )?(?:denier|liar|fraud|shill)|labell?ed|brand(?:ed)?|target(?:ed|ing)? by|sued|lawsuit|complaint against|exposed|revealed|named .* as|debunk|rebut|challeng(?:ed|es)?|disput(?:ed|es)?"),
    ("Opposed/campaigned", r"oppos(?:ed|es|ing|ition)|campaign(?:ed|s|ing)? (?:against|for)|lobb(?:y|ied|ying)|protest|fought (?:against|for)|push(?:ed|es|ing)? (?:for|back|against)|advocat(?:ed|es|ing)?|promot(?:ed|es|ing)?|support(?:ed|s|ing)? the|endors(?:ed|es|ing)?|against the"),
    ("Cited/linked-to",  r"cit(?:ed|es|ing)|quot(?:ed|es|ing)|referenc(?:ed|es|ing)|according to|said|stated|told|noted|argu(?:ed|es)|claim(?:ed|s)?|wrote that|link(?:ed|s)? to|tied to|connect(?:ed|ion)|associated with|relationship with|ties? (?:to|with)|linked"),
    ("Climate-denial framing", r"denier|denial|den(?:ying|ies)|reject(?:s|ed|ing)? .*scientific|misinformation|disinformation|anti-science|climate (?:science )?scepti|skeptic"),
]
COMPILED = [(t, re.compile(p, re.I)) for t, p in RULES]


def window(ctx, anchor):
    """Return the full sentence containing the anchor (fallback: ±120 chars)."""
    i = ctx.lower().find(anchor.lower())
    if i < 0:
        return ctx[:300]
    start = ctx.rfind(". ", 0, i)
    start = 0 if start < 0 else start + 2
    end = ctx.find(". ", i)
    end = len(ctx) if end < 0 else end + 1
    sent = ctx[start:end].strip()
    if len(sent) > 350:  # over-long -> tighten to ±120 around anchor
        sent = ctx[max(0, i - 120): i + len(anchor) + 120]
    return sent


def classify(w):
    tags = [t for t, pat in COMPILED if pat.search(w)]
    return tags or ["Mention/unclear"]


def main():
    ents = load_entities()
    rels = load_relationships()
    out = []
    for r in rels:
        w = re.sub(r"\s+", " ", window(r["context"], r["anchor_text"])).strip()
        # Mask the link's own name (and the source name) so keywords inside an
        # entity name (e.g. "DonorsTrust" -> donor) don't create false types.
        masked = w
        for nm in (r["anchor_text"], r.get("target_name"),
                   ents.get(r["source_slug"], {}).get("name")):
            if nm and len(nm) > 2:
                masked = re.sub(re.escape(nm), " \u2588 ", masked, flags=re.I)
        tags = classify(masked)
        se, te = ents.get(r["source_slug"], {}), ents.get(r["target_slug"], {})
        out.append({
            "source": se.get("name", r["source_slug"]),
            "source_slug": r["source_slug"],
            "source_type": se.get("type"),
            "source_country": se.get("country"),
            "target": te.get("name", r.get("target_name") or r["target_slug"]),
            "target_slug": r["target_slug"],
            "target_type": te.get("type"),
            "target_country": te.get("country"),
            "primary_type": tags[0],
            "relationship_types": "; ".join(tags),
            "evidence": w,
        })

    with open(D / "relationships_typed.jsonl", "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    with open(D / "relationships_typed.csv", "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        wtr.writeheader(); wtr.writerows(out)

    print(f"typed {len(out)} relationships")
    print("\n=== PRIMARY relationship type distribution ===")
    for t, n in Counter(o["primary_type"] for o in out).most_common():
        print(f"  {n:5d}  {t}")
    print("\n=== by any-match (relationships can have multiple types) ===")
    anyc = Counter()
    for o in out:
        for t in o["relationship_types"].split("; "):
            anyc[t] += 1
    for t, _ in RULES:
        if t in anyc:
            print(f"  {anyc[t]:5d}  {t}")
    print(f"  {anyc.get('Mention/unclear',0):5d}  Mention/unclear")
    print("\nwrote relationships_typed.jsonl and relationships_typed.csv")


if __name__ == "__main__":
    main()
