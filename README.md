# Organizational Memory Pipeline

This project builds a temporal organizational memory graph from meeting transcripts. It extracts entities and facts with an LLM, resolves mentions into graph entities, applies temporal update rules, stores facts in a graph backend, retrieves relevant evidence, and answers questions from that evidence.

The current version is a working Phase 1 baseline. Extraction, storage, retrieval, provider connectors, and QA are wired end to end. Entity resolution and update policy are intentionally simple so they can become the Phase 2 research components.

## Project Layout

```text
org_memory/
  core/
    types.py               Shared dataclasses for entities, facts, and relations
    extraction.py           LLM JSON extraction from transcript chunks
    entity_resolution.py    Phase 1 resolver: exact/alias/TF-IDF matching
    update_policy.py        Phase 1 temporal rule table: INSERT/UPDATE/SUPERSEDE
    graph_store.py          NetworkX + JSON temporal graph backend
    graph_store_neo4j.py    Neo4j temporal graph backend
    graph_store_factory.py  Backend factory for JSON or Neo4j
    embeddings.py           Local/OpenAI embedding wrapper with TF-IDF fallback
    retrieval.py            Hybrid graph + vector evidence retrieval
    qa.py                   Evidence-grounded answer generation
    pipeline.py             Main ingest orchestration

  data/
    meetingbank_loader.py          Local/Hugging Face MeetingBank loaders
    meetingbank_slice_merged.json  Included local MeetingBank-style slice

  demo/
    run_demo_offline.py       Deterministic no-key verification
    run_demo.py               Local slice + real LLM + JSON graph
    run_real_meetingbank.py   Hugging Face MeetingBank + real LLM + Neo4j
    multi_llm_demo.py         Compare configured LLM providers

  scripts/
    test_neo4j_connection.py  Live Neo4j connectivity smoke test

  tests/
    Offline unit/adapter tests
```

`demo/synthetic_meetings.py` is not required. The offline demo keeps its small fixture inline.

## Python Environment

Use the project virtual environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Or run commands through the venv explicitly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\demo\run_demo_offline.py
```

Plain `python .\demo\run_real_meetingbank.py` only works after the venv is activated or if your global Python has all requirements installed. If it fails with `ModuleNotFoundError`, you are not using the environment that has this project’s dependencies.

## Configuration

Create or update `.env` in the project root. `.env` is ignored by git and should hold secrets.

Example:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j

EMBEDDING_BACKEND=local
```

Supported `LLM_PROVIDER` values are defined in `core/llm_connectors.py`:

```text
anthropic, openai, groq, gemini, deepseek, openrouter, zhipu
```

Each provider needs its matching key:

```text
ANTHROPIC_API_KEY
OPENAI_API_KEY
GROQ_API_KEY
GEMINI_API_KEY
DEEPSEEK_API_KEY
OPENROUTER_API_KEY
ZHIPU_API_KEY
```

ChatGPT Plus is not an API key. For `LLM_PROVIDER=openai`, use a real platform OpenAI API key with API billing enabled.

## What To Run

### 1. Offline Verification

Run this first. It requires no LLM key and no Neo4j server.

```powershell
.\.venv\Scripts\python.exe .\demo\run_demo_offline.py
```

This verifies entity insertion, temporal INSERT/SUPERSEDE behavior, graph storage, hybrid retrieval, and mocked QA output.

It also prints an expected Phase 1 gap: the naive resolver keeps `Sarah` and `Sarah Chen` as separate entities. That is intentional and useful as a baseline for the future contextual resolver.

### 2. Local Slice With Real LLM And JSON Graph

This uses `data/meetingbank_slice_merged.json`, calls the configured LLM, writes a JSON graph, and does not require Neo4j.

```powershell
.\.venv\Scripts\python.exe .\demo\run_demo.py
```

Requirements:

- `LLM_PROVIDER` set, or default provider available
- matching provider API key in `.env`

Output:

- `demo/demo_graph.json`
- `demo/extraction_log.jsonl`
- terminal QA output

### 3. Real MeetingBank From Hugging Face With Neo4j

This is the command you asked about:

```powershell
python .\demo\run_real_meetingbank.py
```

It will work only if `python` is the activated venv Python or a Python with all dependencies installed. The safer command is:

```powershell
.\.venv\Scripts\python.exe .\demo\run_real_meetingbank.py
```

Requirements:

- project dependencies installed
- one configured LLM provider key
- Neo4j Desktop or server running
- correct `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE`
- internet access for Hugging Face dataset loading, unless already cached

Before running the real ingest, test Neo4j:

