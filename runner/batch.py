"""Generate samples through the gateway's async batch API at ~50% cost.

    python3 -m runner.batch submit    # queue work for batch-capable models
    python3 -m runner.batch status    # check queued batches
    python3 -m runner.batch collect   # write finished results as samples

Only some roster models offer a `:batch` variant; the rest must go through
runner.generate. Both paths write identical sample files, so scoring cannot
tell them apart — the model, prompt, temperature and seed are the same, and
only the delivery mechanism differs.

Batches carry a 24-hour completion window. That is the trade: half the cost
for turnaround measured in hours rather than seconds. Submit and status are
verified against the live API; the result-parsing branch in collect handles
both an inline list and a URL-to-JSONL, whichever the gateway returns, and
should be re-checked the first time a real batch completes.

The request body is order-sensitive — the gateway streams it and requires
`endpoint` and `model` before `requests` — so it is assembled by hand rather
than dumped from a dict whose key order is incidental.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from groundtruth.sdk import REPO_ROOT, load_pins
from runner.env import require
from runner.generate import (SYSTEM, SAMPLES_DIR, Sample, extract_swift,
                             load_corpus, sample_path)

BATCH_ROOT = "https://openrouter.ai/api/beta/batches"
STATE_DIR = REPO_ROOT / "build" / "batches"
MAX_PER_BATCH = 400
TERMINAL = {"completed", "failed", "expired", "cancelled"}


def _api(method: str, path: str = "", body: bytes | None = None) -> dict:
    key = require("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BATCH_ROOT + path, data=body, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: "
                           f"{exc.read()[:400].decode('utf-8','replace')}") from exc


def batch_capable(pins: dict) -> list[str]:
    """Roster models that advertise a :batch variant on the gateway."""
    key = require("OPENROUTER_API_KEY")
    req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        ids = {m["id"] for m in json.loads(resp.read())["data"]}
    return [m for m in pins["models"]["roster"] if f"{m}:batch" in ids]


def submit(args) -> int:
    pins = load_pins()
    corpus = load_corpus()
    k = args.limit or int(pins["generation"]["samples_per_prompt"])
    temperature = float(pins["generation"]["temperature"])
    max_tokens = int(pins["generation"].get("max_tokens", 12000))
    models = args.models.split(",") if args.models else batch_capable(pins)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    for model in models:
        pending = [(p, i) for p in corpus for i in range(k)
                   if not sample_path(model, p["id"], i).is_file()]
        if not pending:
            print(f"{model}: nothing to do")
            continue
        for chunk_no in range(0, len(pending), MAX_PER_BATCH):
            chunk = pending[chunk_no:chunk_no + MAX_PER_BATCH]
            reqs = [json.dumps({
                # custom_id maps the result back to a sample slot.
                "custom_id": f"{p['id']}|{i}",
                "body": {
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": p["task"]}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "seed": i,
                },
            }) for p, i in chunk]
            # Order matters: endpoint and model must precede requests.
            payload = ('{"endpoint":"/v1/chat/completions",'
                       f'"model":{json.dumps(model + ":batch")},'
                       '"requests":[' + ",".join(reqs) + ']}')
            created = _api("POST", body=payload.encode())
            state = STATE_DIR / f"{created['id']}.json"
            state.write_text(json.dumps({
                "batch_id": created["id"], "model": model,
                "count": len(chunk), "status": created.get("status"),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }, indent=1) + "\n")
            print(f"{model}: queued {len(chunk)} -> {created['id']} "
                  f"({created.get('status')})")
    return 0


def _states() -> list[Path]:
    return sorted(STATE_DIR.glob("*.json")) if STATE_DIR.is_dir() else []


def status(args) -> int:
    files = _states()
    if not files:
        print("no batches queued — run: python3 -m runner.batch submit")
        return 0
    print(f"{'batch':40} {'model':30} {'status':12} {'done/total'}")
    for f in files:
        st = json.loads(f.read_text())
        try:
            live = _api("GET", f"/{st['batch_id']}")
        except RuntimeError as exc:
            print(f"{st['batch_id']:40} {st['model']:30} ERROR {exc}")
            continue
        counts = live.get("request_counts") or {}
        st["status"] = live.get("status")
        f.write_text(json.dumps(st, indent=1) + "\n")
        print(f"{st['batch_id']:40} {st['model']:30} {live.get('status',''):12} "
              f"{counts.get('completed',0)}/{counts.get('total',0)}"
              + (f"  failed={counts['failed']}" if counts.get("failed") else ""))
    return 0


def collect(args) -> int:
    prompts = {p["id"]: p for p in load_corpus()}
    written = skipped = 0
    for f in _states():
        st = json.loads(f.read_text())
        live = _api("GET", f"/{st['batch_id']}")
        if live.get("status") not in TERMINAL:
            print(f"{st['batch_id']}: {live.get('status')} — not ready")
            continue
        results = live.get("results")
        # Shape is defensive: the gateway may inline results or hand back a
        # URL to a JSONL file. Verified against a live completed batch before
        # relying on either branch — see the note in the module docstring.
        if isinstance(results, str):                 # a URL to fetch
            with urllib.request.urlopen(results, timeout=300) as resp:
                body = resp.read().decode("utf-8", "replace")
            results = [json.loads(line) for line in body.splitlines() if line.strip()]
        if not results:
            print(f"{st['batch_id']}: terminal but no results ({live.get('error')})")
            continue

        for item in results:
            cid = item.get("custom_id") or ""
            if "|" not in cid:
                continue
            pid, idx = cid.rsplit("|", 1)
            prompt = prompts.get(pid)
            if prompt is None:
                continue
            path = sample_path(st["model"], pid, int(idx))
            if path.is_file():
                skipped += 1
                continue
            resp = item.get("response") or {}
            payload = resp.get("body") or resp
            choice = (payload.get("choices") or [{}])[0]
            raw = (choice.get("message") or {}).get("content") or ""
            err = item.get("error") or payload.get("error")
            finish = choice.get("finish_reason")
            if not err and finish == "length" and not raw.strip():
                err = "truncated before any output (finish_reason=length)"
            sample = Sample(
                prompt_id=pid, split=prompt["split"], api_area=prompt["api_area"],
                model=st["model"], sample_index=int(idx),
                temperature=float(load_pins()["generation"]["temperature"]),
                seed=int(idx),
                prompt_sha256=hashlib.sha256(prompt["task"].encode()).hexdigest(),
                raw_response=raw, swift_source=extract_swift(raw),
                provider=payload.get("provider"), finish_reason=finish,
                usage=payload.get("usage") or {},
                generated_at=datetime.now(timezone.utc).isoformat(),
                error=json.dumps(err)[:300] if err else None,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(vars(sample), indent=1) + "\n")
            written += 1
        print(f"{st['batch_id']}: collected {len(results)} result(s)")
    print(f"\nwrote {written} samples, skipped {skipped} already present")
    print(f"samples in {SAMPLES_DIR.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="runner.batch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit"); s.set_defaults(fn=submit)
    s.add_argument("--models"); s.add_argument("--limit", type=int)
    for name, fn in (("status", status), ("collect", collect)):
        q = sub.add_parser(name); q.set_defaults(fn=fn)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
