"""
Unified LLM connector layer.

Two concrete connector classes cover essentially every provider you'd
want to try:

  - AnthropicConnector          -- native Claude API
  - OpenAICompatibleConnector   -- everything else, because Groq, real
                                    OpenAI, Google Gemini, DeepSeek,
                                    OpenRouter, and Zhipu (GLM) all expose
                                    the SAME OpenAI chat-completions shape.
                                    Only base_url + api_key + model differ.

Both implement the same .complete(system, user, max_tokens) -> str
interface, so extraction.py/qa.py can take an injected connector instead
of a hardcoded client -- letting you run multiple providers (or multiple
instances of the same provider) side by side, fall back from one to
another, or ensemble/vote across them.

IMPORTANT correction on your ChatGPT Plus key: a Plus subscription
(chat.openai.com) does NOT include API credits. API access is billed
separately, pay-as-you-go, from a key generated at platform.openai.com --
your Plus key won't work here unless that account also has API billing
set up. OPENAI_API_KEY below assumes a real platform.openai.com key.
"""
from abc import ABC, abstractmethod
import os


class LLMConnector(ABC):
    """Common interface every provider connector implements."""

    name: str = "base"

    def __init__(self):
        # Usage accumulated across all LLM calls for the current operation.
        self._usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        }

        self._models_used = set()

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        """Returns the model's plain-text response."""
        ...

    def reset_usage(self):
        """Reset usage counters before processing a new meeting."""
        self._usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
        }

        self._models_used = set()

    def _record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int | None = None,
        model: str | None = None,
    ):
        """Accumulate usage from one LLM call."""

        self._usage["input_tokens"] += input_tokens or 0
        self._usage["output_tokens"] += output_tokens or 0

        if total_tokens is not None:
            self._usage["total_tokens"] += total_tokens
        else:
            self._usage["total_tokens"] += (
                (input_tokens or 0) + (output_tokens or 0)
            )

        self._usage["calls"] += 1

        if model:
            self._models_used.add(model)

    def get_usage(self) -> dict:
        """Return a copy of accumulated usage."""

        return {
            **self._usage,
            "models_used": sorted(self._models_used),
        }

    def _log_call(self, model: str, provider: str):
        print(
            f"[llm_connector] calling {provider} | model={model}"
        )

    def _log_usage(self, provider: str, usage_str: str):
        if usage_str:
            print(
                f"[llm_connector] {provider} usage: {usage_str}"
            )


