"""Relationship-type taxonomy for the DeSmog network.

type_relationships.py classifies each in-text link into one of 16 fine
types via ordered keyword rules. For browsing the dashboard those are too
fine-grained (16 legend colours, and the template palette holds only 15),
so the fine types are grouped into 8 analytical groups by "what kind of
tie" the evidence describes:

  Affiliation            formal roles inside an organisation (who runs it)
  Funding                money flowing to/from the target
  Collaboration & events  appearing together, partnering, hosting
  Content & discourse    producing, citing or linking to content
  Conflict & campaigns   opposing, campaigning (for or against), criticising
  Denial framing         the tie is qualified by climate-denial language
  Location               shared physical location (e.g. 55 Tufton Street)
  Unclear                plain mention, no classifiable wording

The fine types stay in the data (relationship_types, primary_type); the
group is derived at write time (primary_group) and used by the dashboard
for edge colouring, the first-level edge filter, and the stats charts —
each group's chips expand to its fine types for drill-down.

RGROUPS is ordered by descending edge count on the current data so palette
assignment (and legend order) goes biggest first.
"""

GROUPS = {
    # fine type (primary_type in relationships_typed.*)  ->  group
    "Leadership":           "Affiliation",
    "Founder":              "Affiliation",
    "Board/member":         "Affiliation",
    "Employee/role":        "Affiliation",
    "Advisor":              "Affiliation",
    "Trustee":              "Affiliation",
    "Funder/donor":         "Funding",
    "Spoke at/attended":    "Collaboration & events",
    "Partnered/event":      "Collaboration & events",
    "Published/authored":   "Content & discourse",
    "Cited/linked-to":      "Content & discourse",
    "Opposed/campaigned":   "Conflict & campaigns",
    "Accused/criticised":   "Conflict & campaigns",
    "Climate-denial framing": "Denial framing",
    "Co-located/based":     "Location",
    "Mention/unclear":      "Unclear",
}

# canonical group order (descending edge count on the current data)
RGROUPS = [
    "Affiliation",
    "Unclear",
    "Content & discourse",
    "Funding",
    "Collaboration & events",
    "Conflict & campaigns",
    "Denial framing",
    "Location",
]


def group_of(rtype):
    """Group for a fine relationship type (unknown types -> Unclear)."""
    return GROUPS.get(rtype, "Unclear")
