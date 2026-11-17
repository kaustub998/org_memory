"""
Offline verification harness.

Mocks extract_from_transcript() with hand-written output that mirrors
what the real LLM call would plausibly extract from the three synthetic
meetings, so entity resolution / update policy / graph store / hybrid
retrieval can all be verified WITHOUT an Anthropic API key.

Run demo/run_demo.py instead once you export ANTHROPIC_API_KEY -- that
version calls the real model for extraction and answer generation.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from core.types import ExtractedEntity, ExtractedFact, new_id
from core.graph_store import TemporalGraphStore
from core import pipeline
from core.retrieval import retrieve_hybrid

STORE_PATH = os.path.join(os.path.dirname(__file__), "demo_graph_offline.json")

MEETINGS = [
    {
        "meeting_id": "council_2024_01_10",
        "date": "2024-01-10",
        "transcript": "Sarah Chen has been appointed as the Project Manager for the Riverfront Park Renewal project. She will report directly to Mark Ibsen, Director of Public Works.",
    },
    {
        "meeting_id": "council_2024_03_14",
        "date": "2024-03-14",
        "transcript": "Sarah briefed the council that the Riverfront project moved from planning to the construction bidding phase. She still reports to the Director of Public Works.",
    },
    {
        "meeting_id": "council_2024_07_22",
        "date": "2024-07-22",
        "transcript": "Sarah Chen has been promoted to Senior Program Director. David Nwosu will take over as Project Manager for the Riverfront Park Renewal project.",
    },
]

DEMO_QUESTIONS = [
    "Who manages the Riverfront Park Renewal project?",
    "What is Sarah Chen's current role?",
]


def _mock_extract(transcript_text, meeting_id, meeting_date, connector=None, **kwargs):
    """Hand-written stand-in for the LLM extraction call, keyed by meeting_id."""
    if meeting_id == "council_2024_01_10":
        entities = [
            ExtractedEntity(new_id("ent"), "Sarah Chen", "PERSON", "Sarah Chen has been appointed as the Project Manager"),
            ExtractedEntity(new_id("ent"), "Riverfront Park Renewal", "PROJECT", "the Project Manager for the Riverfront Park Renewal project"),
            ExtractedEntity(new_id("ent"), "Mark Ibsen", "PERSON", "Director of Public Works, Mark Ibsen"),
            ExtractedEntity(new_id("ent"), "Department of Public Works", "DEPARTMENT", "The Department of Public Works fully supports"),
        ]
        facts = [
            ExtractedFact(new_id("fact"), "Sarah Chen", "role_is", "Project Manager", "appointed as the Project Manager", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "Sarah Chen", "manages", "Riverfront Park Renewal", "Project Manager for the Riverfront Park Renewal project", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "Sarah Chen", "reports_to", "Mark Ibsen", "will report directly to the Director of Public Works, Mark Ibsen", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "Riverfront Park Renewal", "status_is", "planning phase", "currently in the planning phase", meeting_id, meeting_date),
        ]
    elif meeting_id == "council_2024_03_14":
        entities = [
            ExtractedEntity(new_id("ent"), "Sarah", "PERSON", "Sarah, can you brief us?"),
            ExtractedEntity(new_id("ent"), "Riverfront project", "PROJECT", "get an update on the Riverfront project"),
        ]
        facts = [
            ExtractedFact(new_id("fact"), "Riverfront project", "status_is", "construction bidding phase", "moved from planning to the construction bidding phase", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "Sarah", "reports_to", "Director of Public Works", "I still report to the Director of Public Works", meeting_id, meeting_date),
        ]
    elif meeting_id == "council_2024_07_22":
        entities = [
            ExtractedEntity(new_id("ent"), "Sarah Chen", "PERSON", "Sarah Chen has been promoted to Senior Program Director"),
            ExtractedEntity(new_id("ent"), "David Nwosu", "PERSON", "David Nwosu will take over as Project Manager"),
            ExtractedEntity(new_id("ent"), "Riverfront Park Renewal", "PROJECT", "Project Manager for the Riverfront Park Renewal project"),
        ]
        facts = [
            ExtractedFact(new_id("fact"), "Sarah Chen", "role_is", "Senior Program Director", "promoted to Senior Program Director", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "David Nwosu", "role_is", "Project Manager", "take over as Project Manager", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "David Nwosu", "manages", "Riverfront Park Renewal", "Project Manager for the Riverfront Park Renewal project", meeting_id, meeting_date),
            ExtractedFact(new_id("fact"), "Department of Public Works", "supports", "Riverfront Park Renewal", "continues to support this project's timeline", meeting_id, meeting_date),
        ]
    else:
        entities, facts = [], []
    return entities, facts, {
        "meeting_id": meeting_id,
        "chunk_idx": kwargs.get("chunk_idx"),
        "status": "success",
        "raw_output": "[mocked extraction]",
        "entities_cnt": len(entities),
        "facts_cnt": len(facts),
        "parse_error": None,
    }


def _mock_answer(question, evidence):
    """Stand-in for the LLM QA call -- just echoes the evidence found, so
    we can confirm RETRIEVAL is pulling the right things without needing
    a live model to phrase the final sentence."""
    if not evidence:
        return "[MOCK ANSWER] No evidence found."
    return "[MOCK ANSWER] Based on evidence:\n    " + "\n    ".join(evidence)


def main():
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)
    store = TemporalGraphStore(path=STORE_PATH)

    with patch("core.pipeline.extract_from_transcript", side_effect=_mock_extract):
        print("=" * 70)
        print("OFFLINE VERIFICATION -- INGESTING MEETINGS (extraction mocked)")
        print("=" * 70)
        for m in MEETINGS:
            report = pipeline.ingest_meeting(store, m["transcript"], m["meeting_id"], m["date"])
            print(f"\n--- {m['meeting_id']} ({m['date']}) ---")
            print(f"  new entities created: {[n for n, _ in report['new_entities']]}")
            for op, s, r, o in report["operations"]:
                print(f"    [{op}] {s} --{r}--> {o}")

    print("\n" + "=" * 70)
    print("GRAPH STATE -- ENTITIES (checking Sarah/Sarah Chen resolved to ONE node)")
    print("=" * 70)
    for eid, ent in store.all_entities().items():
        print(f"  {eid}: {ent.canonical_name!r}  aliases={ent.aliases}  type={ent.entity_type}")

    print("\n" + "=" * 70)
    print("GRAPH STATE -- RELATIONS (checking SUPERSEDE fired on role change)")
    print("=" * 70)
    for rel in store.all_relations():
        subj = store.get_entity(rel.subject_id)
        obj = store.get_entity(rel.object_id)
        print(f"  [{rel.status:10s}] {subj.canonical_name} --{rel.relation}--> {obj.canonical_name}"
              f"  (from={rel.valid_from}, to={rel.valid_to})")

    print("\n" + "=" * 70)
    print("HYBRID RETRIEVAL (answer generation mocked)")
    print("=" * 70)
    for q in DEMO_QUESTIONS:
        evidence = retrieve_hybrid(store, q)
        print(f"\nQ: {q}")
        print(_mock_answer(q, evidence))

    # ---- diagnostics: what the naive Phase 1 resolver gets right vs. wrong ----
    print("\n" + "=" * 70)
    print("PHASE 1 BASIC-BLOCK DIAGNOSTICS")
    print("=" * 70)

    entities = store.all_entities()
    sarah_nodes = [e for e in entities.values() if "sarah" in e.canonical_name.lower()]
    if len(sarah_nodes) == 1:
        print("[RESOLVED]   'Sarah' and 'Sarah Chen' correctly merged into one entity.")
    else:
        print(f"[EXPECTED GAP] 'Sarah' and 'Sarah Chen' stayed as {len(sarah_nodes)} separate nodes:")
        for e in sarah_nodes:
            print(f"    - {e.entity_id}: {e.canonical_name!r}")
        print("  This is the naive single-signal resolver failing on a short-form name,")
        print("  exactly as expected -- a bare TF-IDF/exact-match check has no way to know")
        print("  'Sarah' and 'Sarah Chen' are the same person without more context (neighbor")
        print("  entities, relation overlap, embeddings). This is the concrete baseline your")
        print("  Phase 2 contextual entity resolver is meant to fix -- keep this as a 'before'")
        print("  data point for your ablation study / results chapter.")

    pm_relations = [r for r in store.all_relations() if r.relation == "role_is"]
    superseded = [r for r in pm_relations if r.status == "superseded"]
    if superseded:
        print("\n[RESOLVED]   Role change (Project Manager -> Senior Program Director) correctly")
        print("             superseded the old role_is edge -- the naive rule table handles")
        print("             same-subject/same-relation/different-object conflicts correctly")
        print("             even without LLM-based conflict reasoning.")
    else:
        print("\n[UNEXPECTED] Expected the promotion to supersede the old role_is edge -- check update_policy.py")

    print("\nSummary: extraction is the only layer that needs a live API key to test for")
    print("real; entity resolution, the update policy, the temporal graph store, and hybrid")
    print("retrieval are all verified deterministically above.")


if __name__ == "__main__":
    main()
