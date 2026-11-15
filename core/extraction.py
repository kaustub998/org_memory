"""
Layer 1: Extraction.
Pulls candidate entities and (subject, relation, object) facts out of a
raw meeting transcript chunk using an LLM call with a strict JSON schema.
This layer is built to full quality from day one -- it's not one of the
two research components, so there's no reason to keep it naive.

Accepts an injected LLMConnector (see core/llm_connectors.py) so you can
run extraction through Claude, Groq, Gemini, or any other provider --
defaults to Claude if none is given, so existing calls keep working.
"""
import json
from .types import ExtractedEntity, ExtractedFact, new_id
from .llm_connectors import LLMConnector, build_connector

_default_connector: LLMConnector | None = None

EXTRACTION_SYSTEM_PROMPT = """You extract structured knowledge from organizational meeting transcripts.

Return ONLY a JSON object, no preamble, no markdown fences, matching exactly this shape:
{
  "entities": [
    {"name": "<surface form as it appears in the text>", "type": "PERSON|ROLE|PROJECT|DEPARTMENT|POLICY|ORGANIZATION|OTHER", "context": "<the sentence it appeared in>"}
  ],
  "facts": [
    {"subject": "<surface form>", "relation": "<short snake_case relation, e.g. leads, reports_to, responsible_for, renamed_to, status_of>", "object": "<surface form>", "context": "<the sentence it appeared in>"}
  ]
}

Rules:
- Only extract facts that are explicitly stated or clearly implied, never invent details.
- Keep relation names short and reusable across meetings (e.g. "leads", "member_of", "responsible_for", "status_is", "renamed_to").
- Use the exact surface form for names (don't normalize "Sarah" to "Sarah Chen" yourself -- that's a downstream step).
- If nothing is extractable, return {"entities": [], "facts": []}.
"""


import os

def extract_from_transcript(
    transcript_text: str, meeting_id: str, meeting_date: str,
    connector: LLMConnector | None = None,
    error_log_dir: str = None,
    chunk_idx: int = None
) -> tuple[list[ExtractedEntity], list[ExtractedFact], dict]:
    """
    Calls the LLM once on a transcript chunk and parses structured output. Logs raw output and errors for robustness if requested.
    Returns (entities, facts, info_dict) where info_dict contains details on error status, raw output, etc.
    """
    global _default_connector
    if connector is None:
        if _default_connector is None:
            _default_connector = build_connector("anthropic")
        connector = _default_connector

    raw = connector.complete(EXTRACTION_SYSTEM_PROMPT, transcript_text, max_tokens=2000).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    info = {
        "meeting_id": meeting_id,
        "chunk_idx": chunk_idx,
        "status": "success",
        "raw_output": raw,
        "entities_cnt": 0,
        "facts_cnt": 0,
        "parse_error": None,
    }
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        info["status"] = "parse_error"
        info["parse_error"] = str(e)
        if error_log_dir:
            os.makedirs(error_log_dir, exist_ok=True)
            fname = os.path.join(error_log_dir, f"meeting_{meeting_id}_chunk_{chunk_idx or 0}.json")
            with open(fname, "w", encoding="utf-8") as f:
                json.dump({
                    "meeting_id": meeting_id,
                    "chunk_idx": chunk_idx,
                    "raw_output": raw,
                    "error": str(e),
                    "transcript_input": transcript_text[:1200],
                }, f, indent=2)
        print(f"[extraction] WARNING: could not parse LLM output for {meeting_id} chunk {chunk_idx}:\n{raw[:300]}")
        return [], [], info

    entities = [
        ExtractedEntity(
            mention_id=new_id("ent"),
            name=e["name"],
            entity_type=e.get("type", "OTHER"),
            context=e.get("context", ""),
        )
        for e in parsed.get("entities", [])
    ]
    facts = [
        ExtractedFact(
            fact_id=new_id("fact"),
            subject=f["subject"],
            relation=f["relation"],
            obj=f["object"],
            context=f.get("context", ""),
            meeting_id=meeting_id,
            timestamp=meeting_date,
        )
        for f in parsed.get("facts", [])
    ]
    info["entities_cnt"] = len(entities)
    info["facts_cnt"] = len(facts)
    return entities, facts, info

