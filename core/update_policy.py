"""
Layer: Graph Update Policy -- PHASE 1 BASIC BLOCK.

Naive version described in your proposal's Phase 1: a fixed rule
table instead of the rules+LLM hybrid. Only three outcomes exist here:

    INSERT     -- no active (subject, relation, *) edge exists yet
    UPDATE     -- an active edge with this exact (s, r, o) exists -> just
                  refresh its provenance/timestamp, don't duplicate it
    SUPERSEDE  -- an active edge with this (s, r) exists but to a
                  DIFFERENT object -> assume the new fact replaces it

There is no MERGE, no PRESERVE, and no DEFER/FLAG yet -- conflicting
or ambiguous evidence is just resolved by "most recent wins", which is
exactly the naive assumption Phase 2's research is meant to improve on.
"""
from .graph_store import TemporalGraphStore
from .types import ExtractedFact


def apply_fact(store: TemporalGraphStore, subject_id: str, object_id: str, fact: ExtractedFact) -> str:
    """Applies one resolved fact to the graph under the naive rule table.
    Returns the operation performed, for logging/evaluation."""

    existing_same = store.find_active_relation(subject_id, fact.relation, object_id)
    if existing_same:
        # UPDATE: same fact restated -- refresh provenance, no new edge.
        for u, v, key, data in store.g.edges(keys=True, data=True):
            if key == existing_same:
                data["provenance"] = f"{fact.meeting_id}: {fact.context}"
                data["valid_from"] = min(data["valid_from"], fact.timestamp)
        return "UPDATE"

    conflicting = store.find_active_relations_by_subject_relation(subject_id, fact.relation)
    if conflicting:
        # SUPERSEDE: naive "most recent wins" -- no conflict adjudication yet.
        for rel in conflicting:
            store.supersede_relation(rel.relation_id, valid_to=fact.timestamp)
        store.add_relation(subject_id, fact.relation, object_id, fact.timestamp,
                            provenance=f"{fact.meeting_id}: {fact.context}")
        return "SUPERSEDE"

    # INSERT: brand new (subject, relation, *) combination.
    store.add_relation(subject_id, fact.relation, object_id, fact.timestamp,
                        provenance=f"{fact.meeting_id}: {fact.context}")
    return "INSERT"
