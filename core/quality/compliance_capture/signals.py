"""Legal-text / licence / AI signal batteries and their classifiers.

Every regex battery here is regression-pinned (tests/unit/test_compliance_signals.py
and test_audit.py) and was moved VERBATIM from the single-file module — never
reflow or rewrap these."""

import re

# Weak signal — page merely MENTIONS scraping-ish words (incl. a site describing its OWN
# data collection, e.g. "we collect by automated means"). Informational only; never flags.
SCRAPE_WORDS = re.compile(
    r"\b(scrap(e|es|ed|ing)|crawl(er|ers|ing)?|spider|"
    r"data[ -]?min(e|ing)|data[ -]?harvest(ing)?|screen[ -]?scrap\w*|"
    r"automated (access|means|collection|querying|tools?))\b",
    re.I,
)
# Strong signal — a DIRECTED PROHIBITION against the reader scraping/crawling THIS site.
# Requires a prohibition aimed at a scraping activity, so it does NOT match a privacy policy
# describing the operator's own automated collection (the rmi.org false positive), NOR a GDPR
# Art. 22 clause ("we do not engage in decision-making based solely on automated PROCESSING"):
# "automated processing/decision-making" is data-protection language, not scraping, so
# `process\w*` is deliberately excluded from the automated-X targets (the nrdc.org FP).
_SCRAPE_TGT = (
    r"(?:scrap\w+|crawl\w+|spider\w*|harvest\w*|data[ -]?min\w+|web ?bots?|"
    r"robots?|automated (?:means|access|tools?|scripts?|systems?|quer\w+|"
    r"agents?|devices?))"
)
_PROHIBIT = (
    r"(?:shall not|may not|must not|will not|do(?:es)? not|cannot|not permitted|"
    r"are prohibited|is prohibited|prohibited from|agree(?:s)? not to|refrain from|"
    r"are not allowed|is not allowed|forbidden)"
)
PROHIBIT_BEFORE = re.compile(rf"(?is)\b{_PROHIBIT}\b[^.]{{0,120}}?\b{_SCRAPE_TGT}\b")
PROHIBIT_AFTER = re.compile(
    rf"(?is)\b{_SCRAPE_TGT}\b[^.]{{0,120}}?\b"
    rf"(?:is|are)\b[^.]{{0,40}}?\b(?:prohibited|forbidden|not permitted|not allowed)\b"
)
CONSENT_AFTER = re.compile(
    rf"(?is)\b{_SCRAPE_TGT}\b[^.]{{0,120}}?\bwithout\b[^.]{{0,40}}?"
    rf"\b(?:written |prior |express )+(?:consent|permission|authoriz\w+)"
)


def scrape_prohibition(text):
    """Match (and snippet) the first DIRECTED prohibition against scraping/crawling this
    site, or None. Distinct from a mere mention of automated processing (SCRAPE_WORDS).
    """
    for rx in (PROHIBIT_BEFORE, PROHIBIT_AFTER, CONSENT_AFTER):
        m = rx.search(text or "")
        if m:
            s, e = max(0, m.start() - 60), m.end() + 60
            return re.sub(r"\s+", " ", text[s:e]).strip()
    return None


