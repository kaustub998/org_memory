"""
Structural test of ConnectorPool's fallback and ensemble logic, using
fake connectors (no real API keys, no network). Verifies the plumbing
before you point it at real Groq/Gemini/Claude keys.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.llm_connectors import LLMConnector, ConnectorPool


class FakeConnector(LLMConnector):
    def __init__(self, name, response=None, should_fail=False):
        self.name = name
        self._response = response or f"response from {name}"
        self._should_fail = should_fail

    def complete(self, system, user, max_tokens=1000):
        if self._should_fail:
            raise RuntimeError(f"{self.name} simulated failure (e.g. rate limit)")
        return self._response


def test_fallback_uses_first_working_connector():
    pool = ConnectorPool([
        FakeConnector("groq_primary", should_fail=True),
        FakeConnector("gemini_backup", response="gemini says hi"),
        FakeConnector("claude_last_resort"),
    ])
    response, used = pool.complete_with_fallback("sys", "hello")
    assert used == "gemini_backup", f"expected fallback to gemini_backup, got {used}"
    assert response == "gemini says hi"
    print("[PASS] fallback skips a failing connector and uses the next working one")


def test_fallback_raises_if_all_fail():
    pool = ConnectorPool([
        FakeConnector("a", should_fail=True),
        FakeConnector("b", should_fail=True),
    ])
    try:
        pool.complete_with_fallback("sys", "hello")
        raise AssertionError("expected RuntimeError when all connectors fail")
    except RuntimeError:
        print("[PASS] raises clearly when every connector in the pool fails")


def test_complete_all_runs_every_connector_and_captures_errors():
    pool = ConnectorPool([
        FakeConnector("claude", response="claude's answer"),
        FakeConnector("groq", response="groq's answer"),
        FakeConnector("broken", should_fail=True),
    ])
    results = pool.complete_all("sys", "hello")
    assert results["claude"] == "claude's answer"
    assert results["groq"] == "groq's answer"
    assert "ERROR" in results["broken"]
    print("[PASS] complete_all runs every connector and captures per-connector errors")


if __name__ == "__main__":
    test_fallback_uses_first_working_connector()
    test_fallback_raises_if_all_fail()
    test_complete_all_runs_every_connector_and_captures_errors()
    print("\nAll connector-pool logic checks passed against fake connectors.")
    print("Run demo/multi_llm_demo.py with real API keys set to test actual providers.")
