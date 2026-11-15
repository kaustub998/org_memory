"""
Run this AGAINST YOUR REAL Neo4j Desktop instance to confirm connectivity
and that the real Cypher in graph_store_neo4j.py actually works (the
offline test in tests/ only checks the Python-side logic against a fake
driver -- this is the real thing).

    1. Open Neo4j Desktop, start your local DBMS.
    2. Note its Bolt URI (Neo4j Desktop shows this in the DBMS details --
       usually bolt://localhost:7687) and the password you set.
    3. Edit NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD below (or set them as
       environment variables).
    4. pip install neo4j
    5. python scripts/test_neo4j_connection.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.graph_store_neo4j import Neo4jGraphStore

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeme")
TEST_DB = os.environ.get("NEO4J_DATABASE", "neo4j")


def main():
    print(f"Connecting to {NEO4J_URI} as {NEO4J_USER} ...")
    store = Neo4jGraphStore(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, database=TEST_DB)
    print("Connected. Constraints/indexes ensured.\n")

    print("Running the same appoint -> restate -> promote scenario as the JSON demo...")
    store.upsert_entity("test_sarah", "Sarah Chen (CONNECTIVITY TEST)", "PERSON", timestamp="2024-01-10")
    store.upsert_entity("test_pm", "Project Manager (TEST)", "OTHER", timestamp="2024-01-10")
    store.upsert_entity("test_spd", "Senior Program Director (TEST)", "OTHER", timestamp="2024-07-22")

    rel_id = store.add_relation("test_sarah", "role_is", "test_pm", "2024-01-10", provenance="connectivity_test")
    found = store.find_active_relation("test_sarah", "role_is", "test_pm")
    assert found == rel_id, "Round-trip failed: wrote a relation, couldn't find it back"
    print(f"  [OK] wrote and re-read an active relation ({rel_id})")

    conflicting = store.find_active_relations_by_subject_relation("test_sarah", "role_is")
    assert len(conflicting) == 1
    store.supersede_relation(conflicting[0].relation_id, valid_to="2024-07-22")
    new_rel_id = store.add_relation("test_sarah", "role_is", "test_spd", "2024-07-22", provenance="connectivity_test")
    print(f"  [OK] superseded old relation, added new one ({new_rel_id})")

    all_rels = store.all_relations()
    active = [r for r in all_rels if r.subject_id == "test_sarah" and r.status == "active"]
    superseded = [r for r in all_rels if r.subject_id == "test_sarah" and r.status == "superseded"]
    assert len(active) == 1 and len(superseded) == 1
    print(f"  [OK] all_relations shows exactly 1 active + 1 superseded for the test subject")

    print("\nCleaning up test nodes/relations from your database...")
    with store.driver.session(database=TEST_DB) as session:
        session.run(
            "MATCH (e:Entity) WHERE e.entity_id STARTS WITH 'test_' "
            "DETACH DELETE e"
        )
    print("Done. Your Neo4j Desktop instance is ready for the real pipeline.")
    store.close()


if __name__ == "__main__":
    main()