# A directed prohibition on using the content to TRAIN / for AI-ML. A site-wide opt-out from
# AI use even when scraping per se isn't forbidden ("...may not be used to train any model").
# Unambiguous AI/ML terms identify AI use on their own:
_AI_NOUN = (
    r"machine[ -]?learning|artificial intelligence|\bAI\b|\bML\b|\bLLMs?\b|"
    r"language model\w*|generative (?:ai|model\w*)|neural network\w*"
)
# "train" is ambiguous (staff / course training), so it counts ONLY with an AI/ML anchor
# beside it — "train a model", "used to train any AI" — NOT "staff training" / "training
# courses" / "training, visa or other fee" (the recruitment-page false positive).
_AI_ANCHOR = (
    r"model\w*|\bAI\b|\bML\b|\bLLMs?\b|machine[ -]?learning|algorithm\w*|"
    r"neural network\w*|dataset\w*|generative|artificial intelligence"
)
_AI_TGT = (
    r"(?:" + _AI_NOUN + r"|train\w*[^.]{0,30}?(?:" + _AI_ANCHOR + r")|"
    r"(?:" + _AI_ANCHOR + r")[^.]{0,30}?train\w*)"
)
AI_TRAIN_BEFORE = re.compile(rf"(?is)\b{_PROHIBIT}\b[^.]{{0,120}}?\b{_AI_TGT}\b")
AI_TRAIN_AFTER = re.compile(
    rf"(?is)\b{_AI_TGT}\b[^.]{{0,120}}?\b"
    rf"(?:is|are)?\b[^.]{{0,40}}?\b(?:prohibited|forbidden|not permitted|not allowed)\b"
)
AI_TRAIN_CONSENT = re.compile(
    rf"(?is)\bnot\b[^.]{{0,40}}?\b(?:used|use)\b[^.]{{0,60}}?\b(?:to |for )\b[^.]{{0,20}}?\b{_AI_TGT}\b"
)


def ai_training_prohibition(text):
    """First directed clause prohibiting use of the content to TRAIN AI/ML models, or None —
    a site-wide AI opt-out expressed in the terms (distinct from a no-scraping clause).
    """
    for rx in (AI_TRAIN_BEFORE, AI_TRAIN_AFTER, AI_TRAIN_CONSENT):
        m = rx.search(text or "")
        if m:
            s, e = max(0, m.start() - 60), m.end() + 60
            return re.sub(r"\s+", " ", text[s:e]).strip()
    return None


LICENSE_RE = re.compile(
    r"(creative commons|CC[ -]BY(?:-[A-Z]{2})?(?:-\d\.\d)?|"
    r"all rights reserved|public domain|open government licence)",
    re.I,
)
COPYRIGHT_RE = re.compile(r"(©|copyright)\s*[^\n]{0,80}", re.I)
# A hyperlink to creativecommons.org is the most reliable, machine-readable licence signal.
CC_URL_RE = re.compile(
    r"creativecommons\.org/(licenses|publicdomain)/([a-z0-9.\-]+(?:/[0-9.]+)?)", re.I
)
# CC variants that restrict reuse (NoDerivatives / NonCommercial / ShareAlike).
LIMITED_LICENSE_RE = re.compile(
    r"\bnd\b|\bnc\b|\bsa\b|noderiv|noncommercial|sharealike", re.I
)
# A specific CC variant token in prose, e.g. "CC BY-NC-SA 2.0" — used to upgrade a bare
# "Creative Commons" match to the actual variant.
CC_CODE_RE = re.compile(
    r"\bCC[ \-]?BY(?:[ \-](?:NC|ND|SA))*(?:[ \-]?\d(?:\.\d)?)?", re.I
)
# Words signalling the licence sentence is about a NARROW SUBSET (a dataset, photos, a map)
# rather than the site's article content — used to downgrade detection confidence.
SUBSET_WORDS = re.compile(
    r"\b(geospatial|google\s+(?:maps|earth)|kml|kmz|flickr|photograph\w*|photos?|imager(?:y|ies)|"
    r"figures?|videos?|excerpts?|logos?|trademark\w*|dataset\w*)\b",
    re.I,
)

# A directed, NON-named reuse grant — "you may reproduce/republish/quote … with attribution /
# for non-commercial / educational / personal use". The single most useful reuse signal a
# non-CC site gives; LICENSE_RE misses it because it isn't a named licence. Trigger phrases
# mirror the client intake guide.
_GRANT_VERB = (
    r"(?:may|can|are free to|is granted|are granted|grant(?:s|ed)? (?:you|the user)?|"
    r"permission is (?:hereby )?granted|free to use)"
)
_GRANT_ACT = (
    r"(?:reproduce|reproduced|republish(?:ed)?|redistribut\w+|copy|copied|share[d]?|"
    r"quot\w+|reus\w+|distribut\w+|us(?:e|ed))"
)
_GRANT_COND = (
    r"(?:with (?:attribution|credit|acknowledg\w+)|provided[^.]{0,40}credit|"
    r"for (?:non[- ]?commercial|noncommercial|educational|academic|personal|"
    r"research|non[- ]?profit)[^.]{0,30}(?:use|purpose)|"
    r"non[- ]?commercial(?:ly)?|educational use|personal use|research purposes)"
)
BESPOKE_PERMISSION = re.compile(
    rf"(?is)\b{_GRANT_VERB}\b[^.]{{0,80}}?\b{_GRANT_ACT}\b[^.]{{0,120}}?\b{_GRANT_COND}\b"
)


