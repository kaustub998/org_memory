# Organizational Memory Pipeline — Phase 1 (Working Baseline)

This is the "make it work end-to-end first" version described in your proposal:
a full Extraction → Entity Resolution → Update Policy → Temporal Graph Store →
Hybrid Retrieval → QA pipeline, where **Entity Resolution** and the **Graph
Update Policy** are deliberately naive placeholders. Everything else
(extraction, the graph schema, hybrid retrieval, QA) is built to full spec
now, since those aren't your two research contributions.

## Structure

```
org_memory/
  core/
    types.py             shared dataclasses (Entity, Fact, Relation)
    extraction.py         LLM-based extraction (full spec)
    entity_resolution.py  BASIC BLOCK — single-signal matching, precision-first
    graph_store.py         temporal graph (NetworkX + JSON; Neo4j-shaped schema)
    update_policy.py      BASIC BLOCK — fixed rule table (INSERT/UPDATE/SUPERSEDE only)
    retrieval.py           hybrid graph + TF-IDF vector retrieval (full spec)
    qa.py                  LLM answer generation from retrieved evidence (full spec)
    pipeline.py            orchestrator: wires all layers together per meeting
  data/
    meetingbank_loader.py  loader for your MeetingBank JSON/JSONL slice
  demo/
    synthetic_meetings.py  3 synthetic council meetings exercising INSERT/UPDATE/SUPERSEDE
    run_demo.py            full pipeline run (needs ANTHROPIC_API_KEY)
    run_demo_offline.py    deterministic verification (extraction mocked, no API key needed)
```

## Running it

### Output Logging and Progress Bar

Recent updates allow you to log all extracted entities, relations, pipeline facts, and summary information for each meeting in a run to a dedicated output file (e.g., `extraction_log.jsonl`).

A progress bar is also displayed during the ingestion of many meetings, letting you monitor processing status (using either `tqdm` or a built-in tracker).

**How to enable and use these features:**
- By default: running any demo or ingestion script will log each meeting's extracted output to `extraction_log.jsonl` in the current directory.
- Each line is a JSON object representing one meeting's extraction (meeting metadata, entities, relations, pipeline operations, etc.).
- You can inspect this file in any text editor or process results programmatically.
- The progress bar appears in your terminal and tracks per-meeting progress during processing.

**To view structured outputs later:**
- Open `extraction_log.jsonl` with a text editor or tools like jq, or load with pandas for analysis.
- Each log line contains all outputs for one meeting, useful for debugging, reviewing, or building a result dashboard.

### 1. Offline verification (no API key needed) — run this first
```bash
pip install -r requirements.txt
python demo/run_demo_offline.py
```
This mocks the LLM extraction call and proves out everything downstream:
entity resolution, the update policy's INSERT/UPDATE/SUPERSEDE logic, the
temporal graph store, and hybrid retrieval. It will also print an "EXPECTED
GAP" diagnostic showing the naive resolver failing to merge "Sarah" with
"Sarah Chen" — keep that as a baseline data point for your results chapter;
it's exactly the failure mode Phase 2's contextual resolver should fix.

### 2. Full pipeline with a real model
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python demo/run_demo.py
```
Same three synthetic meetings, but extraction and answer generation go
through the real Claude API instead of mocks.

### 3. Real MeetingBank data (already included as an example)

`data/meetingbank_slice_merged.json` is a real 11-meeting slice, built from
a 20-segment Hugging Face download of `huuuyeah/meetingbank` via
`data/merge_segments.py`. **Important:** MeetingBank's HF release returns
*segment*-level records, not whole meetings -- several segments often share
one parent-meeting summary because they're different transcript slices of
the same agenda item. Run the merger first if you pull a fresh slice:

```bash
python data/merge_segments.py your_raw_slice.json your_merged_slice.json
```

This groups segments by identical summary text, concatenates their
transcripts in order, and assigns **one placeholder date per merged
meeting** (not per segment) -- otherwise segments of the same session get
spread across fake different days. Real MeetingBank records don't carry a
`date` field at all, so these are still placeholders; replace them with real
dates if you can find them (e.g. from the meeting video/agenda metadata),
since validity intervals are meaningless without real chronology.

Then ingest it:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python demo/run_real_meetingbank.py
```

