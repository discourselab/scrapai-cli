"""Shared library for the DeSmog climate-disinformation network pipeline.

Modules:
    data       - load entities/relationships, degree and neighbour maps
    countries  - centroid/bbox tables, country helpers, deterministic jitter
    geo        - single Nominatim and single Wikidata client (cached, rate-limited)
    placement  - canonical location-merge priority and inheritance

The pipeline scripts in the parent directory import this package.
"""