def bespoke_permission(text):
    """First directed, non-named reuse grant ('may be reproduced for non-commercial use with
    attribution', …) as a clean snippet, or None. Distinct from a named CC/OGL licence.
    """
    m = BESPOKE_PERMISSION.search(text or "")
    if not m:
        return None
    s, e = max(0, m.start() - 30), m.end() + 30
    return re.sub(r"\s+", " ", text[s:e]).strip()


# llms.txt is USUALLY an AI-friendly curation file, but it CAN carry prohibitions. These mark
# a restrictive llms.txt (→ a machine-readable AI-reuse signal); absent them it's curation.
LLMS_PROHIBIT = re.compile(
    r"(?im)^\s*##\s*(disallow|block|prohibit)|"
    r"\b(?:llms?|ai|bots?) (?:may|must|should) not\b|"
    r"\bdo not (?:train|use|scrape|crawl)\b|"
    r"\bno (?:ai|llm) (?:training|use|access)\b"
)
LLMS_ALLOW = re.compile(
    r"(?im)\b(?:llms?|ai) (?:are )?(?:welcome|allowed|may use|"
    r"free to use)\b|^\s*##\s*allow"
)


def classify_llms(text):
    """(verdict, quote) for an llms.txt body. verdict ∈ {allows, prohibits, partial,
    present-unclear}; quote = the single most relevant directive line (or None)."""
    if not text or not text.strip():
        return "not-found", None
    mp = LLMS_PROHIBIT.search(text)
    if mp:
        line = next(
            (
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and LLMS_PROHIBIT.search(ln)
            ),
            None,
        )
        # a `## Disallow` with listed paths is partial; a blanket "do not train" is full
        verdict = (
            "partial" if re.search(r"(?im)^\s*##\s*disallow", text) else "prohibits"
        )
        return verdict, (line or re.sub(r"\s+", " ", mp.group(0)).strip())
    if LLMS_ALLOW.search(text):
        return "allows", None
    return "present-unclear", None


def _norm_cc(matched):
    """Canonicalise a matched CC token ('cc by-nc-sa 2.0', 'CC-BY-ND') → 'CC BY-NC-SA 2.0'."""
    toks, seen = [], set()
    for t in re.findall(r"BY|NC|ND|SA", matched.upper()):
        if t not in seen:
            seen.add(t)
            toks.append(t)
    ver = re.search(r"\d(?:\.\d)?", matched)
    return "CC " + "-".join(toks) + (f" {ver.group(0)}" if ver else "")


def refine_license(lic):
    """Post-process a detected licence in place:
    - a bare 'Creative Commons' is upgraded to the specific CC variant if the grant
      sentence names one (e.g. UNFCCC's 'CC BY-NC-SA 2.0'), so NC/ND/SA aren't lost.
    - confidence drops to 'low' when the grant sentence is about a narrow SUBSET
      (geospatial data, Flickr photos, map imagery…) rather than the site's content."""
    name, quote = lic.get("license"), lic.get("license_quote") or ""
    if (
        name
        and "creative commons" in name.lower()
        and not re.search(r"cc[ \-]?by", name, re.I)
    ):
        m = CC_CODE_RE.search(quote)
        if m:
            lic["license"] = _norm_cc(m.group(0))
    if quote and SUBSET_WORDS.search(quote):
        lic["license_confidence"] = "low"
    return lic


def first(rx, text):
    m = rx.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def split_license(text):
    """First explicit licence mention that is NOT a bare 'all rights reserved'."""
    for m in LICENSE_RE.finditer(text or ""):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if "all rights reserved" not in s.lower():
            return s
    return None