Note on this specific 20-segment sample: it happens to contain 11 *distinct*
agenda items with essentially no entity recurrence across items (different
bills, different people). That's fine for testing extraction quality and
single-meeting INSERT behavior, but it won't exercise cross-meeting
entity resolution or SUPERSEDE the way the synthetic demo does -- for that,
you need a slice where the SAME council members/projects recur across
multiple sessions (e.g. pull a larger slice filtered to one city, sorted
by date, so the same people/departments show up repeatedly).

### 4. Plugging in a different MeetingBank slice
```python
from data.meetingbank_loader import load_meetingbank
from core.graph_store import TemporalGraphStore
from core.pipeline import ingest_meeting

store = TemporalGraphStore("my_graph.json")
meetings = load_meetingbank("path/to/your_meetingbank_slice.json")
for m in meetings:
    ingest_meeting(store, m["transcript"], m["meeting_id"], m["date"])
```
MeetingBank's HF/Zenodo releases use `id` / `summary` / `transcript` fields.
If your slice has a `date` field, the loader picks it up automatically —
if not, it fabricates a placeholder sequential date so the temporal graph
still has something to sort on. **Replace the placeholder with real dates
before running any real evaluation** — the whole point of the temporal
graph is validity intervals, and those are meaningless without real dates.
Long transcripts (MeetingBank averages ~28k tokens) are automatically
chunked by `pipeline.py` before extraction.

## What's naive on purpose (Phase 1) vs. what's full-spec

| Layer | Phase 1 status | Notes |
|---|---|---|
| Extraction | Full spec | Not a research component |
| Entity Resolution | **Naive** | Exact/alias match + single TF-IDF signal, fixed threshold, no LLM verification, no DEFER |
| Update Policy | **Naive** | Fixed rule table: INSERT / UPDATE / SUPERSEDE only, "most recent wins", no MERGE/PRESERVE/DEFER, no conflict adjudication |
| Graph Store | Full spec (schema) | NetworkX+JSON now; swap for Neo4j later without touching callers |
| Hybrid Retrieval | Full spec | TF-IDF stands in for a real embedding model (this sandbox can't download embedding weights — swap `retrieve_vector()`'s TfidfVectorizer for a sentence-transformer or API embedding call in your own environment) |
| QA | Full spec | Straightforward evidence-grounded generation |

## Neo4j (replacing the JSON graph store)

`core/graph_store_neo4j.py` is a drop-in replacement for
`core/graph_store.py` — same public methods (`upsert_entity`,
`add_relation`, `find_active_relation`, etc.), so `pipeline.py` and
`retrieval.py` work with either backend unchanged. Verified two ways
before you touch a real database:

1. `tests/test_neo4j_adapter_offline.py` — runs the adapter's Cypher/
   data-mapping logic against a fake in-memory driver (no network, no
   real Neo4j). Confirms the Python-side logic is internally consistent.
2. `scripts/test_neo4j_connection.py` — run this against your **real**
   Neo4j Desktop instance to confirm actual connectivity and that the
   Cypher is valid against a live server. This is the one that actually
   matters — the offline test can't catch real syntax errors.

Setup:
```bash
# 1. In Neo4j Desktop: create a local DBMS (Neo4j 5.x), start it,
#    note the Bolt URI (usually bolt://localhost:7687) and password.
pip install neo4j

export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password_here

python tests/test_neo4j_adapter_offline.py   # sanity check first, no DB needed
python scripts/test_neo4j_connection.py       # then the real connectivity test
```

Once both pass, switch it into the pipeline:
```python
from core.graph_store_neo4j import Neo4jGraphStore
store = Neo4jGraphStore(
    uri="bolt://localhost:7687", user="neo4j", password="your_password_here"
)
# everything else (ingest_meeting, retrieve_hybrid, ...) is unchanged
```

