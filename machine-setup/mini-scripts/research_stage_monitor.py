#!/usr/bin/env python3
"""Independent liveness monitor for the content research-stage ledger."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LEDGER = Path("~/.hermes/logs/research-served.jsonl").expanduser()


def _parse_ts(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def evaluate(
    records: list[dict[str, Any]],
    *,
    now: float,
    lookback_hours: float,
    min_served_rate: float,
    max_degraded_rate: float,
) -> dict[str, Any]:
    cutoff = now - lookback_hours * 3600
    recent = [r for r in records if (_parse_ts(str(r.get("ts", ""))) or 0) >= cutoff]
    enabled = [r for r in recent if r.get("enabled") and r.get("outcome") != "fetch-only"]
    served = [r for r in enabled if r.get("served")]
    degraded = [r for r in enabled if r.get("degraded")]
    if not recent:
        status = "not-observed"
    elif not enabled:
        status = "disabled-or-smoke-only"
    else:
        rate = len(served) / len(enabled)
        degraded_rate = len(degraded) / len(enabled)
        status = (
            "healthy"
            if rate >= min_served_rate and degraded_rate <= max_degraded_rate
            else "degraded"
        )
    return {
        "status": status,
        "lookback_hours": lookback_hours,
        "recent_receipts": len(recent),
        "enabled_attempts": len(enabled),
        "served_attempts": len(served),
        "degraded_attempts": len(degraded),
        "served_rate": (round(len(served) / len(enabled), 4) if enabled else None),
        "degraded_rate": (round(len(degraded) / len(enabled), 4) if enabled else None),
        "max_degraded_rate": max_degraded_rate,
        "last_outcome": recent[-1].get("outcome") if recent else None,
        "last_task_id": recent[-1].get("task_id") if recent else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--lookback-hours", type=float, default=48)
    parser.add_argument("--min-served-rate", type=float, default=0.8)
    parser.add_argument("--max-degraded-rate", type=float, default=0.5)
    parser.add_argument("--now", help="ISO8601 test override")
    args = parser.parse_args(argv)
    now = _parse_ts(args.now) if args.now else time.time()
    if now is None:
        print(json.dumps({"status": "error", "error": "invalid --now"}))
        return 2
    result = evaluate(
        read_records(Path(args.ledger).expanduser()),
        now=now,
        lookback_hours=max(0.1, args.lookback_hours),
        min_served_rate=max(0.0, min(args.min_served_rate, 1.0)),
        max_degraded_rate=max(0.0, min(args.max_degraded_rate, 1.0)),
    )
    result["checked_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"healthy", "disabled-or-smoke-only"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
