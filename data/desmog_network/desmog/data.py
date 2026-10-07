"""Load the scraped DeSmog data and derive basic graph statistics."""
import json
from collections import defaultdict
from pathlib import Path

# The data directory: <parent of this package>/climate-disinformation-database
D = Path(__file__).resolve().parent.parent / "climate-disinformation-database"


def load_jsonl(path):
    """Read a JSON-lines file into a list (skips blank lines)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_entities(path=None):
    """slug -> entity dict."""
    return {e["slug"]: e for e in load_jsonl(path or D / "entities.jsonl")}


def load_relationships(path=None):
    return load_jsonl(path or D / "relationships.jsonl")


def degree_map(rels):
    """slug -> number of relationships (parallel edges counted separately).

    Note: build_dashboard.py aggregates parallel edges into unique pairs
    first, so it computes its own (smaller) degrees on purpose.
    """
    deg = defaultdict(int)
    for r in rels:
        deg[r["source_slug"]] += 1
        deg[r["target_slug"]] += 1
    return deg


def neighbour_map(rels):
    """slug -> set of slugs it shares at least one relationship with."""
    nb = defaultdict(set)
    for r in rels:
        nb[r["source_slug"]].add(r["target_slug"])
        nb[r["target_slug"]].add(r["source_slug"])
    return nb