class AnthropicConnector(LLMConnector):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        from anthropic import Anthropic
        super().__init__()
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.name = f"anthropic:{model}"

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        self._log_call(self.model, "anthropic")
        resp = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        if getattr(resp, "usage", None):
            self._record_usage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                model=self.model,
            )
            self._log_usage("anthropic", f"input={resp.usage.input_tokens} output={resp.usage.output_tokens}")
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class OpenAICompatibleConnector(LLMConnector):
    """
    Works for OpenAI and OpenAI-compatible providers such as
    Groq, Gemini, DeepSeek, OpenRouter, Zhipu, etc.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        provider_label: str = "openai-compatible"
    ):

        from openai import OpenAI

        super().__init__()

        if not api_key:
            raise ValueError(
                f"No API key provided for {provider_label}. "
                f"Set the relevant environment variable "
                f"or pass api_key explicitly."
            )

        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

        self.model = model
        self.provider_label = provider_label
        self.name = f"{provider_label}:{model}"

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1000
    ) -> str:

        self._log_call(
            self.model,
            self.provider_label
        )

        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": user
                },
            ],
        )

        # Some providers/gateways can serve the request
        # using a different model.
        actual_model = getattr(resp, "model", None)

        if actual_model and actual_model != self.model:
            print(
                f"[llm_connector] NOTE: "
                f"{self.provider_label} served this from "
                f"'{actual_model}', not the requested "
                f"'{self.model}'"
            )

        if getattr(resp, "usage", None):

            u = resp.usage

            input_tokens = getattr(
                u,
                "prompt_tokens",
                0
            )

            output_tokens = getattr(
                u,
                "completion_tokens",
                0
            )

            total_tokens = getattr(
                u,
                "total_tokens",
                input_tokens + output_tokens
            )

            self._record_usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=actual_model or self.model,
            )

            self._log_usage(
                self.provider_label,
                f"prompt={input_tokens} "
                f"completion={output_tokens} "
                f"total={total_tokens}"
            )

        return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Provider presets: base_url + default model + which env var holds the key.
# Add/edit entries here as free tiers change -- these are the parts most
# likely to go stale, keep them in one place.
# ---------------------------------------------------------------------------

PROVIDER_PRESETS = {
    "anthropic": {
        "kind": "anthropic",
        "default_model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",   # must be a real platform.openai.com key, NOT a ChatGPT Plus login
    },
    "groq": {
        "kind": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",     # free, no credit card -- console.groq.com/keys
    },
    "gemini": {
        "kind": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "env_key": "GEMINI_API_KEY",   # free tier via aistudio.google.com/apikey
    },
    "deepseek": {
        "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",  # platform.deepseek.com -- free credits for new signups
    },
    "openrouter": {
        "kind": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",  # ":free" suffix = no-cost model
        "env_key": "OPENROUTER_API_KEY",  # openrouter.ai/keys
    },
    "zhipu": {
        "kind": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_model": "glm-4.5-flash",
        "env_key": "ZHIPU_API_KEY",   # open.bigmodel.cn -- genuinely free, no published cap
    },
}


def build_connector(provider: str, model: str | None = None, api_key: str | None = None) -> LLMConnector:
    """
    Factory: build_connector("groq"), build_connector("anthropic", model="claude-haiku-4-5-20251001"), etc.
    Reads the API key from the preset's env var unless you pass one explicitly.
    """
    if provider not in PROVIDER_PRESETS:
        raise ValueError(f"Unknown provider '{provider}'. Known: {list(PROVIDER_PRESETS)}")
    preset = PROVIDER_PRESETS[provider]
    key = api_key or os.environ.get(preset["env_key"])
    chosen_model = model or preset["default_model"]

    if preset["kind"] == "anthropic":
        return AnthropicConnector(model=chosen_model, api_key=key)
    return OpenAICompatibleConnector(
        base_url=preset["base_url"], model=chosen_model, api_key=key, provider_label=provider,
    )


class ConnectorPool:
    """
    Holds multiple connector instances (different providers, or several
    of the same one) for fallback or ensemble use. This is the "multiple
    instances of Claude / ChatGPT / free keys" piece you asked for.
    """
    def __init__(self, connectors: list[LLMConnector]):
        self.connectors = connectors

    def complete_with_fallback(self, system: str, user: str, max_tokens: int = 1000) -> tuple[str, str]:
        """Tries each connector in order, returns (response, connector_name_used).
        Useful when a free tier's rate limit is hit -- fall through to the next."""
        last_error = None
        for conn in self.connectors:
            try:
                return conn.complete(system, user, max_tokens), conn.name
            except Exception as e:
                last_error = e
                print(f"[ConnectorPool] {conn.name} failed ({type(e).__name__}: {e}), trying next...")
        raise RuntimeError(f"All connectors failed. Last error: {last_error}")

    def complete_all(self, system: str, user: str, max_tokens: int = 1000) -> dict[str, str]:
        """Runs the SAME prompt on every connector, returns {connector_name: response}.
        Useful for comparing extraction quality across models, or majority-vote ensembling."""
        results = {}
        for conn in self.connectors:
            try:
                results[conn.name] = conn.complete(system, user, max_tokens)
            except Exception as e:
                results[conn.name] = f"[ERROR: {type(e).__name__}: {e}]"
        return results