Two design notes worth knowing:
- Relationships all use one generic Neo4j type `:RELATION`, with the
  *semantic* relation name (e.g. `"leads"`, `"reports_to"`) stored as a
  property, not as the Neo4j relationship type itself. This avoids
  building relationship types from dynamic/untrusted strings and makes
  filtering by relation a plain property match.
- `save()` on `Neo4jGraphStore` is a no-op — every write already commits
  immediately, unlike the JSON store where `save()` flushes to disk.

## Real embeddings (replacing TF-IDF in retrieval)

`core/embeddings.py` wraps `sentence-transformers` (`all-MiniLM-L6-v2` by
default) and `retrieval.py`'s `retrieve_vector()` now uses it automatically
**when available**, falling back to TF-IDF with a printed warning if the
model can't load (no internet on first run to fetch weights, package not
installed, etc.) — this sandbox can't download model weights, so it always
falls back here; on your machine, once you `pip install sentence-transformers`
with internet access, it should switch over automatically. Check
`core.retrieval.EMBEDDING_BACKEND` (or just watch the startup message) to
confirm which one is actually active before trusting any retrieval-quality
comparisons — TF-IDF silently taking over would otherwise look identical
from the outside.

**Note:** `entity_resolution.py`'s TF-IDF signal was deliberately left
alone — upgrading that one to embeddings is part of your Phase 2
contextual resolver (it becomes one of the multiple signals: embedding +
neighbor + relation + org-context), not infrastructure. Only the
retrieval-layer TF-IDF was infra, and that one's now upgraded.

## Multiple LLM providers / free API keys (core/llm_connectors.py)

