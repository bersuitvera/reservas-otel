#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any


UNIT_TO_MIB = {
    "B": 1 / (1024 * 1024),
    "kB": 1000 / (1024 * 1024),
    "KB": 1000 / (1024 * 1024),
    "KiB": 1 / 1024,
    "MB": 1000 * 1000 / (1024 * 1024),
    "MiB": 1,
    "GB": 1000 * 1000 * 1000 / (1024 * 1024),
    "GiB": 1024,
    "TB": 1000 * 1000 * 1000 * 1000 / (1024 * 1024),
    "TiB": 1024 * 1024,
}


def parse_percent(value: str | None) -> float:
    if not value:
        return 0.0
    return float(value.strip().replace("%", "") or 0)


def parse_memory_used_mib(mem_usage: str | None) -> float:
    """
    Docker suele devolver: '35.42MiB / 7.714GiB'
    """
    if not mem_usage:
        return 0.0

    used = mem_usage.split("/")[0].strip()
    match = re.match(r"(?P<num>[0-9.]+)\s*(?P<unit>[A-Za-z]+)", used)
    if not match:
        return 0.0

    num = float(match.group("num"))
    unit = match.group("unit")
    return num * UNIT_TO_MIB.get(unit, 0.0)


def clean_name(stats: dict[str, Any]) -> str:
    return stats.get("Name") or stats.get("Container") or "unknown"


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: summarize_docker_stats.py docker_stats_raw.jsonl OUT_DIR", file=sys.stderr)
        return 2

    raw_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    samples_path = out_dir / "docker_stats_samples.csv"
    summary_path = out_dir / "docker_stats_summary.csv"

    rows: list[dict[str, Any]] = []

    if not raw_path.exists() or raw_path.stat().st_size == 0:
        print(f"[WARN] Sin datos en {raw_path}", file=sys.stderr)
        return 0

    with raw_path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                stats = item["stats"]
            except Exception as exc:
                print(f"[WARN] Línea inválida {line_number}: {exc}", file=sys.stderr)
                continue

            row = {
                "ts": item.get("ts", ""),
                "container": clean_name(stats),
                "cpu_pct": parse_percent(stats.get("CPUPerc")),
                "mem_used_mib": parse_memory_used_mib(stats.get("MemUsage")),
                "mem_pct": parse_percent(stats.get("MemPerc")),
                "net_io": stats.get("NetIO", ""),
                "block_io": stats.get("BlockIO", ""),
                "pids": stats.get("PIDs", ""),
            }
            rows.append(row)

    with samples_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "ts",
                "container",
                "cpu_pct",
                "mem_used_mib",
                "mem_pct",
                "net_io",
                "block_io",
                "pids",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["container"], []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for container, items in sorted(grouped.items()):
        cpu_values = [float(item["cpu_pct"]) for item in items]
        mem_values = [float(item["mem_used_mib"]) for item in items]
        mem_pct_values = [float(item["mem_pct"]) for item in items]

        summary_rows.append(
            {
                "container": container,
                "samples": len(items),
                "cpu_avg_pct": round(statistics.mean(cpu_values), 4) if cpu_values else 0,
                "cpu_max_pct": round(max(cpu_values), 4) if cpu_values else 0,
                "mem_avg_mib": round(statistics.mean(mem_values), 4) if mem_values else 0,
                "mem_max_mib": round(max(mem_values), 4) if mem_values else 0,
                "mem_pct_avg": round(statistics.mean(mem_pct_values), 4) if mem_pct_values else 0,
                "mem_pct_max": round(max(mem_pct_values), 4) if mem_pct_values else 0,
            }
        )

    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "container",
                "samples",
                "cpu_avg_pct",
                "cpu_max_pct",
                "mem_avg_mib",
                "mem_max_mib",
                "mem_pct_avg",
                "mem_pct_max",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"[OK] Generado {samples_path}")
    print(f"[OK] Generado {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
