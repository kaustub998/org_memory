"""
Neo4j-backed Temporal Organization Graph Store.

Drop-in replacement for TemporalGraphStore (core/graph_store.py) -- exposes
the exact same public method signatures, so pipeline.py and retrieval.py
work UNCHANGED regardless of which backend is active. This is the payoff
of having built the JSON version against a stable interface from the start.

Schema:
    (:Entity {entity_id, canonical_name, entity_type, aliases, first_seen, last_seen})
    (:Entity)-[:RELATION {relation_id, subject_id, relation, object_id,
                           valid_from, valid_to, status, provenance, confidence}]->(:Entity)

A single generic relationship type (:RELATION) is used, with the semantic
relation name (e.g. "leads", "reports_to") stored as a PROPERTY rather than
as the Neo4j relationship type itself. This avoids building relationship
types from untrusted/dynamic strings (a Cypher-injection-shaped footgun)
and makes "give me all relations of type X" a simple property filter.

Setup (Neo4j Desktop):
    1. Create a new local DBMS (any name), Neo4j 5.x, start it.
    2. Note the Bolt URI (usually bolt://localhost:7687) and the password
       you set for the default 'neo4j' user.
    3. pip install neo4j
    4. Run scripts/test_neo4j_connection.py to confirm connectivity BEFORE
       pointing the real pipeline at it.
"""
from typing import Optional
from neo4j import GraphDatabase

from .types import GraphEntity, GraphRelation, new_id


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self._ensure_constraints()

    def close(self):
        self.driver.close()

    def _ensure_constraints(self):
        with self.driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE"
            )
            # Relationship property indexes require Neo4j 5.x syntax.
            session.run(
                "CREATE INDEX relation_id_index IF NOT EXISTS "
                "FOR ()-[r:RELATION]-() ON (r.relation_id)"
            )

    # ---------- entities ----------

    def get_entity(self, entity_id: str) -> Optional[GraphEntity]:
        with self.driver.session(database=self.database) as session:
            rec = session.run(
                "MATCH (e:Entity {entity_id: $id}) RETURN e", id=entity_id
            ).single()
            if not rec:
                return None
            return self._entity_from_node(rec["e"])

    def all_entities(self) -> dict[str, GraphEntity]:
        with self.driver.session(database=self.database) as session:
            recs = session.run("MATCH (e:Entity) RETURN e")
            return {rec["e"]["entity_id"]: self._entity_from_node(rec["e"]) for rec in recs}

    def upsert_entity(self, entity_id: str, name: str, entity_type: str,
                       alias: Optional[str] = None, timestamp: Optional[str] = None) -> GraphEntity:
        existing = self.get_entity(entity_id)
        with self.driver.session(database=self.database) as session:
            if existing:
                new_aliases = list(existing.aliases)
                if alias and alias not in new_aliases and alias.lower() != existing.canonical_name.lower():
                    new_aliases.append(alias)
                session.run(
                    "MATCH (e:Entity {entity_id: $id}) "
                    "SET e.aliases = $aliases, e.last_seen = coalesce($ts, e.last_seen)",
                    id=entity_id, aliases=new_aliases, ts=timestamp,
                )
            else:
                session.run(
                    "CREATE (e:Entity {entity_id: $id, canonical_name: $name, "
                    "entity_type: $etype, aliases: [], first_seen: $ts, last_seen: $ts})",
                    id=entity_id, name=name, etype=entity_type, ts=timestamp,
                )
        return self.get_entity(entity_id)

    # ---------- relations ----------

    def find_active_relation(self, subject_id: str, relation: str, object_id: str) -> Optional[str]:
        with self.driver.session(database=self.database) as session:
            rec = session.run(
                "MATCH (:Entity {entity_id: $sid})-[r:RELATION "
                "{relation: $rel, status: 'active'}]->(:Entity {entity_id: $oid}) "
                "RETURN r.relation_id AS rid LIMIT 1",
                sid=subject_id, rel=relation, oid=object_id,
            ).single()
            return rec["rid"] if rec else None

    def find_active_relations_by_subject_relation(self, subject_id: str, relation: str) -> list[GraphRelation]:
        with self.driver.session(database=self.database) as session:
            recs = session.run(
                "MATCH (:Entity {entity_id: $sid})-[r:RELATION "
                "{relation: $rel, status: 'active'}]->(:Entity) RETURN r",
                sid=subject_id, rel=relation,
            )
            return [self._relation_from_edge(rec["r"]) for rec in recs]

    def add_relation(self, subject_id: str, relation: str, object_id: str,
                      valid_from: str, provenance: str, confidence: float = 1.0) -> str:
        rel_id = new_id("rel")
        with self.driver.session(database=self.database) as session:
            session.run(
                "MATCH (s:Entity {entity_id: $sid}), (o:Entity {entity_id: $oid}) "
                "CREATE (s)-[r:RELATION {relation_id: $rid, subject_id: $sid, "
                "relation: $rel, object_id: $oid, valid_from: $vf, valid_to: null, "
                "status: 'active', provenance: $prov, confidence: $conf}]->(o)",
                sid=subject_id, oid=object_id, rid=rel_id, rel=relation,
                vf=valid_from, prov=provenance, conf=confidence,
            )
        return rel_id

    def supersede_relation(self, relation_id: str, valid_to: str):
        with self.driver.session(database=self.database) as session:
            result = session.run(
                "MATCH ()-[r:RELATION {relation_id: $rid}]->() "
                "SET r.status = 'superseded', r.valid_to = $vt RETURN r.relation_id AS rid",
                rid=relation_id, vt=valid_to,
            ).single()
            if not result:
                raise KeyError(f"relation {relation_id} not found")

    def all_relations(self) -> list[GraphRelation]:
        with self.driver.session(database=self.database) as session:
            recs = session.run("MATCH ()-[r:RELATION]->() RETURN r")
            return [self._relation_from_edge(rec["r"]) for rec in recs]

    def relations_for_entity(self, entity_id: str) -> list[GraphRelation]:
        with self.driver.session(database=self.database) as session:
            recs = session.run(
                "MATCH (e:Entity {entity_id: $id})-[r:RELATION]-() RETURN DISTINCT r",
                id=entity_id,
            )
            return [self._relation_from_edge(rec["r"]) for rec in recs]

    # ---------- persistence ----------
    # No-ops: every write above is already committed to Neo4j immediately.
    # save()/load() only exist so callers written against TemporalGraphStore
    # don't need an if/else on which backend is active.

    def save(self):
        pass

    # ---------- helpers ----------

    @staticmethod
    def _entity_from_node(node) -> GraphEntity:
        return GraphEntity(
            entity_id=node["entity_id"],
            canonical_name=node["canonical_name"],
            entity_type=node["entity_type"],
            aliases=list(node.get("aliases", [])),
            first_seen=node.get("first_seen"),
            last_seen=node.get("last_seen"),
        )

    @staticmethod
    def _relation_from_edge(edge) -> GraphRelation:
        return GraphRelation(
            relation_id=edge["relation_id"],
            subject_id=edge["subject_id"],
            relation=edge["relation"],
            object_id=edge["object_id"],
            valid_from=edge["valid_from"],
            valid_to=edge.get("valid_to"),
            status=edge.get("status", "active"),
            provenance=edge.get("provenance", ""),
            confidence=edge.get("confidence", 1.0),
        )
