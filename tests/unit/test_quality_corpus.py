"""Pins for core/quality/corpus.py — the shared fingerprint and JSONL scan.

The fingerprint's exact serialization (sort_keys, default=str, ensure_ascii=False,
md5) determines BOTH the audit's true-dupe counts and what dedupe collapses; the
pinned hex digests guard it against any 'harmless' reformatting.
"""

import pytest

from core.quality import corpus
from core.quality.dedupe import _fingerprint as dedupe_fingerprint

pytestmark = pytest.mark.unit

REC = {"url": "https://x.org/a", "title": "T", "content": "body text"}


def test_fingerprint_invariant_to_every_volatile_field():
    base = corpus.fingerprint(REC)
    for k in corpus.VOLATILE:
        assert corpus.fingerprint({**REC, k: "changed"}) == base, k


def test_fingerprint_sensitive_to_content():
    assert corpus.fingerprint({**REC, "content": "different"}) != corpus.fingerprint(
        REC
    )
    assert corpus.fingerprint({**REC, "new_field": 1}) != corpus.fingerprint(REC)


def test_fingerprint_pinned_digest():
    # guards the serialization itself (key order, str-coercion, unicode, md5)
    assert corpus.fingerprint(REC) == "08c9ba895517d91f588c09436285a778"
    assert corpus.fingerprint({"url": "https://x.org/ü", "n": 3}) == corpus.fingerprint(
        {"n": 3, "url": "https://x.org/ü"}
    )  # sort_keys


def test_audit_and_dedupe_share_one_fingerprint():
    assert dedupe_fingerprint is corpus.fingerprint


def test_scan_file_counts(tmp_path):
    f = tmp_path / "crawl.jsonl"
    rows = [
        '{"url": "https://x.org/a", "title": "A", "content": "long enough text"}',
        '{"url": "https://x.org/a", "title": "A", "content": "long enough text"}',  # true dupe
        '{"url": "https://x.org/a", "title": "A", "content": "CHANGED text"}',  # version
        '{"title": "no url"}',  # noURL
        "not json at all",  # malformed
        '{"url": "https://x.org/b", "title": "", "content": "  "}',  # empty fields
    ]
    f.write_text("\n".join(rows) + "\n")
    p = corpus.scan_file(str(f))
    assert p["recs"] == 5  # parsed records (malformed dropped)
    assert len(p["urls"]) == 3  # a, b, noURL placeholder
    assert len(p["uc"]) == 4  # a×2 fingerprints, noURL, b
    assert len(p["content"]) == 1  # only /a has real content
    assert len(p["title"]) == 2  # /a and the noURL row


def test_median():
    assert corpus.median([]) == 0
    assert corpus.median([5]) == 5
    assert corpus.median([1, 9]) == 5
    assert corpus.median([1, 2, 100]) == 2


# --- PDF-row awareness (the framework's URL-only PDF harvest model) -----------

PDF_ROW = (
    '{"url": "https://ext.org/d.pdf", "title": "d.pdf", "content": "",'
    ' "metadata_json": {"content_type": "pdf", "found_on": "https://x.org/a"}}'
)


def test_is_pdf_row():
    assert corpus.is_pdf_row({"metadata_json": {"content_type": "pdf"}})
    # extract-mode rows carry the same marker with non-empty content
    assert corpus.is_pdf_row(
        {"metadata_json": {"content_type": "pdf"}, "content": "extracted text"}
    )
    # re-serialised corpora may carry metadata_json as a JSON string
    assert corpus.is_pdf_row({"metadata_json": '{"content_type": "pdf"}'})
    # a marker-less .pdf-suffixed URL is an ORDINARY row (no legacy sniffing)
    assert not corpus.is_pdf_row({"url": "https://x.org/report.pdf"})
    assert not corpus.is_pdf_row({"metadata_json": {"content_type": "html"}})
    assert not corpus.is_pdf_row({"metadata_json": "not json"})
    assert not corpus.is_pdf_row({})


def test_url_host_and_domains():
    assert corpus.url_host("https://www.wedocs.unep.org/x.pdf") == "wedocs.unep.org"
    assert corpus.url_host("bad url") == ""
    assert corpus.host_in_domains("wedocs.unep.org", ["unep.org"])
    assert corpus.host_in_domains("www.unep.org", ["unep.org"])
    assert not corpus.host_in_domains("notunep.org", ["unep.org"])  # dot boundary
    assert not corpus.host_in_domains("", ["unep.org"])
    assert not corpus.host_in_domains("unep.org", [])


def test_scan_file_pdf_rows_separated(tmp_path):
    f = tmp_path / "crawl.jsonl"
    rows = [
        '{"url": "https://x.org/a", "title": "A", "content": "real article text"}',
        PDF_ROW,
        # extract-mode pdf row: content present but must NOT count as content/clen
        '{"url": "https://x.org/own.pdf", "title": "own.pdf", "content": "pdf text",'
        ' "metadata_json": {"content_type": "pdf"}}',
    ]
    f.write_text("\n".join(rows) + "\n")
    p = corpus.scan_file(str(f))
    assert p["pdf"] == {"https://ext.org/d.pdf", "https://x.org/own.pdf"}
    assert p["content"] == {"https://x.org/a"}  # pdf text excluded
    assert list(p["clen"]) == ["https://x.org/a"]  # thin-median excluded too
    assert len(p["urls"]) == 3  # totals stay total (dupe math)
    c = corpus.file_counts(str(f))
    assert c["pdf"] == 2
    assert c["pdf_hosts"] == {"ext.org": 1, "x.org": 1}


def test_merge_partials_pdf_union(tmp_path):
    f1, f2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    f1.write_text(PDF_ROW + "\n")
    f2.write_text(PDF_ROW + "\n")  # same pdf in both files → one unique
    m = corpus.merge_partials([corpus.scan_file(str(f1)), corpus.scan_file(str(f2))])
    assert m["pdf"] == 1
    assert m["pdf_hosts"] == {"ext.org": 1}


def test_scan_project_cache_migration(tmp_path, monkeypatch):
    """A valid OLD-format cache entry (no pdf_hosts) triggers exactly one rescan;
    the rewritten entry is then served from cache."""
    import json as _json

    monkeypatch.setattr(corpus, "DATA_DIR", str(tmp_path))
    d = tmp_path / "proj" / "sp" / "crawls"
    d.mkdir(parents=True)
    f = d / "crawl_01012026.jsonl"
    f.write_text(PDF_ROW + "\n")
    st = f.stat()
    cache_dir = tmp_path / "proj" / "_audit" / "scan_cache"
    cache_dir.mkdir(parents=True)
    old_entry = {
        "unique": 1,
        "uc": 1,
        "content": 0,
        "title": 1,
        "recs": 1,
        "clen_vals": [],
        "size": st.st_size,
        "mtime": st.st_mtime,
    }
    (cache_dir / "sp.json").write_text(_json.dumps({f.name: old_entry}))
    out = corpus.scan_project("proj")
    assert out["sp"]["pdf"] == 1  # rescanned, pdf-aware
    ent = _json.loads((cache_dir / "sp.json").read_text())[f.name]
    assert "pdf_hosts" in ent  # cache rewritten in new format
    out2 = corpus.scan_project("proj")  # second run: served from cache
    assert out2["sp"]["pdf"] == 1
    assert out2["sp"]["pdf_hosts"] == {"ext.org": 1}
