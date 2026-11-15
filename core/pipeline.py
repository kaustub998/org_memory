"""
Orchestrator: wires Extraction -> Entity Resolution -> Update Policy ->
Graph Store together for one meeting at a time. This is the "six-layer
pipeline" from Slide 14/15, minus the sophistication in layers 2 and 4
(marked BASIC BLOCK in their respective files).
"""
from .extraction import extract_from_transcript
from .entity_resolution import BasicEntityResolver
from .update_policy import apply_fact
from .graph_store import TemporalGraphStore

resolver = BasicEntityResolver()

MAX_CHUNK_CHARS = 12000  # real MeetingBank transcripts run ~28k tokens; chunk to stay well within one call


def _chunk_transcript(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Paragraph-aware chunking that also hard-splits any single paragraph
    longer than max_chars on its own (sentence boundaries where possible).
    Real-world transcripts -- especially merged MeetingBank segments --
    are often one giant unbroken block with no internal newlines, so
    paragraph splitting alone is not sufficient."""
    if len(text) <= max_chars:
        return [text]

    def _hard_split(block: str) -> list[str]:
        """Split an oversized block on sentence boundaries, packing as
        many sentences as fit under max_chars per piece."""
        if len(block) <= max_chars:
            return [block]
        sentences = block.replace("? ", "?|").replace("! ", "!|").replace(". ", ".|").split("|")
        pieces, current = [], ""
        for s in sentences:
            if len(current) + len(s) + 1 > max_chars and current:
                pieces.append(current)
                current = s
            else:
                current = f"{current} {s}" if current else s
        if current:
            pieces.append(current)
        # Pathological case: a single "sentence" itself exceeds max_chars
        # (no punctuation at all) -- fall back to a hard character slice.
        final = []
        for p in pieces:
            if len(p) <= max_chars:
                final.append(p)
            else:
                final.extend(p[i:i + max_chars] for i in range(0, len(p), max_chars))
        return final

    paragraphs = text.split("\n")
    chunks, current = [], ""
    for p in paragraphs:
        if len(p) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(p))
            continue
        if len(current) + len(p) + 1 > max_chars and current:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


import json
from typing import Optional, IO

def ingest_meeting(store: TemporalGraphStore, transcript_text: str, meeting_id: str, meeting_date: str,
                    connector=None, log_file: Optional[IO]=None, error_log_dir: str = None, usage_stats: dict = None) -> dict:
    """
    Runs one meeting through the full pipeline. Logs per-chunk extraction errors, aggregates provider usage if usage_stats is given.
    Returns a report dictionary for the meeting.
    Now supports error_log_dir for failed extractions, and can update usage_stats in place.
    """
    entities, facts = [], []
    extraction_infos = []
    chunk_idx = 0
    for chunk in _chunk_transcript(transcript_text):
        e, f, info = extract_from_transcript(chunk, meeting_id, meeting_date, connector=connector, error_log_dir=error_log_dir, chunk_idx=chunk_idx)
        entities.extend(e)
        facts.extend(f)
        extraction_infos.append(info)
        chunk_idx += 1
    
    # Usage statistics tracking
    if usage_stats is not None and connector is not None:
        usage = connector.get_usage()
        if meeting_id not in usage_stats:
            usage_stats[meeting_id] = usage
        else:
            # aggregate
            for k in ["input_tokens", "output_tokens", "total_tokens", "calls"]:
                usage_stats[meeting_id][k] += usage.get(k, 0)
            usage_stats[meeting_id]["models_used"].extend(usage.get("models_used", []))
    
    # Resolve every mentioned entity first, so facts can reference resolved IDs.
    name_to_id = {}
    new_entities = []
    for mention in entities:
        entity_id, is_new = resolver.resolve(mention, store.all_entities())
        store.upsert_entity(entity_id, mention.name, mention.entity_type,
                             alias=mention.name, timestamp=meeting_date)
        name_to_id[mention.name] = entity_id
        if is_new:
            new_entities.append((mention.name, entity_id))

    def _resolve_name(name: str) -> str:
        if name in name_to_id:
            return name_to_id[name]
        from .types import ExtractedEntity, new_id
        mention = ExtractedEntity(mention_id=new_id("ent"), name=name, entity_type="OTHER", context="")
        entity_id, is_new = resolver.resolve(mention, store.all_entities())
        store.upsert_entity(entity_id, name, "OTHER", alias=name, timestamp=meeting_date)
        name_to_id[name] = entity_id
        if is_new:
            new_entities.append((name, entity_id))
        return entity_id

    operations = []
    for fact in facts:
        before_state = {
            "entities": {k: v.__dict__ for k, v in store.all_entities().items()},
            "relations": [rel.__dict__ for rel in store.all_relations()]
        }
        subj_id = _resolve_name(fact.subject)
        obj_id = _resolve_name(fact.obj)
        op = apply_fact(store, subj_id, obj_id, fact)
        after_state = {
            "entities": {k: v.__dict__ for k, v in store.all_entities().items()},
            "relations": [rel.__dict__ for rel in store.all_relations()]
        }
        operations.append((op, fact.subject, fact.relation, fact.obj))
        if log_file is not None:
            log_file.write(json.dumps({
                "step": "fact_application",
                "meeting_id": meeting_id,
                "fact": fact.__dict__,
                "operation": op,
                "before_state": before_state,
                "after_state": after_state,
            }) + "\n")

    store.save()
    # Track error chunks, summarize them for return for batch stats if desired
    parse_errors = [info for info in extraction_infos if info["status"] != "success"]
    return {
        "meeting_id": meeting_id,
        "entities_seen": len(entities),
        "new_entities": new_entities,
        "facts_extracted": len(facts),
        "operations": operations,
        "parse_error_chunks": parse_errors,
        "all_chunk_infos": extraction_infos,
    }
