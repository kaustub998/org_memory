# Neo4j Database Setup and Usage

This document describes how this project uses Neo4j as the persistent graph backend for the MeetingBank ingestion path.

---

## 1. When Neo4j Is Required

Neo4j is required for:

```powershell
.\.venv\Scripts\python.exe .\demo\run_real_meetingbank.py
```

Neo4j is not required for:

```powershell
.\.venv\Scripts\python.exe .\demo\run_demo_offline.py
.\.venv\Scripts\python.exe .\demo\run_demo.py
.\.venv\Scripts\python.exe -m pytest -q
```

If you run the real MeetingBank script before Neo4j is started, the script will fail during startup because it creates constraints/indexes immediately.

## 2. Database Schema Design

### Node Label: Entity

Each resolved entity is stored as a node with label `Entity`.

#### Properties:
- `entity_id` (string): Unique identifier for the entity.
- `canonical_name` (string): The entity's main name.
- `entity_type` (string): The type/category of entity (e.g., PERSON, POLICY, ORGANIZATION).
- `aliases` (list of strings): Alternative names or variants.
- `first_seen` (string): Timestamp/Date first seen.
- `last_seen` (string): Timestamp/Date last seen.

### Relationship Types

Edges represent relationships between entities. The project uses one generic Neo4j relationship type:

```cypher
[:RELATION]
```

The semantic relation name is stored as a property, for example `reports_to`, `role_is`, `supports`, or `status_is`. This avoids generating Neo4j relationship types from arbitrary LLM output.

#### Relationship Properties:
- `relation_id` (string): Unique relation identifier.
- `subject_id` (string): Source entity id.
- `relation` (string): Semantic relation name.
- `object_id` (string): Target entity id.
- `valid_from` (string): Date/time the relation became true.
- `valid_to` (string/null): Date/time the relation stopped being current.
- `status` (string): `active`, `superseded`, or `preserved`.
- `provenance` (string): Source meeting/snippet where this fact was extracted.
- `confidence` (float): Confidence score.

## 3. Neo4j Setup

- Download and install Neo4j Desktop or run a Neo4j server.
- Create and start a Neo4j 5.x DBMS.
- Obtain the Bolt URI, username, password, and database name.
- For a local Neo4j Desktop database, prefer `bolt://localhost:7687`.

Put this in `.env`:

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j
```

PowerShell one-off alternative:

```powershell
$env:NEO4J_URI="bolt://localhost:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="your_neo4j_password"
$env:NEO4J_DATABASE="neo4j"
```

## 4. Python Neo4j Driver Setup

Install project requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then test the live database connection:

```powershell
.\.venv\Scripts\python.exe .\scripts\test_neo4j_connection.py
```

This writes temporary test nodes/relations, verifies active/superseded temporal behavior, and removes the test data.

## 5. Python Code Example for Connection & Insertion

```python
from core.graph_store_neo4j import Neo4jGraphStore
import os
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password")
store = Neo4jGraphStore(uri, user, password, database=os.getenv("NEO4J_DATABASE", "neo4j"))

# Example usage:
# Entities:
store.upsert_entity('ent1', 'John Doe', 'PERSON', alias='J. Doe', timestamp='2024-06-12')

# Relations:
store.add_relation('ent1', 'reports_to', 'ent2', valid_from='2024-06-12', provenance='Meeting transcript ...')

# Usage stats, logs, QA:
store.insert_usage_stat({'meeting_id': 'meeting01', 'input_tokens': 123, ...})
store.insert_error_log({'meeting_id': 'meeting01', 'chunk_idx': 0, 'error': 'Some error', 'raw_output': '...'})
store.insert_qa_log({'meeting_id': 'meeting01', 'question': 'What ordinances?', 'answer': 'Council Bill 161...', 'evidence_retrieved': ['...']})
```


## 6. Running Real MeetingBank Ingestion

Configure `.env` with both an LLM provider and Neo4j:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j
```

Run:

```powershell
.\.venv\Scripts\python.exe .\demo\run_real_meetingbank.py
```

What this does:

- loads a small Hugging Face MeetingBank split,
- chunks long transcripts,
- extracts entities/facts with the configured LLM,
- resolves entities,
- writes temporal entities and relations into Neo4j,
- writes usage stats, parse errors, and QA logs.

Important: do not call `create_entity` or `create_relation`; those older names are not part of the current adapter. The current graph-store interface is:

```text
upsert_entity
add_relation
supersede_relation
find_active_relation
find_active_relations_by_subject_relation
all_entities
all_relations
relations_for_entity
```

## 7. Useful Cypher Queries

All entities:

```cypher
MATCH (e:Entity)
RETURN e.entity_id, e.canonical_name, e.entity_type, e.first_seen, e.last_seen
ORDER BY e.canonical_name
```

Active relations:

```cypher
MATCH (s:Entity)-[r:RELATION {status: 'active'}]->(o:Entity)
RETURN s.canonical_name AS subject,
       r.relation AS relation,
       o.canonical_name AS object,
       r.valid_from AS valid_from,
       r.provenance AS provenance
ORDER BY subject, relation
```

Superseded history:

```cypher
MATCH (s:Entity)-[r:RELATION {status: 'superseded'}]->(o:Entity)
RETURN s.canonical_name AS subject,
       r.relation AS relation,
       o.canonical_name AS old_object,
       r.valid_from AS valid_from,
       r.valid_to AS valid_to
ORDER BY valid_to DESC
```

Usage stats:

```cypher
MATCH (u:UsageStat)
RETURN u.meeting_id, u.input_tokens, u.output_tokens, u.total_tokens, u.calls, u.models_used
ORDER BY u.meeting_id
```

Errors:

```cypher
MATCH (e:ErrorLog)
RETURN e.meeting_id, e.chunk_idx, e.error, e.raw_output
ORDER BY e.meeting_id, e.chunk_idx
```

QA logs:

```cypher
MATCH (q:QALog)
RETURN q.question, q.answer, q.evidence_retrieved
```

## 8. Troubleshooting

`Unable to retrieve routing information` or `ConnectionRefusedError`:

- Start Neo4j Desktop/server.
- Confirm the DBMS is running.
- Prefer `NEO4J_URI=bolt://localhost:7687` for local Neo4j Desktop.
- Check that port `7687` is not blocked.

Authentication errors:

- Check `NEO4J_USER`.
- Check `NEO4J_PASSWORD`.
- Reset the password in Neo4j Desktop if needed.

`ModuleNotFoundError`:

- Activate the venv or run with `.\.venv\Scripts\python.exe`.
- Install requirements with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.

