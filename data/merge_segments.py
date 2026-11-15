"""
MeetingBank segment merger.

MeetingBank's HF release returns SEGMENT-level records (6,892 of them),
not whole meetings -- several segments share one parent-meeting summary
because they're different transcript slices of the same agenda item.
This script groups segments by identical summary text, concatenates
their transcripts in id order, and assigns one placeholder date per
MERGED meeting (not per segment) so segments of the same session don't
get spread across fake different days.

Usage:
    python data/merge_segments.py /path/to/meetingbank_slice.json /path/to/merged_output.json
"""
import json
import sys
from collections import defaultdict
from datetime import date, timedelta


def merge_segments(records: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for r in records:
        # Segments with no summary at all are treated as their own group
        # rather than silently merged with other summary-less segments.
        key = r.get("summary") or f"__no_summary__{r['id']}"
        groups[key].append(r)

    merged = []
    base_date = date(2024, 1, 1)
    for i, (summary, segs) in enumerate(sorted(groups.items(), key=lambda kv: min(s["id"] for s in kv[1]))):
        segs_sorted = sorted(segs, key=lambda s: s["id"])
        merged_transcript = "\n\n".join(s["transcript"] for s in segs_sorted)
        meeting_date = (base_date + timedelta(days=i)).isoformat()
        merged.append({
            "meeting_id": f"meeting_{i:03d}_segs_{'-'.join(str(s['id']) for s in segs_sorted)}",
            "transcript": merged_transcript,
            "summary": summary if not summary.startswith("__no_summary__") else "",
            "date": meeting_date,          # PLACEHOLDER -- replace with real dates if you get them
            "source_segment_ids": [s["id"] for s in segs_sorted],
        })
    return merged


if __name__ == "__main__":
    in_path = sys.argv[1] if len(sys.argv) > 1 else "meetingbank_slice.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "meetingbank_slice_merged.json"

    with open(in_path) as f:
        records = json.load(f)

    merged = merge_segments(records)

    with open(out_path, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"Merged {len(records)} segments into {len(merged)} meetings -> {out_path}")
    for m in merged:
        print(f"  {m['meeting_id']}  (segments {m['source_segment_ids']}, "
              f"{len(m['transcript'])} chars, date={m['date']})")
