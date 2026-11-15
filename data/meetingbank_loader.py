"""
Loader for MeetingBank data (Hu et al., 2023).

MeetingBank's released records look like:
    {"id": "...", "summary": "...", "transcript": "...", ...}
sometimes with extra metadata (city, date, item type) depending on
which release file you have (main JSON / HF splits / Zenodo export).

This loader is intentionally forgiving about the exact key names so you
can point it at whatever slice of MeetingBank you have locally --
just upload a JSON (list of records) or JSONL file and set the path
below. If your file uses different field names, adjust FIELD_MAP.

Usage:
    from data.meetingbank_loader import load_meetingbank
    meetings = load_meetingbank("path/to/your_meetingbank_slice.json")
    for m in meetings:
        ingest_meeting(store, m["transcript"], m["meeting_id"], m["date"])
"""
import json
import os

FIELD_MAP = {
    "id": ["id", "meeting_id", "uid"],
    "transcript": ["transcript", "text", "full_transcript"],
    "summary": ["summary", "reference_summary"],
    "date": ["date", "meeting_date", "session_date"],
    "city": ["city", "source_city", "municipality"],
}


def _first_present(record: dict, keys: list[str], default=None):
    for k in keys:
        if k in record and record[k]:
            return record[k]
    return default


def load_meetingbank(path: str) -> list[dict]:
    """Returns a list of {"meeting_id", "transcript", "summary", "date", "city"} dicts."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Upload a MeetingBank JSON/JSONL slice and point this loader at it."
        )

    records = []
    if path.endswith(".jsonl"):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    else:
        with open(path) as f:
            data = json.load(f)
        records = data if isinstance(data, list) else data.get("data", [data])

    normalized = []
    for i, r in enumerate(records):
        normalized.append({
            "meeting_id": str(_first_present(r, FIELD_MAP["id"], default=f"meeting_{i}")),
            "transcript": _first_present(r, FIELD_MAP["transcript"], default=""),
            "summary": _first_present(r, FIELD_MAP["summary"], default=""),
            # MeetingBank transcripts don't always carry an explicit date field --
            # fall back to a placeholder so the temporal graph still has something
            # monotonic to sort on; replace with real dates if your slice has them.
            "date": _first_present(r, FIELD_MAP["date"], default=f"2024-01-{i+1:02d}"),
            "city": _first_present(r, FIELD_MAP["city"], default="unknown"),
        })
    return normalized

def load_meetingbank_hf(split: str = "train[:100]", merge_segments: bool = True,
                        max_meetings: int | None = None) -> list[dict]:
    """
    Loads MeetingBank straight from Hugging Face instead of a local JSON file.
    Segments sharing an identical summary are merged into one meeting, in the
    order they appear. Dates are still placeholders (HF has no date field).
    max_meetings caps the result, to limit API cost while testing.
    """
    from datetime import date, timedelta
    from datasets import load_dataset

    ds = load_dataset("huuuyeah/meetingbank", split=split)
    print(f"[meetingbank] loaded {len(ds)} segments from Hugging Face "
          f"(split={split}); columns={ds.column_names}")

    segments = []
    for i, r in enumerate(ds):
        segments.append({
            "seg_id": str(r.get("id", i)),
            "transcript": r.get("transcript", "") or "",
            "summary": r.get("summary", "") or "",
        })

    base_date = date(2024, 1, 1)

    if not merge_segments:
        groups = [[s] for s in segments]
    else:
        ordered = {}  # dict keeps first-appearance order
        for s in segments:
            key = s["summary"] or f"__no_summary__{s['seg_id']}"
            ordered.setdefault(key, []).append(s)
        groups = list(ordered.values())

    if max_meetings is not None:
        groups = groups[:max_meetings]

    meetings = []
    for i, segs in enumerate(groups):
        meetings.append({
            "meeting_id": f"meeting_{i:03d}_segs_{'-'.join(s['seg_id'] for s in segs)}",
            "transcript": "\n\n".join(s["transcript"] for s in segs),
            "summary": segs[0]["summary"],
            "date": (base_date + timedelta(days=i)).isoformat(),
            "city": "unknown",
            "source_segment_ids": [s["seg_id"] for s in segs],
        })
    return meetings