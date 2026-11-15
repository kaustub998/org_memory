"""
Shared data structures for the organizational memory pipeline.
Kept deliberately simple (dicts-in, dataclasses-out) so Phase 2 can
replace individual pieces without touching the others.
"""
from dataclasses import dataclass, field
from typing import Optional
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class ExtractedEntity:
    """An entity mention pulled out of a single meeting transcript."""
    mention_id: str
    name: str                 # surface form as it appeared, e.g. "Sarah" or "the PM"
    entity_type: str          # PERSON, ROLE, PROJECT, DEPARTMENT, POLICY, ...
    context: str               # the sentence/snippet it came from (for scoring + provenance)


@dataclass
class ExtractedFact:
    """A (subject, relation, object) triple pulled out of a single meeting."""
    fact_id: str
    subject: str                # surface form
    relation: str
    obj: str                    # surface form
    context: str
    meeting_id: str
    timestamp: str               # meeting date, used as validity start


@dataclass
class GraphEntity:
    """A resolved, canonical node in the temporal graph."""
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list = field(default_factory=list)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


@dataclass
class GraphRelation:
    """An edge in the temporal graph, with a validity interval."""
    relation_id: str
    subject_id: str
    relation: str
    object_id: str
    valid_from: str
    valid_to: Optional[str] = None   # None == still current
    status: str = "active"            # active | superseded | preserved
    provenance: str = ""              # meeting_id + snippet
    confidence: float = 1.0
