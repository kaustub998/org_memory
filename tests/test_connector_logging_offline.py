"""
Verifies AnthropicConnector and OpenAICompatibleConnector actually print
model + usage info, and that OpenAICompatibleConnector flags when a
provider (e.g. OpenRouter) serves a different model than requested --
all using mocked SDK clients, no real API keys needed. Standalone script,
no pytest dependency.
"""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from core.llm_connectors import AnthropicConnector, OpenAICompatibleConnector


class Capture:
    """Minimal stand-in for pytest's capsys, so this runs without pytest."""
    def __enter__(self):
        self._buf = io.StringIO()
        self._orig_stdout = sys.stdout
        sys.stdout = self._buf
        return self
    def __exit__(self, *a):
        sys.stdout = self._orig_stdout
    def text(self) -> str:
        return self._buf.getvalue()


def test_anthropic_connector_logs_model_and_usage():
    fake_block = MagicMock(type="text", text="hello from claude")
    fake_usage = MagicMock(input_tokens=10, output_tokens=5)
    fake_response = MagicMock(content=[fake_block], usage=fake_usage)

    with patch("anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = fake_response
        conn = AnthropicConnector(model="claude-sonnet-4-6", api_key="fake-key")
        with Capture() as cap:
            result = conn.complete("sys", "hi")
        out = cap.text()

    assert result == "hello from claude"
    assert "model=claude-sonnet-4-6" in out
    assert "input=10 output=5" in out
    print("[PASS] AnthropicConnector logs model + token usage")


def test_openai_compatible_connector_logs_model_and_usage():
    fake_message = MagicMock(content="hello from gpt")
    fake_choice = MagicMock(message=fake_message)
    fake_usage = MagicMock(prompt_tokens=8, completion_tokens=3, total_tokens=11)
    fake_response = MagicMock(choices=[fake_choice], usage=fake_usage, model="gpt-4o-mini")

    with patch("openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = fake_response
        conn = OpenAICompatibleConnector(
            base_url="https://api.openai.com/v1", model="gpt-4o-mini",
            api_key="fake-key", provider_label="openai",
        )
        with Capture() as cap:
            result = conn.complete("sys", "hi")
        out = cap.text()

    assert result == "hello from gpt"
    assert "openai" in out and "model=gpt-4o-mini" in out
    assert "prompt=8 completion=3 total=11" in out
    print("[PASS] OpenAICompatibleConnector logs model + token usage")


def test_openrouter_flags_when_actual_model_differs():
    """OpenRouter can auto-route to a different model than requested --
    confirm the connector notices and prints a NOTE about it."""
    fake_message = MagicMock(content="hello from whatever OpenRouter picked")
    fake_choice = MagicMock(message=fake_message)
    fake_response = MagicMock(
        choices=[fake_choice], usage=None,
        model="meta-llama/llama-3.1-8b-instruct",  # different from what we'll request below
    )

    with patch("openai.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = fake_response
        conn = OpenAICompatibleConnector(
            base_url="https://openrouter.ai/api/v1",
            model="meta-llama/llama-3.3-70b-instruct:free",
            api_key="fake-key", provider_label="openrouter",
        )
        with Capture() as cap:
            conn.complete("sys", "hi")
        out = cap.text()

    assert "NOTE" in out and "llama-3.1-8b-instruct" in out
    print("[PASS] OpenRouter model-mismatch is detected and logged")


if __name__ == "__main__":
    test_anthropic_connector_logs_model_and_usage()
    test_openai_compatible_connector_logs_model_and_usage()
    test_openrouter_flags_when_actual_model_differs()
    print("\nAll connector logging checks passed with mocked SDK clients.")
