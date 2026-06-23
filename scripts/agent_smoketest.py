#!/usr/bin/env python
"""Live smoke test for the agentic NL structure builder (nl_agent).

Runs a handful of free-text prompts through the tool-calling worker against one
or more Groq models and prints, for each, the steps the model took and the final
structure's formula. Requires a real key:

    GROQ_API_KEY=gsk_... ./venv/bin/python scripts/agent_smoketest.py

Optional args:
    --models m1,m2     comma-separated Groq model ids (default: the two below)
    --prompt "text"    run a single custom prompt instead of the built-in set
"""
from __future__ import annotations

import argparse
import os
import sys

# Run from the repo root; make src/ importable without installing.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vasp_auto.nl_agent import agent_build_from_text  # noqa: E402

DEFAULT_MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
DEFAULT_PROMPTS = [
    "bulk fcc platinum",
    "Pt(111) slab, 4 layers, 3x3, with an O atom adsorbed on top",
    "a CO molecule standing on a 2x2 Cu(100) slab",
    "graphene under a 2x2 Au fcc(111) slab",
]


def run(prompt: str, model: str, key: str) -> bool:
    print(f"\n=== [{model}] {prompt}")
    try:
        struct, transcript = agent_build_from_text(prompt, api_key=key, model=model)
    except Exception as exc:  # noqa: BLE001 — smoke test wants the message, not a trace
        print(f"  FAIL: {type(exc).__name__}: {exc}")
        return False
    for step in transcript:
        print(f"  - {step['tool']}({step['args']}) -> {step['result']}")
    formula = "".join(f"{e}{c}" for e, c in zip(struct["elements"], struct["counts"]))
    print(f"  => built {formula} ({sum(struct['counts'])} atoms) in {len(transcript)} steps")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--prompt")
    args = ap.parse_args()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        print("Set GROQ_API_KEY first:  GROQ_API_KEY=gsk_... ./venv/bin/python scripts/agent_smoketest.py")
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    prompts = [args.prompt] if args.prompt else DEFAULT_PROMPTS

    results: dict[str, tuple[int, int]] = {}
    for model in models:
        ok = sum(run(p, model, key) for p in prompts)
        results[model] = (ok, len(prompts))

    print("\n--- summary ---")
    for model, (ok, total) in results.items():
        print(f"  {model}: {ok}/{total} prompts produced a structure")
    return 0 if all(ok == total for ok, total in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
