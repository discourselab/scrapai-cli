"""Per-project manual-review configs: audit_notes.json and
audit_sitemap_skip.json (loaders + the self-documenting stub writer)."""

import json
import os

from core.quality._env import DATA_DIR

from .spiders_db import audit_dir
from .text import _NOTES_INSTRUCTIONS, _SKIP_INSTRUCTIONS


def load_skip(project):
    """Spiders where sitemap use was deliberately avoided → never auto-probed.
    Format: {"<spider>": {"reason": "<why>", "updated": "YYYY-MM-DD"}} in
    data/<project>/_audit/audit_sitemap_skip.json (project-scoped — no project key
    wrapping it). A legacy bare-string value ("<spider>": "<reason>") is still accepted
    and normalised to {"reason": ..., "updated": None}. Returns (skip_dict, warnings)
    where each value is the normalised {"reason", "updated"} dict; warnings list config
    problems (duplicate keys, invalid JSON, missing reason/updated) so they can be BOTH
    printed and surfaced in the report."""
    warnings = []

    def warn_dup(pairs):
        # JSON keeps last-wins on duplicate keys, silently dropping entries — flag it.
        seen = {}
        for k, v in pairs:
            if k in seen:
                warnings.append(
                    f"`audit_sitemap_skip.json`: duplicate key `{k}` — "
                    "only the last block is kept, so some skips are "
                    "silently dropped. Merge them into one object."
                )
            seen[k] = v
        return seen

    path = os.path.join(DATA_DIR, project, "_audit", "audit_sitemap_skip.json")
    try:
        with open(path) as fh:
            data = json.load(fh, object_pairs_hook=warn_dup)
    except FileNotFoundError:
        return {}, warnings
    except json.JSONDecodeError as e:
        warnings.append(
            f"`{path}` is not valid JSON ({e}) — no " "skips applied; fix the file."
        )
        return {}, warnings
    # keys starting with `_` (e.g. `_instructions`) are documentation, not spiders.
    # Normalise each value to {"reason", "updated"} (legacy bare strings allowed).
    skip = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str):
            entry = {"reason": v, "updated": None}
        elif isinstance(v, dict):
            entry = {"reason": v.get("reason", ""), "updated": v.get("updated")}
            if not entry["reason"]:
                warnings.append(
                    f"`audit_sitemap_skip.json`: `{k}` has no `reason` — "
                    "the row will still be ignored but show no explanation."
                )
        else:
            warnings.append(
                f"`audit_sitemap_skip.json`: `{k}` must be a string or an "
                "object with `reason`/`updated` — skipped."
            )
            continue
        if not entry["updated"]:
            warnings.append(f"`audit_sitemap_skip.json`: `{k}` has no `updated` date.")
        skip[k] = entry
    return skip, warnings