```powershell
.\.venv\Scripts\python.exe .\scripts\test_neo4j_connection.py
```

Then run:

```powershell
.\.venv\Scripts\python.exe .\demo\run_real_meetingbank.py
```

If Neo4j is not running, the script fails early with a clear message telling you to start Neo4j or check the connection settings.

## Testing

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Current expected result:

```text
7 passed
```

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall core demo data scripts tests
```

Standalone checks:

```powershell
.\.venv\Scripts\python.exe .\tests\test_connector_pool_offline.py
.\.venv\Scripts\python.exe .\tests\test_connector_logging_offline.py
.\.venv\Scripts\python.exe .\tests\test_neo4j_adapter_offline.py
```

## Pipeline Flow

The ingest flow is:

1. Load a transcript record.
2. Chunk long transcripts in `core/pipeline.py`.
3. Extract structured JSON entities and facts in `core/extraction.py`.
4. Resolve mentions in `core/entity_resolution.py`.
5. Apply temporal graph updates in `core/update_policy.py`.
6. Persist to JSON or Neo4j graph store.
7. Retrieve evidence with `core/retrieval.py`.
8. Answer with `core/qa.py`.

Fact shape:

```text
subject --relation--> object
```

Relation metadata:

```text
valid_from, valid_to, status, provenance, confidence
```

## Storage Backends

### JSON Backend

`TemporalGraphStore` in `core/graph_store.py` stores the graph in memory and saves to JSON.

Use it for offline verification, small local experiments, and debugging pipeline behavior.

### Neo4j Backend

`Neo4jGraphStore` in `core/graph_store_neo4j.py` writes entities and temporal relations to Neo4j.

Use it for real graph inspection, Cypher queries, larger ingestion runs, and visualization in Neo4j Browser or Bloom.

The Neo4j backend uses:

- `(:Entity)` nodes
- generic `[:RELATION]` edges
- semantic relation names stored as the `relation` property

That design avoids generating dynamic relationship types from LLM output and keeps querying simpler.

## LLM Providers

All LLM calls go through `core/llm_connectors.py`.

Single provider example:

```python
from core.llm_connectors import build_connector

connector = build_connector("openai")
```

Fallback/ensemble support:

```python
from core.llm_connectors import build_connector, ConnectorPool

pool = ConnectorPool([
    build_connector("groq"),
    build_connector("gemini"),
    build_connector("openrouter"),
])
```

Every connector logs the provider, model, and usage information when the provider returns token usage.

## Embeddings

`core/embeddings.py` supports:

- local sentence-transformers: `EMBEDDING_BACKEND=local`
- OpenAI embeddings: `EMBEDDING_BACKEND=openai`
- TF-IDF fallback if embeddings cannot initialize

Default:

```text
EMBEDDING_BACKEND=local
```

Local embeddings may download model weights on first run. If that fails, retrieval falls back to TF-IDF and prints a warning.

## Phase 1 Limitations

These limitations are intentional:

- Entity resolution is conservative and can miss short-name matches.
- Update policy is a fixed rule table.
- Conflict handling is `most recent wins`.
- MeetingBank records often lack real dates, so placeholder dates may be used.
- The included MeetingBank slice may not contain enough recurring entities to fully exercise cross-meeting resolution.

These are the intended Phase 2 improvement areas:

- contextual entity resolution
- multi-signal identity scoring
- conflict-aware update policy
- DEFER/PRESERVE/MERGE decisions
- stronger temporal reasoning
- improved evidence ranking

## Troubleshooting

`ModuleNotFoundError: No module named 'tqdm'`

You are not using the venv. Run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`Set NEO4J_PASSWORD before running...`

Add `NEO4J_PASSWORD` to `.env` or set it in PowerShell:

```powershell
$env:NEO4J_PASSWORD="your_password"
```

`Could not connect to Neo4j`

Start Neo4j Desktop or server, then verify:

```powershell
.\.venv\Scripts\python.exe .\scripts\test_neo4j_connection.py
```

`No API key provided`

Set `LLM_PROVIDER` and the matching API key in `.env`.

`Unable to retrieve routing information`

Neo4j is not reachable at the configured URI, or the URI scheme is wrong. For a local single database, prefer:

```text
NEO4J_URI=bolt://localhost:7687
```

## Recommended Development Loop

```powershell
.\.venv\Scripts\python.exe .\demo\run_demo_offline.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\scripts\test_neo4j_connection.py
.\.venv\Scripts\python.exe .\demo\run_real_meetingbank.py
```

That order separates local code issues from live API and database issues.