def license_sentence(text, max_chars=500):
    """The full sentence(s) around the first licence mention in `text` — the actual grant
    wording a reviewer needs (e.g. 'For Owner Content we grant You a Creative Commons (CC)
    Attribution 4.0 International licence. It is Your responsibility to read the licence in
    full and comply.'). Grabs the sentence the licence sits in plus the following one (so a
    'we grant … You must …' pair survives), bounded by '.'/newline. None if not found.
    """
    if not text:
        return None
    m = LICENSE_RE.search(text)
    if not m:
        return None
    # back up to the start of the sentence the match sits in
    s = max(text.rfind(". ", 0, m.start()), text.rfind("\n", 0, m.start()))
    s = s + 1 if s != -1 else 0
    # extend through the match's sentence and the next one (caps/conditions often follow)
    e, sentences = m.end(), 0
    while sentences < 2 and e < len(text):
        cands = [x for x in (text.find(". ", e), text.find("\n", e)) if x != -1]
        if not cands:
            e = len(text)
            break
        e = min(cands) + 1
        sentences += 1
    return re.sub(r"\s+", " ", text[s:e]).strip()[:max_chars].strip() or None


# A © holder line: "© 2018-2024 Rocky Mountain Institute" → holder + year(s). Greedy enough
# to grab the org name, stops at sentence end / 'all rights reserved' / a long run.
COPYRIGHT_STMT_RE = re.compile(
    r"(?im)(?:©|copyright|\(c\))\s*(?:©\s*)?"
    r"(?P<years>(?:\d{4}\s*[–\-—to]+\s*\d{4})|\d{4})?\s*"
    r"(?P<rest>[^\n.]{0,120})"
)
# Trailing text that is ONLY legal-nav words — marks a menu link ("Copyright, terms and
# conditions"), NOT a real notice. Used to reject those false matches.
_CR_NAVWORDS = re.compile(
    r"(?i)^(?:[\s,&|/–—-]*(?:terms|conditions?|privacy|cookies?|polic\w+|"
    r"disclaimers?|legal|and|of|use|notices?|sitemap|accessibility)\b"
    r"[\s,&|/–—-]*)+$"
)


def copyright_statement(text):
    """The fullest REAL copyright notice in `text` (whole line, not an 80-char snippet) +
    parsed {years, holder}. Returns (full, years, holder) or (None, None, None).
    Rejects bare nav labels like 'Copyright, terms and conditions' (no ©/year, only nav
    words). A holder is parsed ONLY from a structured ©/year-anchored notice — prose copyright
    keeps the statement but no holder, so a licence sentence isn't mistaken for a rights-holder
    (which would spawn a false discrepancy)."""
    if not text:
        return None, None, None
    best = None
    for m in COPYRIGHT_STMT_RE.finditer(text):
        full = re.sub(r"\s+", " ", m.group(0)).strip()
        years = m.group("years")
        rest = (m.group("rest") or "").strip()
        head = m.group(0).lstrip()
        has_symbol = "©" in m.group(0)  # the real © glyph (unambiguous)
        # A lone "(c)" with NO year is almost always a list/enumeration marker
        # ("(c) personal data from a known child"), NOT a copyright symbol — reject it.
        # A genuine "(c) 2024 Name" carries a year, so it still matches.
        if re.match(r"(?i)\(c\)", head) and not has_symbol and not years:
            continue
        # reject a bare nav link: no symbol, no year, trailing text only legal-nav words
        if not has_symbol and not years and (not rest or _CR_NAVWORDS.match(rest)):
            continue
        holder = None
        if has_symbol or years:
            h = re.sub(r"(?i)\.?\s*all rights reserved.*$", "", rest).strip(" .,-–—|&")
            holder = h if (h and not _CR_NAVWORDS.match(h)) else None
        if len(full) > 3 and (best is None or len(full) > len(best[0])):
            best = (full, years, holder)
    if not best:
        return None, None, None
    return best[0], (best[1].strip() if best[1] else None), best[2]
