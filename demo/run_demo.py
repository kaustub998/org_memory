from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__) + '/..')

from core.graph_store import TemporalGraphStore
from core.pipeline import ingest_meeting
from core.retrieval import retrieve_hybrid
from core.qa import answer_question
from data.meetingbank_loader import load_meetingbank
from tqdm import tqdm
from core.llm_connectors import build_connector

STORE_PATH = os.path.join(os.path.dirname(__file__), "demo_graph.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "extraction_log.jsonl")
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "meetingbank_slice_merged.json")
DEMO_QUESTIONS = [
    "What ordinances or bills were discussed across these meetings?",
    "Which council members or officials are mentioned, and what did they do?",
]

def main():
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)  # fresh run each time for the demo
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)  # fresh log file
    store = TemporalGraphStore(path=STORE_PATH)

    provider = os.environ.get('LLM_PROVIDER', 'anthropic')
    connector = build_connector(provider)
    meetings = load_meetingbank(DATA_PATH)[:3]
        

    print("=" * 70)
    print("PHASE 1 -- INGESTING MEETINGS")
    print("=" * 70)
    with open(LOG_PATH, "a") as log_file:
        for m in tqdm(meetings, desc="Meetings"):
            report = ingest_meeting(store, m["transcript"], m["meeting_id"], m["date"], connector=connector)
            log_file.write(json.dumps({
                "step": "meeting_summary",
                "meeting_id": m["meeting_id"],
                "date": m["date"],
                **report
            }) + "\n")
            print(f"\n--- {m['meeting_id']} ({m['date']}) ---")
            print(f"  entities seen: {report['entities_seen']}  |  new entities: {[n for n,_ in report['new_entities']]}")
            print(f"  facts extracted: {report['facts_extracted']}")
            for op, s, r, o in report["operations"]:
                print(f"    [{op}] {s} --{r}--> {o}")

    print("\n" + "=" * 70)
    print("GRAPH STATE -- ALL ENTITIES")
    print("=" * 70)
    for eid, ent in store.all_entities().items():
        print(f"  {eid}: {ent.canonical_name} ({ent.entity_type})  aliases={ent.aliases}")

    print("\n" + "=" * 70)
    print("GRAPH STATE -- ALL RELATIONS (active + superseded)")
    print("=" * 70)
    for rel in store.all_relations():
        subj = store.get_entity(rel.subject_id)
        obj = store.get_entity(rel.object_id)
        print(f"  [{rel.status:10s}] {subj.canonical_name} --{rel.relation}--> {obj.canonical_name}"
              f"  (valid_from={rel.valid_from}, valid_to={rel.valid_to})")

    print("\n" + "=" * 70)
    print("PHASE 1 -- HYBRID RETRIEVAL + QA")
    print("=" * 70)
    with open(LOG_PATH, "a") as log_file:
        for q in DEMO_QUESTIONS:
            evidence = retrieve_hybrid(store, q)
            answer = answer_question(q, evidence, connector=connector)
            qa_entry = {
                "step": "qa",
                "question": q,
                "evidence_retrieved": evidence,
                "answer": answer
            }
            log_file.write(json.dumps(qa_entry) + "\n")
            print(f"\nQ: {q}")
            print(f"  evidence retrieved ({len(evidence)}):")
            for e in evidence:
                print(f"    - {e}")
            print(f"  ANSWER: {answer}")

if __name__ == "__main__":
    main()

