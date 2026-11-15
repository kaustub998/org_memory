# Project Plan for the Organizational Memory System

## 1. Project Objective

Build a working organizational memory system that can ingest meeting transcripts, extract structured knowledge, track temporal updates, retrieve relevant evidence, and answer organizational questions with grounded answers.

The current project is intentionally structured as a working baseline first, with advanced research features planned as later upgrades.

---

## 2. Current Status

### Output and Monitoring Enhancements

- Pipeline runs now log all extracted entities, facts, and summary/operation logs for each meeting as individual output records to a file (typically `extraction_log.jsonl`).
- A progress bar/tracker displays per-meeting status in the terminal for transparent progress monitoring of batch runs.
- Results can be browsed, analyzed, or re-used at any later stage.


The repository already includes:

- transcript ingestion
- chunking
- LLM-based extraction
- entity resolution baseline
- temporal graph representation
- graph update rules
- hybrid retrieval
- QA over retrieved evidence
- multiple LLM provider support
- Neo4j adapter compatibility
- offline verification scripts and tests

This means the project has already reached a working end-to-end prototype stage.

---

## 3. Core Outcome to Deliver

The final system should allow a user to:

1. load organization-related transcript data,
2. extract people, roles, projects, departments, policies, and facts,
3. maintain time-aware organizational state,
4. answer natural-language questions with evidence-backed replies,
5. support future upgrades without rewriting the pipeline.

---

## 4. Phase-by-Phase Plan

### Phase 1: Working Baseline (Current stage)

Goal: make the full pipeline function end-to-end.

Tasks:

- implement transcript extraction via LLM
- normalize raw data into meeting records
- chunk long transcript inputs
- resolve entities with a conservative baseline matcher
- apply temporal graph update rules
- store facts in a temporal graph
- retrieve relevant evidence
- answer questions using evidence only
- validate offline and against synthetic data

Completed status:

- extraction pipeline is implemented
- graph store is implemented
- retrieval and QA are implemented
- offline tests and demos exist

Key files:

- [core/pipeline.py](../core/pipeline.py)
- [core/extraction.py](../core/extraction.py)
- [core/entity_resolution.py](../core/entity_resolution.py)
- [core/update_policy.py](../core/update_policy.py)
- [core/retrieval.py](../core/retrieval.py)
- [core/qa.py](../core/qa.py)

---

### Phase 2: Contextual Entity Resolution

Goal: replace the naive resolver with a stronger contextual identity matcher.

Research problem:

- short names and aliases like “Sarah” vs. “Sarah Chen” may refer to the same person,
- naive TF-IDF matching fails when names are underspecified,
- the graph needs more context than just name similarity.

Planned improvements:

- combine multiple signals
  - lexical similarity
  - embedding similarity
  - role/department overlap
  - neighbor/entity co-occurrence
  - relation compatibility
  - organizational context
- add confidence scoring
- add a DEFER/FLAG mode for uncertain matches
- require LLM verification on ambiguous cases

Expected gain:

- fewer false negatives in alias resolution
- better merging of recurring persons and teams across meetings
- less incorrect graph duplication

Key files to improve:

- [core/entity_resolution.py](../core/entity_resolution.py)

---

### Phase 3: Smarter Temporal Update Policy

Goal: upgrade the fixed rule table to a richer conflict-aware update layer.

Current issue:

- all conflicting changes are handled by a naive “most recent wins” rule
- there is no deeper adjudication
- no MERGE / PRESERVE / DEFER paths are present

Planned improvements:

- classify updates as INSERT / UPDATE / SUPERSEDE / PRESERVE / DEFER / MERGE
- compare evidence recency, confidence, and source provenance
- maintain richer historical semantics
- distinguish true change from repeated reporting
- support explicit contradiction handling

Key files to improve:

- [core/update_policy.py](../core/update_policy.py)
- [core/graph_store.py](../core/graph_store.py)

---

### Phase 4: Graph Quality and Temporal Reasoning

Goal: make the graph more faithful to real-world organizational dynamics.

