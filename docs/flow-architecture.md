# Organizational Memory Flow Architecture

## 1. System Goal

This project builds an organizational memory layer over meeting transcripts and other organizational artifacts. The core idea is:

- extract facts and entities from raw organizational text,
- resolve mentions to canonical people/projects/departments,
- store historical states in a temporal graph,
- retrieve relevant evidence using graph + vector signals,
- answer organizational questions with traceable evidence.

The system is designed to be modular so the research-heavy parts can later be upgraded without reworking the entire pipeline.

---

## 2. High-Level Pipeline

The operational flow is:

1. Load meeting or transcript data
2. Chunk long text into manageable units
3. Extract entities and facts with an LLM
4. Resolve extracted mentions to canonical graph entities
5. Apply temporal update rules to the graph
6. Persist the graph state
7. Retrieve relevant graph and semantic evidence
8. Generate a grounded answer with citation-like evidence references

In code, the main orchestration is in [core/pipeline.py](../core/pipeline.py).

---

## 3. Data Flow by Layer

### A. Input layer

Sources may include:

- synthetic council transcripts,
- real MeetingBank records,
- future organizational documents or meeting logs.

The loader normalizes records into a consistent format. See:

- [data/meetingbank_loader.py](../data/meetingbank_loader.py)
- [demo/synthetic_meetings.py](../demo/synthetic_meetings.py)

Expected normalized shape:

- meeting_id
- transcript
- summary
- date
- city

---

### B. Chunking layer

Long transcripts are chunked before extraction.

Relevant code:

- [core/pipeline.py](../core/pipeline.py)

Why this matters:

- LLM calls are bounded by prompt size and context length,
- MeetingBank transcripts can be very long,
- chunking ensures each extraction call stays within a practical token budget.

Chunking strategy:

- split by paragraphs first,
- split long paragraphs on sentence boundaries,
- hard-split oversized text if needed.

---

### C. Extraction layer

The extraction stage converts raw transcript chunks into structured knowledge.

Relevant code:

- [core/extraction.py](../core/extraction.py)

Output:

- list of entity mentions
- list of fact triples

Each extracted fact carries:

- subject
- relation
- object
- meeting_id
- timestamp
- context

The LLM is instructed to return strict JSON so the pipeline can parse it reliably.

---

### D. Entity resolution layer

Extracted mentions often vary in surface form, for example:

- Sarah
- Sarah Chen
- Director of Public Works
- the PM

The resolver maps these to canonical graph entities.

Relevant code:

- [core/entity_resolution.py](../core/entity_resolution.py)

Current Phase 1 approach:

- exact name match
- alias match
- TF-IDF similarity fallback
- otherwise create a new entity

This is intentionally conservative and precision-first.

---

### E. Graph update layer

Once entities are resolved, extracted facts are applied to the temporal graph.

Relevant code:

- [core/update_policy.py](../core/update_policy.py)

Behavior:

- INSERT when a new subject-relation combination appears,
- UPDATE when the same fact reappears,
- SUPERSEDE when the same subject and relation change to a different object.

This gives the graph a time-aware state model rather than just a flat set of facts.

---

### F. Temporal graph store

The graph is the system’s memory layer.

Relevant code:

- [core/graph_store.py](../core/graph_store.py)
- [core/graph_store_neo4j.py](../core/graph_store_neo4j.py)

The graph stores:

- entities as canonical nodes
- aliases for name variation
- relations with valid_from / valid_to
- provenance and confidence
- status = active | superseded | preserved

This supports historical reasoning and temporal tracking of organizational change.

---

### G. Retrieval layer

After the graph has been populated, the next step is to answer queries by retrieving the most relevant evidence.

Relevant code:

- [core/retrieval.py](../core/retrieval.py)

The system combines:

- graph retrieval: match names/entities in the query, pull their current and historical relations,
- vector retrieval: score relation provenance text semantically,
- deduplicate and merge the resulting evidence.

This produces a focused evidence set for the question-answering stage.

---

### H. QA layer

The final pipeline step is evidence-grounded question answering.

Relevant code:

- [core/qa.py](../core/qa.py)

The model is instructed to:

- answer using only the provided evidence,
- be explicit when evidence is insufficient or conflicting,
- cite evidence fragments at the end.

This reduces hallucination and keeps answers traceable.

---

## 4. End-to-End Flow Example

Consider a question like:

> Who is currently the Project Manager for Riverfront Park Renewal?

The flow is:

1. Query matches relevant entity names in the graph
2. Graph retrieval pulls active and historical role relations
3. Vector retrieval finds relevant provenance text
4. Evidence is deduplicated and ordered
5. The QA model answers using only the evidence list
6. The answer cites the matching snippets / related meetings

---

## 5. Key Architectural Principle

The project separates concerns clearly:

- extraction focuses on extraction quality,
- resolution focuses on identity alignment,
- the graph preserves historical truth,
- retrieval focuses on evidence selection,
- QA focuses on grounded synthesis.

This decomposition makes the system easier to improve incrementally, especially in a research setting.

---

## 6. Known Research Gaps (Intentionally Left Naive)

The README describes the project as a working baseline with the two major research targets intentionally left simple for now:

- entity resolution is naive and single-signal
- update policy is fixed-rule and simplistic

The project is designed so these can be upgraded in Phase 2 without disturbing the rest of the architecture.

---

## 7. Provider and Backend Abstractions

The system supports multiple LLM providers and multiple embedding backends through abstraction layers:

- [core/llm_connectors.py](../core/llm_connectors.py)
- [core/embeddings.py](../core/embeddings.py)

This allows:

- switching between Anthropic/OpenAI/Groq/Gemini/etc.,
- fallback between providers,
- using local sentence-transformers or OpenAI embeddings,
- keeping the rest of the pipeline unchanged.

---

## 8. Recommended Mental Model

Think of the project as a temporal organizational memory stack:

- text in
- structured knowledge out
- graph memory as the source of truth
- retrieval as the evidence selector
- LLM as the final reasoner

This is essentially a graph-backed RAG system for organizational knowledge.

---

## 9. Where to Look When Changing the System

- extraction logic: [core/extraction.py](../core/extraction.py)
- entity matching: [core/entity_resolution.py](../core/entity_resolution.py)
- graph logic: [core/graph_store.py](../core/graph_store.py)
- temporal update semantics: [core/update_policy.py](../core/update_policy.py)
- evidence retrieval: [core/retrieval.py](../core/retrieval.py)
- final answer generation: [core/qa.py](../core/qa.py)
- pipeline orchestration: [core/pipeline.py](../core/pipeline.py)

---

## 10. Project Direction

The current version is a working baseline that proves the architecture can operate end-to-end. The next research-oriented stage should improve:

1. contextual entity resolution,
2. conflict-aware update policy,
3. stronger temporal reasoning,
4. more robust evidence ranking.

That makes the architecture a strong foundation for a proper research iteration.
