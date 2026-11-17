"""
Ingests the real, merged MeetingBank slice (data/meetingbank_slice_merged.json)
and answers a few sample questions.

Works with any connector from core/llm_connectors.py -- set LLM_PROVIDER to
pick which one (defaults to "anthropic" / Claude):

    export LLM_PROVIDER=openai            # ChatGPT -- needs a REAL platform.openai.com
    export OPENAI_API_KEY=sk-...          # key, NOT your ChatGPT Plus login (see README)
    python demo/run_real_meetingbank.py

    export LLM_PROVIDER=openrouter
    export OPENROUTER_API_KEY=sk-or-...
    python demo/run_real_meetingbank.py

    export LLM_PROVIDER=anthropic         # default if LLM_PROVIDER isn't set
    export ANTHROPIC_API_KEY=sk-ant-...
    python demo/run_real_meetingbank.py
"""
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
from datetime import datetime
from tqdm import tqdm
from neo4j.exceptions import Neo4jError, ServiceUnavailable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.graph_store import TemporalGraphStore
from core.pipeline import ingest_meeting
from core.retrieval import retrieve_hybrid
from core.qa import answer_question
from core.llm_connectors import build_connector
from core.graph_store_neo4j import Neo4jGraphStore
from data.meetingbank_loader import load_meetingbank_hf

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")

DEMO_QUESTIONS = [
    "What ordinances or bills were discussed across these meetings?",
    "Which council members or officials are mentioned, and what did they do?",
]

def main():
    print(f"LLM_PROVIDER={LLM_PROVIDER}")
    connector = build_connector(LLM_PROVIDER)  # raises clearly if the matching API key isn't set
    print(f"Connector ready: {connector.name}\n")

    # Initialize Neo4j Handler and constraints
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD")
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
    if not neo4j_password:
        raise ValueError("Set NEO4J_PASSWORD before running the real MeetingBank Neo4j demo.")
    try:
        neo4j_handler = Neo4jGraphStore(neo4j_uri, neo4j_user, neo4j_password, database=neo4j_database)
    except ServiceUnavailable as exc:
        raise RuntimeError(
            "Could not connect to Neo4j. Start your Neo4j DBMS and confirm "
            f"NEO4J_URI={neo4j_uri!r}, NEO4J_USER={neo4j_user!r}, and "
            f"NEO4J_DATABASE={neo4j_database!r} are correct."
        ) from exc
    except Neo4jError as exc:
        raise RuntimeError(
            "Neo4j rejected the connection or setup query. Check the Neo4j "
            "password, database name, and server version."
        ) from exc

    store = TemporalGraphStore(path=None)  # Disable file storage since all in Neo4j

    MEETINGS = load_meetingbank_hf("train[:20]", max_meetings=3)
    print(f"Loaded {len(MEETINGS)} merged meetings from Hugging Face\n")
    print("=" * 70)
    print("PHASE 1 -- INGESTING MEETINGS")
    print("=" * 70)

    usage_stats = {}
    error_chunks_all = []
    progress = tqdm(MEETINGS, desc="Meetings")

    for m in progress:
        meeting_id = m["meeting_id"]
        date = m["date"]
        transcript = m["transcript"]
        print(f"Ingesting {meeting_id} ({len(transcript)} chars)...")

        # Ingest meeting, store data in Neo4j
        report = ingest_meeting(
            store,
            transcript, meeting_id, date,
            connector=connector,
            neo4j_handler=neo4j_handler,
            usage_stats=usage_stats
        )
        print(f"  -> {report['entities_seen']} entities seen, {report['facts_extracted']} facts extracted, "
              f"{len(report['new_entities'])} new entities")

        # Collect parsing errors
        if report.get("parse_error_chunks"):
            error_chunks_all.extend(report["parse_error_chunks"])

    print("\n" + "=" * 70)
    print(f"GRAPH BUILT: {len(store.all_entities())} entities, {len(store.all_relations())} relations")
    print("=" * 70)
    for eid, ent in list(store.all_entities().items())[:30]:
        print(f"  {ent.canonical_name}  ({ent.entity_type})")
    if len(store.all_entities()) > 30:
        print(f"  ... and {len(store.all_entities()) - 30} more")

    print("\n" + "=" * 70)
    print("QA")
    print("=" * 70)

    qa_results = []
    for q in DEMO_QUESTIONS:
        evidence = retrieve_hybrid(store, q)
        answer = answer_question(q, evidence, connector=connector)
        qa_entry = {
            "meeting_id": None, # Optional: set meeting_id if you want
            "question": q,
            "answer": answer,
            "evidence_retrieved": evidence
        }
        qa_results.append(qa_entry)
        print(f"\nQ: {q}")
        print(f"  ({len(evidence)} evidence items retrieved)")
        print(f"  A: {answer}")

    # Save QA results in Neo4j
    for qa_log in qa_results:
        neo4j_handler.insert_qa_log(qa_log)

    # Show errors summary
    if error_chunks_all:
        print("\nERRORS during extraction (some chunks failed to parse LLM output):")
        for err in error_chunks_all:
            print(f"  - meeting_id: {err['meeting_id']}, chunk: {err.get('chunk_idx', '?')}, error: {err.get('parse_error')}")

    neo4j_handler.close()

if __name__ == "__main__":
    main()


