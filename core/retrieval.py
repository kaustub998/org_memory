"""
Layer: Hybrid Retrieval.

This is NOT one of the two research components, so it's built to full
spec now rather than left naive. Two retrieval paths, combined:

  - Graph retrieval: given entities named/matched in the query, pull
    their active relations (their current "state" in the org).
  - Vector retrieval: real sentence embeddings (all-MiniLM-L6-v2) over
    relation provenance text, with automatic fallback to TF-IDF if the
    embedding model isn't available in the current environment (see
    core/embeddings.py) -- so this module works unmodified in both this
    sandbox (TF-IDF) and your machine (real embeddings), and you can tell
    which is active from the printed startup message or EMBEDDING_BACKEND
    below.

Both evidence sets are merged, deduplicated, and handed to the LLM to
generate the final answer -- this is the base-RAG-plus-graph formulation
from your methodology slide.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from . import embeddings
from .graph_store import TemporalGraphStore
from .types import GraphRelation

EMBEDDING_BACKEND = "sentence-transformers" if embeddings.USING_REAL_EMBEDDINGS else "tfidf"


def _fmt_relation(store: TemporalGraphStore, rel: GraphRelation) -> str:
    subj = store.get_entity(rel.subject_id)
    obj = store.get_entity(rel.object_id)
    s_name = subj.canonical_name if subj else rel.subject_id
    o_name = obj.canonical_name if obj else rel.object_id
    tag = "" if rel.status == "active" else f" [superseded, valid until {rel.valid_to}]"
    return f"{s_name} --{rel.relation}--> {o_name} (since {rel.valid_from}){tag}  [source: {rel.provenance}]"


def retrieve_graph(store: TemporalGraphStore, query: str, top_k_entities: int = 3) -> list[str]:
    """Naive entity matching against canonical names/aliases, then pull their relations."""
    query_lower = query.lower()
    matched_ids = []
    for ent_id, ent in store.all_entities().items():
        names = [ent.canonical_name] + ent.aliases
        if any(n.lower() in query_lower for n in names):
            matched_ids.append(ent_id)

    evidence = []
    for ent_id in matched_ids[:top_k_entities]:
        for rel in store.relations_for_entity(ent_id):
            evidence.append(_fmt_relation(store, rel))
    return evidence


def retrieve_vector(store: TemporalGraphStore, query: str, top_k: int = 5) -> list[str]:
    """Semantic similarity over ALL relation provenance text. Uses real
    sentence embeddings when available (see EMBEDDING_BACKEND), else
    falls back to TF-IDF automatically -- same function signature either
    way, so callers never need to know which backend is active."""
    all_rels = store.all_relations()
    if not all_rels:
        return []
    docs = [f"{r.relation} {r.provenance}" for r in all_rels]

    if embeddings.USING_REAL_EMBEDDINGS:
        doc_vecs = embeddings.embed(docs)
        query_vec = embeddings.embed([query])[0]
        sims = embeddings.cosine_sim_matrix(query_vec, doc_vecs)
    else:
        try:
            vec = TfidfVectorizer().fit_transform([query] + docs)
        except ValueError:
            return []
        sims = cosine_similarity(vec[0:1], vec[1:]).flatten()

    top_idx = np.argsort(sims)[::-1][:top_k]
    return [_fmt_relation(store, all_rels[i]) for i in top_idx if sims[i] > 0]


def retrieve_hybrid(store: TemporalGraphStore, query: str) -> list[str]:
    graph_ev = retrieve_graph(store, query)
    vector_ev = retrieve_vector(store, query)
    # dedupe while preserving order, graph evidence first (it's higher-precision)
    seen = set()
    combined = []
    for ev in graph_ev + vector_ev:
        if ev not in seen:
            seen.add(ev)
            combined.append(ev)
    return combined
