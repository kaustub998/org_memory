"""
Runs the SAME extraction prompt through multiple real LLM providers side
by side, so you can compare quality/speed across free options before
picking one (or building a fallback chain / ensemble).

Set whichever API keys you actually have as environment variables --
you don't need all of them, the script only builds connectors for keys
that are actually set:

    export ANTHROPIC_API_KEY=sk-ant-...      # paid, what the pipeline defaults to
    export GROQ_API_KEY=gsk_...              # free, no credit card -- console.groq.com/keys
    export GEMINI_API_KEY=...                # free tier -- aistudio.google.com/apikey
    export DEEPSEEK_API_KEY=...              # free credits for new signups
    export OPENROUTER_API_KEY=...            # free models available, filter by ":free"
    export ZHIPU_API_KEY=...                 # genuinely free GLM-4.5-flash

    python demo/multi_llm_demo.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.llm_connectors import build_connector, ConnectorPool, PROVIDER_PRESETS
from core.extraction import EXTRACTION_SYSTEM_PROMPT

SAMPLE_TRANSCRIPT = """
COUNCIL MEETING - JANUARY 10, 2024
CHAIR: Sarah Chen has been appointed as the Project Manager for the
Riverfront Park Renewal project. Sarah Chen will report directly to the
Director of Public Works, Mark Ibsen.
"""


def main():
    available = []
    for provider, preset in PROVIDER_PRESETS.items():
        if os.environ.get(preset["env_key"]):
            try:
                available.append(build_connector(provider))
                print(f"[OK]      {provider} -- key found, connector built ({preset['default_model']})")
            except Exception as e:
                print(f"[SKIP]    {provider} -- failed to build connector: {e}")
        else:
            print(f"[SKIP]    {provider} -- no {preset['env_key']} set")

    if not available:
        print("\nNo API keys found in the environment. Set at least one "
              "(GROQ_API_KEY is easiest -- free, no credit card) and re-run.")
        return

    print(f"\nRunning the same extraction prompt through {len(available)} connector(s)...\n")
    pool = ConnectorPool(available)
    results = pool.complete_all(EXTRACTION_SYSTEM_PROMPT, SAMPLE_TRANSCRIPT, max_tokens=500)

    for name, output in results.items():
        print("=" * 70)
        print(f"PROVIDER: {name}")
        print("=" * 70)
        print(output)
        print()


if __name__ == "__main__":
    main()
