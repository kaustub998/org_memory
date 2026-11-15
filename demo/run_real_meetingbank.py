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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.graph_store import TemporalGraphStore
from core.pipeline import ingest_meeting
from core.retrieval import retrieve_hybrid
from core.qa import answer_question
from core.llm_connectors import build_connector
from data.meetingbank_loader import load_meetingbank_hf

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "meetingbank_slice_merged.json")
STORE_PATH = os.path.join(os.path.dirname(__file__), "real_meetingbank_graph.json")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOGS_BASEDIR = os.path.join(os.path.dirname(__file__), f"extraction_logs_{timestamp}")
PER_MEETING_LOGS = os.path.join(LOGS_BASEDIR, "meeting_logs")
ERROR_LOG_DIR = os.path.join(LOGS_BASEDIR, "failed_extractions")
ERROR_SUMMARY_LOG = os.path.join(LOGS_BASEDIR, "error_log.jsonl")
USAGE_SUMMARY_FILE = os.path.join(LOGS_BASEDIR, "usage_summary.json")
os.makedirs(PER_MEETING_LOGS, exist_ok=True)
os.makedirs(ERROR_LOG_DIR, exist_ok=True)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")

# Generic questions that should work regardless of which specific agenda
# items ended up in your slice -- edit these once you've seen what
# entities/relations actually got extracted.
DEMO_QUESTIONS = [
    "What ordinances or bills were discussed across these meetings?",
    "Which council members or officials are mentioned, and what did they do?",
]

import time

class ProgressTracker:
    """
    Tracks overall MeetingBank processing progress.

    Example:

    Processing MeetingBank:
    [████████████████░░░░░░░░] 68.0% | 680/1000 | ETA: 18m 32s
    """

    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.start_time = time.perf_counter()

    def update(self, completed: int | None = None):
        if completed is not None:
            self.completed = completed
        else:
            self.completed += 1

        elapsed = time.perf_counter() - self.start_time

        if self.completed > 0:
            avg_time = elapsed / self.completed
            remaining = self.total - self.completed
            eta_seconds = avg_time * remaining
        else:
            eta_seconds = 0

        percentage = (
            self.completed / self.total * 100
            if self.total
            else 0
        )

        bar_length = 30
        filled = int(
            bar_length * self.completed / self.total
        ) if self.total else 0

        bar = (
            "█" * filled
            + "░" * (bar_length - filled)
        )

        eta = self._format_time(eta_seconds)

        sys.stdout.write(
            f"\rProcessing MeetingBank: "
            f"[{bar}] "
            f"{percentage:6.2f}% | "
            f"{self.completed}/{self.total} | "
            f"ETA: {eta}"
        )

        sys.stdout.flush()

        if self.completed >= self.total:
            print()

    @staticmethod
    def _format_time(seconds: float) -> str:

        seconds = int(seconds)

        hours, remainder = divmod(
            seconds,
            3600
        )

        minutes, seconds = divmod(
            remainder,
            60
        )

        if hours:
            return f"{hours}h {minutes}m {seconds}s"

        if minutes:
            return f"{minutes}m {seconds}s"

        return f"{seconds}s"

def main():
    print(f"LLM_PROVIDER={LLM_PROVIDER}")
    connector = build_connector(LLM_PROVIDER)  # raises clearly if the matching API key isn't set
    print(f"Connector ready: {connector.name}\n")

    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)
    store = TemporalGraphStore(path=STORE_PATH)

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

        per_meeting_log_file = os.path.join(PER_MEETING_LOGS, f"meeting_{meeting_id}.json")
        with open(per_meeting_log_file, "w", encoding="utf-8") as logf:
            report = ingest_meeting(
                store,
                transcript, meeting_id, date,
                connector=connector,
                log_file=logf,
                error_log_dir=ERROR_LOG_DIR,
                usage_stats=usage_stats
            )
            json.dump({
                "step": "meeting_summary",
                "meeting_id": meeting_id,
                "date": date,
                **report
            }, logf, indent=2)
        print(f"  -> {report['entities_seen']} entities seen, {report['facts_extracted']} facts extracted, "
              f"{len(report['new_entities'])} new entities")
        # Append parsing errors for this meeting to centralized report
        if report.get("parse_error_chunks"):
            error_chunks_all.extend(report["parse_error_chunks"])
            with open(ERROR_SUMMARY_LOG, "a", encoding="utf-8") as ef:
                for err_info in report["parse_error_chunks"]:
                    ef.write(json.dumps(err_info) + "\n")

    # Write usage summary
    with open(USAGE_SUMMARY_FILE, "w", encoding="utf-8") as usf:
        json.dump(usage_stats, usf, indent=2)

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
    # Save the results of QA as a separate file for audibility.
    qa_results = []
    for q in DEMO_QUESTIONS:
        evidence = retrieve_hybrid(store, q)
        answer = answer_question(q, evidence, connector=connector)
        qa_entry = {
            "step": "qa",
            "question": q,
            "evidence_retrieved": evidence,
            "answer": answer
        }
        qa_results.append(qa_entry)
        print(f"\nQ: {q}")
        print(f"  ({len(evidence)} evidence items retrieved)")
        print(f"  A: {answer}")
    qa_file = os.path.join(LOGS_BASEDIR, "qa_results.json")
    with open(qa_file, "w", encoding="utf-8") as qf:
        json.dump(qa_results, qf, indent=2)

    # Finally, summarize errors if there were any
    if error_chunks_all:
        print("\nERRORS during extraction (some chunks failed to parse LLM output):")
        for err in error_chunks_all:
            print(f"  - meeting_id: {err['meeting_id']}, chunk: {err.get('chunk_idx', '?')}, error: {err.get('parse_error')}")
        print(f"Full error details saved in {ERROR_SUMMARY_LOG}\n")
    print(f"Full meeting logs in folder: {PER_MEETING_LOGS}\n")
    print(f"Usage summary: {USAGE_SUMMARY_FILE}\n")

if __name__ == "__main__":
    main()


