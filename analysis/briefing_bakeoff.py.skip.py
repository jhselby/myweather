#!/usr/bin/env python3
"""Briefing model bake-off — run candidate (provider, model, temperature)
configs against the current production weather_data.json and print the
resulting headline + subheadline side-by-side for eyeball comparison.

Runs from your Mac, NOT from the collector. Uses the same SYSTEM_PROMPT and
_build_weather_summary() the production code uses, so the inputs are
identical to what the live collector would feed each model.

Setup:
  - GROQ_API_KEY      pulled from `gcloud secrets versions access latest --secret=groq-api-key`
  - OPENROUTER_API_KEY pulled from `gcloud secrets versions access latest --secret=openrouter-api-key`
  - GEMINI_API_KEY    pulled from `gcloud secrets versions access latest --secret=gemini-api-key`
  Override any via env if you want.

Usage:
  python3 analysis/briefing_bakeoff.py            # uses live weather_data.json
  python3 analysis/briefing_bakeoff.py --runs 3   # 3 samples per config (catches temperature variance)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Pull in the production prompt construction so the bake-off matches live behavior.
# briefing_ai.py reads GEMINI_API_KEY etc. at import time; we only need the
# constants and one pure function, so satisfy the env-var read with placeholders.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
for _k in ("GEMINI_API_KEY", "GROQ_API_KEY"):
    os.environ.setdefault(_k, "placeholder-for-import")
from weather_collector.fetchers.briefing_ai import (  # noqa: E402
    SYSTEM_PROMPT,
    _build_weather_summary,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL_FMT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _secret(name):
    try:
        return subprocess.check_output(
            ["gcloud", "secrets", "versions", "access", "latest", "--secret", name],
            text=True,
        ).strip()
    except Exception as e:
        print(f"  ⚠ could not fetch {name} from Secret Manager: {e}")
        return None


def _fetch_live_weather_data():
    """Pull and decompress the live weather_data.json (might be gzip, might be plain)."""
    raw = subprocess.check_output(["gsutil", "cat", "gs://myweather-data/weather_data.json"])
    if raw[:2] == b"\x1f\x8b":
        import gzip
        return json.loads(gzip.decompress(raw))
    return json.loads(raw)


# --- Provider callers --------------------------------------------------------

def call_groq(model, temperature, user_msg, key):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 600,
    }
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_openrouter(model, temperature, user_msg, key):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 600,
    }
    r = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://wymancove.com",
            "X-Title": "MyWeather briefing bake-off",
        },
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_gemini(model, temperature, user_msg, key):
    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nWeather data for right now:\n{user_msg}"}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
    }
    r = requests.post(
        GEMINI_URL_FMT.format(model=model),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


# --- Output parsing ----------------------------------------------------------

def parse_headline(raw_text):
    """Same JSON extraction the production code does: strip markdown fences,
    then json.loads. Returns (headline, subheadline) or (None, raw_text) on failure."""
    t = raw_text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
    if t.endswith("```"):
        t = t[:-3]
    try:
        d = json.loads(t.strip())
        return d.get("headline", "").strip(), d.get("subheadline", "").strip()
    except Exception:
        return None, raw_text[:200]


# --- The bake-off ------------------------------------------------------------

CONFIGS = [
    # (label, provider, model, temperature, status)
    # status is "evaluated" (already measured in a prior run) or "new" (not yet measured).
    # --new-only filters to status="new" so re-runs don't re-burn quota on the Groq
    # configs we already characterized 2026-06-18.
    #
    # Gemini intentionally excluded from this list to avoid burning the live
    # quota during testing. To include it, add a row with provider="gemini".
    #
    # Baseline: current production
    ("Groq Llama-3.3 70B @ 0.5 (CURRENT PROD)",    "groq", "llama-3.3-70b-versatile", 0.5, "evaluated"),
    # Same model, just turn the dial up
    ("Groq Llama-3.3 70B @ 0.85",                  "groq", "llama-3.3-70b-versatile", 0.85, "evaluated"),
    # Other Groq-hosted models (verified live 2026-06-18 via /v1/models)
    ("Groq Llama-4 Scout 17B @ 0.85",              "groq", "meta-llama/llama-4-scout-17b-16e-instruct", 0.85, "evaluated"),
    ("Groq GPT-OSS 120B @ 0.85",                   "groq", "openai/gpt-oss-120b", 0.85, "evaluated"),
    ("Groq GPT-OSS 20B @ 0.85",                    "groq", "openai/gpt-oss-20b", 0.85, "evaluated"),
    ("Groq Qwen-3.6 27B @ 0.85",                   "groq", "qwen/qwen3.6-27b", 0.85, "evaluated"),
    ("Groq Qwen-3 32B @ 0.85",                     "groq", "qwen/qwen3-32b", 0.85, "evaluated"),
    # OpenRouter free routes (verified live 2026-06-18)
    ("OpenRouter Hermes-3 Llama-405B (free)",      "openrouter", "nousresearch/hermes-3-llama-3.1-405b:free", 0.85, "new"),
    ("OpenRouter Qwen-3 80B (free)",               "openrouter", "qwen/qwen3-next-80b-a3b-instruct:free", 0.85, "new"),
    ("OpenRouter Gemma-4 31B (free)",              "openrouter", "google/gemma-4-31b-it:free", 0.85, "evaluated"),
    ("OpenRouter Dolphin-Mistral 24B (free)",      "openrouter", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", 0.85, "new"),
    # Big-brain OpenRouter free routes added 2026-06-18 (per Joe's "what else free")
    ("OpenRouter Nemotron-3 Ultra 550B (free)",    "openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 0.85, "new"),
    ("OpenRouter Nemotron-3 Super 120B (free)",    "openrouter", "nvidia/nemotron-3-super-120b-a12b:free", 0.85, "new"),
    # OpenRouter PAID — DeepSeek tier (no free routes available 2026-06-18).
    # Per-call cost is fractions of a cent; including for quality comparison only.
    # Will 402 if your OpenRouter account has no credits — that's fine, treat as skip.
    ("OpenRouter DeepSeek V4 Pro (PAID ~$0.87/M)", "openrouter", "deepseek/deepseek-v4-pro", 0.85, "new"),
    ("OpenRouter DeepSeek V4 Flash (PAID ~$0.18/M)", "openrouter", "deepseek/deepseek-v4-flash", 0.85, "new"),
    ("OpenRouter DeepSeek V3.2 (PAID ~$0.34/M)",   "openrouter", "deepseek/deepseek-v3.2", 0.85, "new"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="samples per config (default 1)")
    ap.add_argument("--data", type=str, default=None, help="path to a weather_data.json to use (default: live from GCS)")
    ap.add_argument("--new-only", action="store_true",
                    help='skip configs marked "evaluated" — only run "new" ones (saves Groq quota on re-runs)')
    args = ap.parse_args()
    selected = [c for c in CONFIGS if not args.new_only or c[4] == "new"]

    print("  ⇣ fetching weather_data.json…")
    if args.data:
        wd = json.load(open(args.data))
    else:
        wd = _fetch_live_weather_data()
    summary = _build_weather_summary(wd)
    user_msg = f"Weather data for right now:\n{summary}"
    print(f"  ✓ summary: {len(summary)} chars, {len(user_msg.split())} words\n")

    # Secret Manager is the source of truth — local shell env vars may be stale
    # from previous sessions. Only fall back to env if the secret isn't accessible.
    keys = {
        "groq":       _secret("groq-api-key")       or os.environ.get("GROQ_API_KEY"),
        "openrouter": _secret("openrouter-api-key") or os.environ.get("OPENROUTER_API_KEY"),
        "gemini":     _secret("gemini-api-key")     or os.environ.get("GEMINI_API_KEY"),
    }

    callers = {"groq": call_groq, "openrouter": call_openrouter, "gemini": call_gemini}

    bar = "─" * 78
    print(f"  running {len(selected)} of {len(CONFIGS)} configs{' (--new-only)' if args.new_only else ''}")
    print(bar)
    for label, provider, model, temp, _status in selected:
        key = keys.get(provider)
        if not key:
            print(f"⊘ {label}\n  (no {provider} key available — skipping)\n{bar}")
            continue
        for run_i in range(args.runs):
            run_tag = f" run {run_i+1}/{args.runs}" if args.runs > 1 else ""
            print(f"▸ {label}{run_tag}")
            t0 = time.time()
            try:
                raw = callers[provider](model, temp, user_msg, key)
                elapsed = time.time() - t0
                headline, sub = parse_headline(raw)
                if headline is None:
                    print(f"  ⚠ JSON parse failed ({elapsed:.1f}s) — raw[:200]: {sub}")
                else:
                    print(f"  HEADLINE:    {headline}")
                    print(f"  SUBHEADLINE: {sub}")
                    print(f"  ({elapsed:.1f}s)")
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                body = (e.response.text if e.response is not None else "")[:200]
                print(f"  ⚠ HTTP {status}: {body}")
            except Exception as e:
                print(f"  ⚠ {type(e).__name__}: {e}")
        print(bar)


if __name__ == "__main__":
    main()
