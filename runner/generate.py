"""Generate samples: one prompt in, one response out, no tools, no turns.

    python3 -m runner.generate [--limit N] [--models M] [--dry-run]

Single prompt, single response, raw model API — no agentic loop and no tool
scaffolding, both of which would be confounds.

Resumable: a sample already on disk is never regenerated, so an interrupted
run continues where it stopped and costs nothing to restart.

Everything needed to reproduce a sample is written beside it — model id,
temperature, seed, the serving provider, and the prompt hash. For
routing-sensitive models the gateway is told not to fail over, because a
silent switch to a differently-quantised host would break the recorded
-quantisation invariant without any visible symptom.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from groundtruth.sdk import REPO_ROOT, load_pins
from runner.env import require

SAMPLES_DIR = REPO_ROOT / "build" / "samples"
PUBLISHED = REPO_ROOT / "prompts" / "corpus.json"
HELD_OUT = REPO_ROOT / "prompts.local" / "heldout.json"

# Sent verbatim with every request. Says what to produce and nothing about
# which APIs to use — naming a modern API here would hand the model the answer
# and the benchmark would measure instruction-following instead of currency.
SYSTEM = (
    "You are writing Swift code for an iOS app. Reply with a single "
    "self-contained SwiftUI source file and nothing else: no explanation, no "
    "commentary. Do not include import statements for anything beyond SwiftUI."
)

FENCE = re.compile(r"```(?:swift|Swift)?\s*\n(.*?)```", re.DOTALL)


class GenerationError(RuntimeError):
    pass


@dataclass
class Sample:
    prompt_id: str
    split: str
    api_area: str
    model: str
    sample_index: int
    temperature: float
    seed: int | None
    prompt_sha256: str
    raw_response: str
    swift_source: str
    provider: str | None          # which backend actually served it
    finish_reason: str | None
    usage: dict
    generated_at: str
    error: str | None = None


def extract_swift(text: str) -> str:
    """Pull the Swift out of a markdown reply.

    Recorded separately from the raw response so a bad extraction is visible
    rather than silently scoring as a compile failure.
    """
    blocks = FENCE.findall(text)
    if blocks:
        return max(blocks, key=len).strip()
    return text.strip()


def load_corpus() -> list[dict]:
    prompts = json.loads(PUBLISHED.read_text())["prompts"]
    if HELD_OUT.is_file():
        prompts += json.loads(HELD_OUT.read_text())["prompts"]
    else:
        print("note: held-out split absent — generating published prompts only")
    return prompts


def sample_path(model: str, prompt_id: str, index: int) -> Path:
    return SAMPLES_DIR / model.replace("/", "__") / f"{prompt_id}.{index}.json"


def call_gateway(pins: dict, key: str, model: str, task: str,
                 temperature: float, seed: int | None, pin_provider: bool,
                 max_tokens: int) -> dict:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": task},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if seed is not None:
        body["seed"] = seed
    if pin_provider:
        # Open-weight models can be served by several backends at different
        # quantisations. Failover would swap one mid-run without saying so.
        body["provider"] = {"allow_fallbacks": False}

    req = urllib.request.Request(
        f"{pins['gateway']['base_url']}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "ios-evals",
        },
    )
    last: Exception | None = None
    for attempt in range(7):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (429, 500, 502, 503, 529):
                last = GenerationError(f"HTTP {exc.code}: {detail}")
                # Honour Retry-After when the gateway sends it; per-model RPM
                # limits need far longer than a short exponential backoff.
                wait = exc.headers.get("Retry-After")
                try:
                    delay = float(wait) if wait else min(60.0, 3 * 2 ** attempt)
                except ValueError:
                    delay = min(60.0, 3 * 2 ** attempt)
                time.sleep(delay)
                continue
            raise GenerationError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(min(60.0, 3 * 2 ** attempt))
    raise GenerationError(f"failed after retries: {last}")


def generate_one(pins: dict, key: str, prompt: dict, model: str, index: int) -> Path:
    path = sample_path(model, prompt["id"], index)
    if path.is_file():
        return path

    temperature = float(pins["generation"]["temperature"])
    max_tokens = int(pins["generation"].get("max_tokens", 12000))
    seed = index  # deterministic per sample where the provider honours it
    pin_provider = model in pins["models"].get("routing_sensitive", [])

    try:
        payload = call_gateway(pins, key, model, prompt["task"],
                               temperature, seed, pin_provider, max_tokens)
        choice = (payload.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason")
        if finish == "length" and not raw.strip():
            # Whole budget consumed before any output — on thinking models this
            # means max_tokens is too low, not that the model failed the task.
            raise GenerationError(
                f"truncated before any output (finish_reason=length, "
                f"{(payload.get('usage') or {}).get('completion_tokens')} tokens): "
                f"raise generation.max_tokens")
        sample = Sample(
            prompt_id=prompt["id"], split=prompt["split"], api_area=prompt["api_area"],
            model=model, sample_index=index, temperature=temperature, seed=seed,
            prompt_sha256=hashlib.sha256(prompt["task"].encode()).hexdigest(),
            raw_response=raw, swift_source=extract_swift(raw),
            provider=payload.get("provider"),
            finish_reason=choice.get("finish_reason"),
            usage=payload.get("usage") or {},
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except GenerationError as exc:
        # Retained, not discarded. A model that cannot produce output scores as
        # failure; dropping it would flatter the model.
        sample = Sample(
            prompt_id=prompt["id"], split=prompt["split"], api_area=prompt["api_area"],
            model=model, sample_index=index, temperature=temperature, seed=seed,
            prompt_sha256=hashlib.sha256(prompt["task"].encode()).hexdigest(),
            raw_response="", swift_source="", provider=None, finish_reason=None,
            usage={}, generated_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(sample), indent=1) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(prog="runner.generate")
    ap.add_argument("--limit", type=int, help="cap samples per prompt (default: pins)")
    ap.add_argument("--models", help="comma-separated subset of the roster")
    ap.add_argument("--prompts", help="comma-separated prompt ids")
    ap.add_argument("--workers", type=int, help="default: generation.workers in pins")
    ap.add_argument("--dry-run", action="store_true", help="plan only, no calls")
    args = ap.parse_args()

    pins = load_pins()
    key = require(pins["gateway"]["api_key_env"])
    corpus = load_corpus()
    if args.prompts:
        wanted = set(args.prompts.split(","))
        corpus = [p for p in corpus if p["id"] in wanted]
    models = args.models.split(",") if args.models else pins["models"]["roster"]
    k = args.limit or int(pins["generation"]["samples_per_prompt"])
    workers = args.workers or int(pins["generation"].get("workers", 4))

    jobs = [(p, m, i) for m in models for p in corpus for i in range(k)]
    todo = [j for j in jobs if not sample_path(j[1], j[0]["id"], j[2]).is_file()]
    print(f"models {len(models)}  prompts {len(corpus)}  k {k}")
    print(f"samples {len(jobs)} total, {len(jobs) - len(todo)} already on disk, {len(todo)} to generate")
    if args.dry_run or not todo:
        return 0

    done = failed = 0
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(generate_one, pins, key, p, m, i): (p, m, i) for p, m, i in todo}
        for fut in futures.as_completed(futs):
            p, m, i = futs[fut]
            try:
                path = fut.result()
                rec = json.loads(path.read_text())
                if rec.get("error"):
                    failed += 1
                    print(f"  ERR  {m} {p['id']}.{i}: {rec['error'][:80]}")
            except Exception as exc:                      # noqa: BLE001
                failed += 1
                print(f"  ERR  {m} {p['id']}.{i}: {exc}")
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(todo)} ({failed} errored)")

    print(f"\ngenerated {done}, errored {failed} (retained as failures)")
    print(f"samples in {SAMPLES_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
