"""
Layer: Temporal Organization Graph Store.

Phase 1 implementation: NetworkX in-memory graph + JSON-on-disk
persistence. Nodes and edges carry the SAME fields your architecture
slide promises for the eventual Neo4j store (entity type, aliases,
validity intervals, provenance, confidence) -- so migrating to Neo4j
later is a storage-adapter swap, not a schema redesign.
"""
import json
import os
import networkx as nx
from dataclasses import asdict
from typing import Optional

from .types import GraphEntity, GraphRelation, new_id


class TemporalGraphStore:
    def __init__(self, path: str = "graph_store.json"):
        self.path = path
        self.g = nx.MultiDiGraph()
        if os.path.exists(path):
            self._load()

    # ---------- entities ----------

    def get_entity(self, entity_id: str) -> Optional[GraphEntity]:
        if entity_id not in self.g.nodes:
            return None
        return GraphEntity(entity_id=entity_id, **self.g.nodes[entity_id])

    def all_entities(self) -> dict[str, GraphEntity]:
        return {n: GraphEntity(entity_id=n, **d) for n, d in self.g.nodes(data=True)}

    def upsert_entity(self, entity_id: str, name: str, entity_type: str,
                       alias: Optional[str] = None, timestamp: Optional[str] = None) -> GraphEntity:
        if entity_id in self.g.nodes:
            data = self.g.nodes[entity_id]
            if alias and alias not in data["aliases"] and alias.lower() != data["canonical_name"].lower():
                data["aliases"].append(alias)
            if timestamp:
                data["last_seen"] = timestamp
        else:
            self.g.add_node(
                entity_id,
                canonical_name=name,
                entity_type=entity_type,
                aliases=[],
                first_seen=timestamp,
                last_seen=timestamp,
            )
        return self.get_entity(entity_id)

    # ---------- relations ----------

    def find_active_relation(self, subject_id: str, relation: str, object_id: str) -> Optional[str]:
        """Returns relation_id of an existing ACTIVE edge with this exact (s, r, o), if any."""
        for _, _, key, data in self.g.out_edges(subject_id, keys=True, data=True):
            if data["relation"] == relation and data["object_id"] == object_id and data["status"] == "active":
                return key
        return None

    def find_active_relations_by_subject_relation(self, subject_id: str, relation: str) -> list[GraphRelation]:
        """All active edges with this subject+relation, regardless of object -- used to detect
        conflicts, e.g. subject already has an active 'leads' edge to a DIFFERENT object."""
        out = []
        for _, _, key, data in self.g.out_edges(subject_id, keys=True, data=True):
            if data["relation"] == relation and data["status"] == "active":
                out.append(GraphRelation(**data))
        return out

    def add_relation(self, subject_id: str, relation: str, object_id: str,
                      valid_from: str, provenance: str, confidence: float = 1.0) -> str:
        rel_id = new_id("rel")
        self.g.add_edge(
            subject_id, object_id, key=rel_id,
            relation_id=rel_id, subject_id=subject_id, relation=relation, object_id=object_id,
            valid_from=valid_from, valid_to=None, status="active",
            provenance=provenance, confidence=confidence,
        )
        return rel_id

    def supersede_relation(self, relation_id: str, valid_to: str):
        """Marks an edge as no longer current (used by the update policy)."""
        for u, v, key, edata in list(self.g.edges(keys=True, data=True)):
            if key == relation_id:
                edata["status"] = "superseded"
                edata["valid_to"] = valid_to
                return
        raise KeyError(f"relation {relation_id} not found")

    def all_relations(self) -> list[GraphRelation]:
        return [GraphRelation(**data) for _, _, key, data in self.g.edges(keys=True, data=True)]

    def relations_for_entity(self, entity_id: str) -> list[GraphRelation]:
        out = []
        for u, v, key, data in self.g.edges(keys=True, data=True):
            if u == entity_id or v == entity_id:
                out.append(GraphRelation(**data))
        return out

    # ---------- persistence ----------

    def save(self):
        payload = {
            "nodes": [{"id": n, **d} for n, d in self.g.nodes(data=True)],
            "edges": [{"u": u, "v": v, "key": k, **d} for u, v, k, d in self.g.edges(keys=True, data=True)],
        }
        with open(self.path, "w") as f:
            json.dump(payload, f, indent=2)

    def _load(self):
        with open(self.path) as f:
            payload = json.load(f)
        for n in payload["nodes"]:
            node_id = n.pop("id")
            self.g.add_node(node_id, **n)
        for e in payload["edges"]:
            u, v, k = e.pop("u"), e.pop("v"), e.pop("key")
            self.g.add_edge(u, v, key=k, **e)