`extraction.py` and `qa.py` now accept an injected `connector` (defaults
to Claude if you don't pass one), so you can run the pipeline through
any provider, mix providers, or fall back from one to another when a
free tier's rate limit gets hit. Two connector classes cover almost
everything:

- `AnthropicConnector` — native Claude API.
- `OpenAICompatibleConnector` — everything else. Groq, real OpenAI,
  Google Gemini, DeepSeek, OpenRouter, and Zhipu (GLM) all expose the
  *same* OpenAI chat-completions shape, so one class handles all of them
  by swapping `base_url` + `model` + API key. See `PROVIDER_PRESETS` in
  `core/llm_connectors.py` for the exact URLs/models/env-var names —
  edit that dict if a free tier's terms change.

**Important correction if you're planning to use a ChatGPT Plus key:**
a Plus subscription (chat.openai.com) does **not** include API credits.
API access is billed separately, pay-as-you-go, through a key generated
at platform.openai.com — your Plus login won't work as `OPENAI_API_KEY`
here unless that account also has API billing set up separately.

Free options that work as-is (no card required for most):
| Provider | Env var | Get a key |
|---|---|---|
| Groq | `GROQ_API_KEY` | console.groq.com/keys |
| Google Gemini | `GEMINI_API_KEY` | aistudio.google.com/apikey |
| Zhipu (GLM) | `ZHIPU_API_KEY` | open.bigmodel.cn |
| DeepSeek | `DEEPSEEK_API_KEY` | platform.deepseek.com (free credits for new signups) |
| OpenRouter | `OPENROUTER_API_KEY` | openrouter.ai/keys (filter models by `:free`) |

Usage:
```python
from core.llm_connectors import build_connector, ConnectorPool
from core.pipeline import ingest_meeting

# single provider, explicit
groq = build_connector("groq")
ingest_meeting(store, transcript, meeting_id, date, connector=groq)

# fallback chain: try Claude, then Groq, then Gemini if earlier ones fail/rate-limit
pool = ConnectorPool([build_connector("anthropic"), build_connector("groq"), build_connector("gemini")])
response, used = pool.complete_with_fallback(system_prompt, user_prompt)

# run the SAME prompt on every provider you have a key for, compare outputs
results = pool.complete_all(system_prompt, user_prompt)
```

Two test scripts:
- `tests/test_connector_pool_offline.py` — fake connectors, no keys/network needed, checks fallback and ensemble logic.
- `demo/multi_llm_demo.py` — real providers; builds a connector for every API key you actually have set as an env var and runs one extraction prompt through all of them so you can compare.

## The three connectors you asked for

```python
from core.llm_connectors import build_connector

claude     = build_connector("anthropic")   # ANTHROPIC_API_KEY
chatgpt    = build_connector("openai")      # OPENAI_API_KEY -- real platform.openai.com key, NOT your ChatGPT Plus login
openrouter = build_connector("openrouter")  # OPENROUTER_API_KEY -- pick any model, incl. free ones tagged ":free"
```

Every connector call (all three, and any other provider in `PROVIDER_PRESETS`)
prints which model it's calling and the token usage it got back, e.g.:
```
[llm_connector] calling openrouter | model=meta-llama/llama-3.3-70b-instruct:free
[llm_connector] openrouter usage: prompt=142 completion=58 total=200
```
OpenRouter specifically can auto-route your request to a *different* model
than the one you asked for (fallback/load-balancing on their end) — the
connector checks the response's actual `model` field against what you
requested and prints an extra `NOTE` line if they don't match, so you're
never silently billed for or evaluating a different model than you think.
Verified with mocked SDK responses in `tests/test_connector_logging_offline.py`.

## Neo4j "connector" (storage backend factory)

Same factory pattern, for storage instead of LLMs:
```python
from core.graph_store_factory import build_graph_store

store = build_graph_store("json", path="my_graph.json")       # NetworkX + JSON
store = build_graph_store("neo4j", uri="bolt://localhost:7687",
                           user="neo4j", password="...")       # real Neo4j Desktop
```
Prints which backend it built (`[graph_store_factory] backend=neo4j uri=... database=...`),
and `pipeline.py`/`retrieval.py` don't care which one you pass in — same
interface parity already verified in `tests/test_neo4j_adapter_offline.py`.

## Is the embedding model the same as the ChatGPT connector?

**No** — and it's worth being precise about this. `gpt-4o-mini` (what the
`"openai"` connector uses for chat) and OpenAI's embedding models are
different models, served by a different endpoint, billed separately —
"ChatGPT" and "embeddings" are not the same product even within one
provider. What was already in `core/embeddings.py` before this change was
a **local** model (`sentence-transformers`, `all-MiniLM-L6-v2`) that has
nothing to do with any API key at all — it runs on your machine for free.

You now have both as explicit options, switched via an environment variable:
```bash
export EMBEDDING_BACKEND=local    # sentence-transformers, free, offline (default)
export EMBEDDING_BACKEND=openai   # OpenAI's text-embedding-3-small, reuses OPENAI_API_KEY, billed per call
```
If you set `EMBEDDING_BACKEND=openai` but don't have `OPENAI_API_KEY` set
(or the package/model can't load), it prints why and falls back to local
automatically — same fail-soft pattern as everything else here. Check the
startup message, or `core.embeddings.ACTIVE_BACKEND`, to confirm which one
is actually active.

## Phase 2 — where the research work plugs in

- **`entity_resolution.py`**: replace `BasicEntityResolver` with a multi-signal
  scorer (name/alias, embedding, neighbor overlap, relation context,
  organizational context), add confidence thresholds with LLM verification
  for ambiguous cases, and add DEFER/FLAG instead of forced binary merge/new.
- **`update_policy.py`**: replace the fixed rule table with the full
  INSERT/UPDATE/MERGE/SUPERSEDE/PRESERVE/DEFER decision logic, combining
  rules with LLM reasoning for nuanced conflicting evidence.
- Both are swappable in isolation — `pipeline.py` only calls
  `resolver.resolve(...)` and `apply_fact(...)`, so neither change touches
  extraction, storage, retrieval, or QA. This is what makes your ablation
  study (naive vs. full resolver, naive vs. full update policy) a clean,
  apples-to-apples comparison later.
