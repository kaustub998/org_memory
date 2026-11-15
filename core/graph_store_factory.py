"""
Storage backend factory -- same "pick a backend by name, get a working
object back" pattern as build_connector() in llm_connectors.py, applied
to the graph store instead of the LLM. Also logs which backend got
built, same spirit as the LLM connector logging.

Usage:
    from core.graph_store_factory import build_graph_store

    store = build_graph_store("json", path="my_graph.json")
    # or
    store = build_graph_store("neo4j", uri="bolt://localhost:7687",
                               user="neo4j", password="...")
"""
import os


def build_graph_store(backend: str = "json", **kwargs):
    """
    backend: "json" (TemporalGraphStore, NetworkX + JSON-on-disk) or
             "neo4j" (Neo4jGraphStore, real Bolt connection).
    kwargs are passed straight through to the chosen class's constructor.
    """
    if backend == "json":
        from .graph_store import TemporalGraphStore
        path = kwargs.get("path", "graph_store.json")
        print(f"[graph_store_factory] backend=json  path={path}")
        return TemporalGraphStore(path=path)

    if backend == "neo4j":
        from .graph_store_neo4j import Neo4jGraphStore
        uri = kwargs.get("uri") or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = kwargs.get("user") or os.environ.get("NEO4J_USER", "neo4j")
        password = kwargs.get("password") or os.environ.get("NEO4J_PASSWORD")
        database = kwargs.get("database") or os.environ.get("NEO4J_DATABASE", "neo4j")
        if not password:
            raise ValueError(
                "No Neo4j password provided. Pass password=... or set NEO4J_PASSWORD."
            )
        print(f"[graph_store_factory] backend=neo4j  uri={uri}  database={database}")
        return Neo4jGraphStore(uri=uri, user=user, password=password, database=database)

    raise ValueError(f"Unknown graph store backend '{backend}'. Known: json, neo4j")
