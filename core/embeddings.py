"""
Embedding backends.

Two options, both exposed through the SAME embed()/cosine_sim_matrix()
interface so retrieval.py doesn't care which is active:

  - "local"  (default): sentence-transformers, all-MiniLM-L6-v2, runs on
              your machine, no API key, no per-call cost. This is what
              was already wired into retrieval.py.
  - "openai": OpenAI's real embedding API (text-embedding-3-small),
              reuses the SAME OPENAI_API_KEY as your ChatGPT connector
              -- but note this is a genuinely different model/service
              than gpt-4o-mini chat completions; embeddings and chat are
              billed and served separately even within one provider.

Switch backends with the EMBEDDING_BACKEND environment variable
("local" or "openai") -- defaults to "local" if unset or if the chosen
backend fails to initialize (missing package, missing key, no internet
to fetch local model weights, etc.), same fail-soft philosophy as before.
"""
import os
import numpy as np

REQUESTED_BACKEND = os.environ.get("EMBEDDING_BACKEND", "local")

_model = None            # sentence-transformers model, if backend == local
_openai_client = None    # OpenAI client, if backend == openai
_openai_embed_model = "text-embedding-3-small"

USING_REAL_EMBEDDINGS = False
ACTIVE_BACKEND = None  # "local", "openai", or None if nothing loaded

if REQUESTED_BACKEND == "openai":
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _openai_client = OpenAI(api_key=api_key)
        USING_REAL_EMBEDDINGS = True
        ACTIVE_BACKEND = "openai"
        print(f"[embeddings] Using OpenAI embedding API ({_openai_embed_model}), "
              f"same OPENAI_API_KEY as your ChatGPT connector but a DIFFERENT model/service.")
    except Exception as e:
        print(f"[embeddings] Could not initialize OpenAI embeddings ({type(e).__name__}: {e}). "
              f"Falling back to local sentence-transformers.")

if ACTIVE_BACKEND is None:  # local, either by default or as a fallback from a failed "openai" request
    MODEL_NAME = "all-MiniLM-L6-v2"
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
        USING_REAL_EMBEDDINGS = True
        ACTIVE_BACKEND = "local"
        print(f"[embeddings] Using local embedding model: {MODEL_NAME} (no API key, no per-call cost)")
    except Exception as e:
        print(f"[embeddings] Could not load local sentence-transformers model ({type(e).__name__}: {e}).")
        print("[embeddings] Falling back to TF-IDF. Run `pip install sentence-transformers` "
              "and ensure internet access on first run to download model weights.")


def embed(texts: list[str]) -> np.ndarray:
    """Returns an (N, D) array of embeddings. Only call this if
    USING_REAL_EMBEDDINGS is True -- callers should check that flag and
    fall back to TF-IDF (see retrieval.py) if it's False."""
    if not USING_REAL_EMBEDDINGS:
        raise RuntimeError("No real embedding backend loaded -- check USING_REAL_EMBEDDINGS first.")

    if ACTIVE_BACKEND == "openai":
        print(f"[embeddings] calling openai | model={_openai_embed_model} | {len(texts)} text(s)")
        resp = _openai_client.embeddings.create(model=_openai_embed_model, input=texts)
        return np.array([d.embedding for d in resp.data], dtype=np.float32)

    # local
    return _model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)


def cosine_sim_matrix(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """query_vec: (D,) or (1, D). doc_vecs: (N, D).
    Local embeddings are pre-normalized (embed() does this), so a dot
    product is cosine similarity directly. OpenAI's embeddings are NOT
    pre-normalized, so normalize explicitly here -- this function works
    correctly regardless of which backend produced the vectors."""
    if query_vec.ndim == 1:
        query_vec = query_vec.reshape(1, -1)
    q_norm = query_vec / (np.linalg.norm(query_vec, axis=1, keepdims=True) + 1e-10)
    d_norm = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    return (q_norm @ d_norm.T).flatten()