def load_notes(project):
    """Manual-review annotations, keyed {"<spider>": {...}} in
    data/<project>/_audit/audit_notes.json (project-scoped — the file lives in that
    project's audit folder, with no project key wrapping it).
    Each entry: {"status": "ok"|"discard", "flag": "<short, shown in the report>",
    "note": "<concise: overall picture + a clause per original auto-flag>", "note_long":
    "<optional fuller detail — maintenance, commands, background>", "updated":
    "YYYY-MM-DD"}. `note`/`note_long` are file-only (never rendered).

    The `status` key is what changes the report — and the ONLY thing that does. A note
    with NO `status` is inert: it sits in the file as documentation/draft and changes
    neither the computed status nor the flags. (`"discard": true` is still accepted as a
    legacy alias for status "discard".)
      status "ok"      → promotes the row to `ok` with a `✓ reviewed: <flag>` token that
                         REPLACES the auto-flags that prompted review. Works whether the
                         computed status was a concern (`manual review` / `too few
                         pages`) OR already a clean `ok` (it stays `ok`, just gains the
                         reviewed tag). EXCEPTION: `extraction broken` is NOT promoted — it
                         surfaces as `⚠ reviewed-stale`, so a note can never claim empty
                         content is fine. `incomplete` (a coverage shortfall) CAN be
                         promoted: the reviewer is vouching the shortfall is a false positive
                         (e.g. a misleading denominator).
      status "discard" → moves the row to `discarded` with `🗑 discard: <flag>`, wins
                         over any computed status. For a source you've deliberately dropped.
    Whenever `status` is set a `flag` is REQUIRED, and it must be genuinely short — the
    1-2 most central points only, not a summary of the note; everything else goes in
    `note`/`note_long`. `note` should address EACH original auto-flag (thin?/small/
    liveness/sitemap-drift/…) so a reader sees why it's a false alarm (e.g. 'thin? ->
    genuinely short posts').
    Returns (notes_dict, warnings) — warnings mirror load_skip()."""
    warnings = []

    def warn_dup(pairs):
        seen = {}
        for k, v in pairs:
            if k in seen:
                warnings.append(
                    f"`audit_notes.json`: duplicate key `{k}` — only the "
                    "last block is kept; merge them into one object."
                )
            seen[k] = v
        return seen

    path = os.path.join(DATA_DIR, project, "_audit", "audit_notes.json")
    try:
        with open(path) as fh:
            data = json.load(fh, object_pairs_hook=warn_dup)
    except FileNotFoundError:
        return {}, warnings
    except json.JSONDecodeError as e:
        warnings.append(
            f"`{path}` is not valid JSON ({e}) — no review "
            "flags applied; fix the file."
        )
        return {}, warnings
    # keys starting with `_` (e.g. `_instructions`) are documentation, not spiders
    notes = {k: v for k, v in data.items() if not k.startswith("_")}
    for sp, entry in notes.items():
        if not isinstance(entry, dict):
            warnings.append(f"`audit_notes.json`: `{sp}` must be an object — ignored.")
            continue
        st = entry.get("status")
        want = st or ("discard" if entry.get("discard") else None)
        if st is not None and st not in ("ok", "discard"):
            warnings.append(
                f"`audit_notes.json`: `{sp}` has status `{st}` — must be "
                '"ok" or "discard"; the note is ignored (no effect).'
            )
        elif want and not entry.get("flag"):
            warnings.append(
                f"`audit_notes.json`: `{sp}` has status `{want}` but no "
                "`flag` — add a short flag (1-2 central points) so the row "
                "shows why."
            )
        elif want and not entry.get("updated"):
            warnings.append(
                f"`audit_notes.json`: `{sp}` (status `{want}`) has no "
                "`updated` date."
            )
        # no `status`/`discard` → inert documentation note; intentionally no warning
    return notes, warnings


def ensure_review_configs(project):
    """Keep each project's _audit/{audit_notes,audit_sitemap_skip}.json present and
    self-documenting. Creates the file (with just `_instructions`) if missing; if it
    exists, ensures the `_instructions` line is current — added if absent, refreshed if
    stale — while preserving every other key untouched (your spider entries are never
    modified or reordered). A file that isn't valid JSON is left alone (the loader will
    warn) so a mid-edit file is never clobbered."""
    d = audit_dir(project)
    for fname, instr in (
        ("audit_notes.json", _NOTES_INSTRUCTIONS),
        ("audit_sitemap_skip.json", _SKIP_INSTRUCTIONS),
    ):
        path = os.path.join(d, fname)
        try:
            with open(path) as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                continue  # unexpected shape — leave for the loader
        except FileNotFoundError:
            data = {}
        except json.JSONDecodeError:
            continue  # don't clobber a file being edited
        if data.get("_instructions") == instr:
            continue  # already current — no write
        # rebuild with `_instructions` first, every other entry preserved in order.
        # tmp + os.replace: these files hold HUMAN-edited review records — a crash
        # mid-dump must never truncate them (same pattern as _save_scan_cache).
        merged = {"_instructions": instr}
        merged.update({k: v for k, v in data.items() if k != "_instructions"})
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(merged, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