Planned improvements:

- stronger validity interval handling
- provenance-aware reasoning
- role history tracking
- status transitions over time
- support for team membership, reporting lines, responsibilities, programs, and policies

This is where the system becomes more than a passive fact store and evolves into a true organizational memory graph.

---

### Phase 5: Retrieval and Evaluation Quality

Goal: tighten retrieval quality and evaluate the system on realistic organizational questions.

Planned improvements:

- stronger entity-aware retrieval
- combine graph and semantic evidence more carefully
- rank evidence by temporal relevance
- evaluate retrieval recall and answer grounding
- test on real MeetingBank slices with repeated entities across meetings

Key files:

- [core/retrieval.py](../core/retrieval.py)
- [core/qa.py](../core/qa.py)
- [demo/run_real_meetingbank.py](../demo/run_real_meetingbank.py)

---

### Phase 6: Real Deployment / Productionization

Goal: transition from research prototype to production-ready use.

Planned work:

- switch to a stable data source pipeline
- validate real MeetingBank slices with reliable dates
- move from JSON graph to durable storage if needed
- add monitoring and observability
- implement logging and versioned graph snapshots
- add batch processing and re-ingestion workflows

Key files and modules:

- [core/graph_store_neo4j.py](../core/graph_store_neo4j.py)
- [data/meetingbank_loader.py](../data/meetingbank_loader.py)
- [scripts/test_neo4j_connection.py](../scripts/test_neo4j_connection.py)

---

## 5. Recommended Working Roadmap

### Sprint 1: Baseline validation

- run offline demo
- verify extraction and graph updates on synthetic meetings
- confirm the expected baseline gap in entity resolution
- document the failure mode for Chapter/Results write-up

### Sprint 2: Resolver improvement

- add contextual resolution features
- test on recurring names across meetings
- measure improvement against baseline

### Sprint 3: Temporal update improvement

- implement a richer update policy
- add rule evaluation for conflicts and preserved state
- validate with synthetic scenarios

### Sprint 4: Real-data evaluation

- run on a MeetingBank slice with recurring organizations/people
- inspect entity merging quality
- compare retrieval and QA quality

### Sprint 5: Thesis write-up and evaluation

- capture ablations and examples
- compare baseline versus improved versions
- produce final metrics and narrative

---

## 6. Expected Research Contributions

The likely value of the project is in the following areas:

1. temporal organization graph construction from meetings,
2. contextual entity resolution for ambiguous org references,
3. conflict-aware update logic for evolving organizational state,
4. hybrid retrieval over graph + semantic evidence,
5. evidence-grounded QA for organization memory.

---

## 7. Risks and Mitigation

### Risk 1: short names are ambiguous
Mitigation: use context-aware multi-signal matching and a DEFER mode.

### Risk 2: temporal updates may be wrong
Mitigation: keep provenance and confidence; support explicit conflict handling.

### Risk 3: retrieval quality is weak
Mitigation: combine graph retrieval with semantic retrieval and evaluate evidence precision.

### Risk 4: data quality in MeetingBank is inconsistent
Mitigation: normalize records, replace placeholder dates, and filter for relevant meeting slices.

### Risk 5: LLM outputs are inconsistent
Mitigation: use strict JSON prompts and validation logic, plus fallback provider support.

---

## 8. Immediate Next Actions

Recommended next steps:

1. Read and understand the pipeline from [core/pipeline.py](../core/pipeline.py)
2. Run the offline demo and capture results
3. Identify the entity resolution failure cases in the synthetic scenario
4. Define the Phase 2 contextual resolver design
5. Prepare evaluation criteria for baseline vs upgraded version
6. Write the results chapter around the observed behavior before and after improvement

---

## 9. Final Project Vision

The end state is a system that behaves like a temporal enterprise memory layer:

- it remembers who people are,
- remembers what roles and projects they hold,
- tracks how those facts change over time,
- can retrieve relevant organizational history,
- can answer questions using evidence rather than guesswork.

This is a strong foundation for both a research prototype and a practical internal knowledge assistant.
