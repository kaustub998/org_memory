"""
Structural test of Neo4jGraphStore using an in-memory FAKE Neo4j driver
(no real database, no network) -- catches obvious bugs in the Cypher/
data-mapping logic (wrong property names, wrong record keys, etc.)
before you ever point this at a real Neo4j Desktop instance.

This does NOT prove the real Cypher is syntactically valid against a
real Neo4j server -- only that Neo4jGraphStore's Python-side logic
(what it asks for, what it does with the response) is internally
consistent. Run scripts/test_neo4j_connection.py against your real
Neo4j Desktop instance for that final check.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


class FakeGraphDB:
    """A tiny in-memory stand-in for a Neo4j database, just enough to
    exercise Neo4jGraphStore's logic without a real Bolt connection."""

    def __init__(self):
        self.nodes = {}   # entity_id -> dict
        self.edges = {}   # relation_id -> dict

    def run_create_constraint_or_index(self):
        pass

    def upsert_entity(self, entity_id, name, etype, ts):
        if entity_id in self.nodes:
            self.nodes[entity_id]["last_seen"] = ts or self.nodes[entity_id]["last_seen"]
        else:
            self.nodes[entity_id] = {
                "entity_id": entity_id, "canonical_name": name, "entity_type": etype,
                "aliases": [], "first_seen": ts, "last_seen": ts,
            }

    def set_aliases(self, entity_id, aliases, ts):
        self.nodes[entity_id]["aliases"] = aliases
        if ts:
            self.nodes[entity_id]["last_seen"] = ts


def test_neo4j_adapter_logic():
    """Exercises upsert/add/find/supersede against the fake DB by
    monkeypatching the driver session's .run() to operate on FakeGraphDB
    instead of speaking Bolt."""
    from core import graph_store_neo4j as mod

    fake_db = FakeGraphDB()

    class FakeResult:
        def __init__(self, records):
            self._records = records
        def single(self):
            return self._records[0] if self._records else None
        def __iter__(self):
            return iter(self._records)

    class FakeRecord(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def run(self, query, **params):
            q = " ".join(query.split())  # normalize whitespace for matching

            if q.startswith("CREATE CONSTRAINT") or q.startswith("CREATE INDEX"):
                return FakeResult([])

            if q.startswith("MATCH (e:Entity {entity_id: $id}) RETURN e"):
                node = fake_db.nodes.get(params["id"])
                return FakeResult([FakeRecord(e=node)] if node else [])

            if q.startswith("MATCH (e:Entity) RETURN e"):
                return FakeResult([FakeRecord(e=n) for n in fake_db.nodes.values()])

            if q.startswith("MATCH (e:Entity {entity_id: $id}) SET e.aliases"):
                fake_db.set_aliases(params["id"], params["aliases"], params["ts"])
                return FakeResult([])

            if q.startswith("CREATE (e:Entity"):
                fake_db.upsert_entity(params["id"], params["name"], params["etype"], params["ts"])
                return FakeResult([])

            if "RETURN r.relation_id AS rid LIMIT 1" in q:
                for e in fake_db.edges.values():
                    if (e["subject_id"] == params["sid"] and e["relation"] == params["rel"]
                            and e["object_id"] == params["oid"] and e["status"] == "active"):
                        return FakeResult([FakeRecord(rid=e["relation_id"])])
                return FakeResult([])

            if q.startswith("MATCH (:Entity {entity_id: $sid})-[r:RELATION {relation: $rel, status: 'active'}]->(:Entity) RETURN r"):
                matches = [e for e in fake_db.edges.values()
                           if e["subject_id"] == params["sid"] and e["relation"] == params["rel"] and e["status"] == "active"]
                return FakeResult([FakeRecord(r=e) for e in matches])

            if q.startswith("MATCH (s:Entity {entity_id: $sid}), (o:Entity {entity_id: $oid}) CREATE"):
                fake_db.edges[params["rid"]] = {
                    "relation_id": params["rid"], "subject_id": params["sid"], "relation": params["rel"],
                    "object_id": params["oid"], "valid_from": params["vf"], "valid_to": None,
                    "status": "active", "provenance": params["prov"], "confidence": params["conf"],
                }
                return FakeResult([])

            if q.startswith("MATCH ()-[r:RELATION {relation_id: $rid}]->() SET"):
                if params["rid"] in fake_db.edges:
                    fake_db.edges[params["rid"]]["status"] = "superseded"
                    fake_db.edges[params["rid"]]["valid_to"] = params["vt"]
                    return FakeResult([FakeRecord(rid=params["rid"])])
                return FakeResult([])

            if q.startswith("MATCH ()-[r:RELATION]->() RETURN r"):
                return FakeResult([FakeRecord(r=e) for e in fake_db.edges.values()])

            if q.startswith("MATCH (e:Entity {entity_id: $id})-[r:RELATION]-() RETURN DISTINCT r"):
                matches = [e for e in fake_db.edges.values()
                           if e["subject_id"] == params["id"] or e["object_id"] == params["id"]]
                return FakeResult([FakeRecord(r=e) for e in matches])

            raise NotImplementedError(f"FakeSession got an unhandled query:\n{query}\nparams={params}")

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()
        def close(self):
            pass

    with patch.object(mod.GraphDatabase, "driver", return_value=FakeDriver()):
        store = mod.Neo4jGraphStore(uri="bolt://fake", user="fake", password="fake")

        # Same scenario as the offline sanity test: appoint, restate, promote.
        store.upsert_entity("e_sarah", "Sarah Chen", "PERSON", timestamp="2024-01-10")
        store.upsert_entity("e_pm", "Project Manager", "OTHER", timestamp="2024-01-10")
        store.upsert_entity("e_spd", "Senior Program Director", "OTHER", timestamp="2024-07-22")

        rel_id = store.add_relation("e_sarah", "role_is", "e_pm", "2024-01-10", provenance="meeting1")
        assert store.find_active_relation("e_sarah", "role_is", "e_pm") == rel_id, "FAIL: active relation not found"

        conflicting = store.find_active_relations_by_subject_relation("e_sarah", "role_is")
        assert len(conflicting) == 1, "FAIL: expected exactly one active role_is relation"

        for rel in conflicting:
            store.supersede_relation(rel.relation_id, valid_to="2024-07-22")
        new_rel_id = store.add_relation("e_sarah", "role_is", "e_spd", "2024-07-22", provenance="meeting3")

        all_rels = store.all_relations()
        active = [r for r in all_rels if r.status == "active"]
        superseded = [r for r in all_rels if r.status == "superseded"]
        assert len(active) == 1 and active[0].relation_id == new_rel_id, "FAIL: expected one active relation (the new one)"
        assert len(superseded) == 1 and superseded[0].relation_id == rel_id, "FAIL: expected old relation superseded"

        ent = store.get_entity("e_sarah")
        assert ent.canonical_name == "Sarah Chen", "FAIL: entity lookup broken"

        print("[PASS] upsert_entity, add_relation, find_active_relation")
        print("[PASS] find_active_relations_by_subject_relation")
        print("[PASS] supersede_relation correctly flips status + sets valid_to")
        print("[PASS] all_relations reflects exactly one active + one superseded edge")
        print("\nAll Neo4jGraphStore logic checks passed against the fake in-memory driver.")
        print("This does NOT test real Cypher syntax against a live server --")
        print("run scripts/test_neo4j_connection.py against Neo4j Desktop next.")


if __name__ == "__main__":
    test_neo4j_adapter_logic()
