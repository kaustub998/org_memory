"""
Layer: Question Answering.
Takes hybrid-retrieved evidence and asks the LLM to answer using ONLY
that evidence -- this is the Graph+Vector RAG formulation from your
methodology slide (Slide 20).

Accepts an injected LLMConnector -- defaults to Claude if none given.
"""
from .llm_connectors import LLMConnector, build_connector

_default_connector: LLMConnector | None = None

QA_SYSTEM_PROMPT = """You answer questions about an organization using ONLY the evidence provided.
Each piece of evidence includes its source meeting for traceability.
If the evidence is insufficient or conflicting, say so explicitly rather than guessing.
Cite which piece(s) of evidence you used, briefly, at the end of your answer."""


def answer_question(question: str, evidence: list[str], connector: LLMConnector | None = None) -> str:
    global _default_connector
    if not evidence:
        return "No relevant evidence found in the organizational graph for this question."
    if connector is None:
        if _default_connector is None:
            _default_connector = build_connector("anthropic")
        connector = _default_connector

    evidence_block = "\n".join(f"- {e}" for e in evidence)
    prompt = f"Question: {question}\n\nEvidence:\n{evidence_block}"
    return connector.complete(QA_SYSTEM_PROMPT, prompt, max_tokens=500).strip()
