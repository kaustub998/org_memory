"""
Layer 2: Entity Resolution -- PHASE 1 BASIC BLOCK.

This is deliberately the naive version described in your proposal's
Phase 1: a single similarity signal (exact/alias match + TF-IDF cosine
on name+context) against a fixed threshold. No multi-signal scoring,
no LLM verification of ambiguous cases, no DEFER/FLAG escalation --
those are the Phase 2 research contribution (see docs/phase2_notes.md).

Design choice carried over from the precision-first discussion:
below the threshold we ALWAYS create a new entity rather than force a
merge. That one habit is worth keeping even in the naive version,
since a false merge is much harder to undo later than a duplicate node.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from .types import GraphEntity, ExtractedEntity, new_id

MATCH_THRESHOLD = 0.72  # tune this; conservative on purpose (precision > recall)


def _normalize(name: str) -> str:
    return name.strip().lower()


class BasicEntityResolver:
    """
    Naive resolver: exact/alias string match first, then a single TF-IDF
    cosine-similarity signal over "name + context" as a fallback.
    Swap this class out wholesale in Phase 2 without touching callers --
    resolve() is the only method the rest of the pipeline calls.
    """

    def __init__(self):
        self._vectorizer = TfidfVectorizer()

    def resolve(self, mention: ExtractedEntity, graph_entities: dict[str, GraphEntity]) -> tuple[str, bool]:
        """
        Returns (entity_id, is_new_entity).
        """
        mention_norm = _normalize(mention.name)

        # 1. Exact / alias match (cheap, high precision, do this first)
        for ent_id, ent in graph_entities.items():
            if mention_norm == _normalize(ent.canonical_name):
                return ent_id, False
            if mention_norm in [_normalize(a) for a in ent.aliases]:
                return ent_id, False

        # 2. Single-signal similarity fallback (name + context vs canonical + aliases)
        if graph_entities:
            candidates = list(graph_entities.items())
            corpus = [f"{mention.name} {mention.context}"] + [
                f"{ent.canonical_name} {' '.join(ent.aliases)}" for _, ent in candidates
            ]
            try:
                tfidf = self._vectorizer.fit_transform(corpus)
                sims = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
                best_idx = int(np.argmax(sims))
                if sims[best_idx] >= MATCH_THRESHOLD:
                    return candidates[best_idx][0], False
            except ValueError:
                pass  # empty vocabulary etc. -- fall through to new entity

        # 3. Below threshold -> new entity (precision-first: don't guess)
        new_entity_id = new_id("entity")
        return new_entity_id, True
