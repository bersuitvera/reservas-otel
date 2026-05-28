#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_COMMON = [
    "engine_root.json",
    "cluster_health.json",
    "cluster_stats.json",
    "nodes_stats.json",
    "indices_stats.json",
    "indices.json",
    "count.json",
    "templates.json",
    "shards.json",
    "nodes.json",
    "allocation.json",
    "thread_pool.json",
]

REQUIRED_BY_SCENARIO = {
    "escenario_a": [
        "indices_opensearch_otel_v1_apm.json",
        "indices_opensearch_logs_otel_v1.json",
        "indices_opensearch_otel_v2_service_map.json",
        "indices_opensearch_service_map_all.json",
    ],
    "escenario_b": [
        "data_streams.json",
        "indices_elastic_ds_traces.json",
        "indices_elastic_ds_logs.json",
        "indices_elastic_ds_metrics.json",
        "data_streams_elastic_traces.json",
        "data_streams_elastic_logs.json",
        "data_streams_elastic_metrics.json",
    ],
    "escenario_c": [
        "data_streams.json",
        "indices_elastic_traces_apm.json",
        "indices_elastic_metrics_apm.json",
        "indices_elastic_logs_containerlogs.json",
        "indices_elastic_metrics_system.json",
        "indices_elastic_metrics_docker.json",
        "data_streams_elastic_traces_apm.json",
        "data_streams_elastic_metrics_apm.json",
        "data_streams_elastic_logs_containerlogs.json",
        "data_streams_elastic_metrics_system.json",
        "data_streams_elastic_metrics_docker.json",
    ],
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_status(path: Path) -> str:
    status_path = path.with_suffix(path.suffix + ".status")
    if not status_path.exists():
        return "missing"
    return status_path.read_text(encoding="utf-8").strip()


def add(rows: list[dict[str, str]], name: str, result: str, detail: str = "") -> None:
    rows.append({"check": name, "result": result, "detail": detail})


def check_status_files(out_dir: Path, scenario: str, rows: list[dict[str, str]]) -> None:
    for filename in REQUIRED_COMMON + REQUIRED_BY_SCENARIO.get(scenario, []):
        path = out_dir / filename
        status = read_status(path)
        if status == "missing":
            add(rows, f"http_status:{filename}", "FAIL", "missing .status file")
        elif status == "skipped":
            add(rows, f"http_status:{filename}", "SKIP", "not applicable for this scenario")
        elif status.startswith("2"):
            add(rows, f"http_status:{filename}", "PASS", f"HTTP {status}")
        else:
            add(rows, f"http_status:{filename}", "FAIL", f"HTTP {status}")


def check_cluster_health(out_dir: Path, rows: list[dict[str, str]]) -> None:
    data = load_json(out_dir / "cluster_health.json")
    if not isinstance(data, dict):
        add(rows, "cluster_health:parse", "FAIL", "cluster_health.json is not a JSON object")
        return

    status = str(data.get("status", "unknown")).lower()
    timed_out = bool(data.get("timed_out", False))
    nodes = data.get("number_of_nodes", "unknown")
    active_shards = data.get("active_shards", "unknown")
    unassigned = data.get("unassigned_shards", "unknown")

    if status in {"green", "yellow"}:
        add(rows, "cluster_health:status", "PASS", status)
    else:
        add(rows, "cluster_health:status", "FAIL", status)

    add(rows, "cluster_health:timed_out", "FAIL" if timed_out else "PASS", str(timed_out).lower())
    add(rows, "cluster_health:nodes", "PASS" if isinstance(nodes, int) and nodes >= 1 else "WARN", str(nodes))
    add(rows, "cluster_health:active_shards", "PASS" if isinstance(active_shards, int) and active_shards >= 1 else "WARN", str(active_shards))
    add(rows, "cluster_health:unassigned_shards", "WARN" if isinstance(unassigned, int) and unassigned > 0 else "PASS", str(unassigned))


def check_indices(out_dir: Path, rows: list[dict[str, str]]) -> None:
    indices = load_json(out_dir / "indices.json")
    if not isinstance(indices, list):
        add(rows, "indices:parse", "FAIL", "indices.json is not a JSON list")
        return

    add(rows, "indices:count", "PASS" if indices else "WARN", str(len(indices)))

    red = [item.get("index", "") for item in indices if item.get("health") == "red"]
    add(rows, "indices:red_health", "FAIL" if red else "PASS", ",".join(red[:10]))

    telemetry_patterns = ("otel-v1-apm", "logs-otel-v1", "otel-v2-apm-service-map")
    telemetry = [
        item.get("index", "")
        for item in indices
        if any(pattern in str(item.get("index", "")) for pattern in telemetry_patterns)
    ]
    add(rows, "indices:scenario_a_telemetry", "PASS" if telemetry else "WARN", str(len(telemetry)))


def write_outputs(out_dir: Path, rows: list[dict[str, str]]) -> None:
    csv_path = out_dir / "backend_health_summary.csv"
    json_path = out_dir / "backend_health_summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["check", "result", "detail"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "passes": sum(1 for row in rows if row["result"] == "PASS"),
        "warnings": sum(1 for row in rows if row["result"] == "WARN"),
        "failures": sum(1 for row in rows if row["result"] == "FAIL"),
        "skipped": sum(1 for row in rows if row["result"] == "SKIP"),
        "checks": rows,
    }
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] Generado {csv_path}")
    print(f"[OK] Generado {json_path}")


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Uso: summarize_backend_health.py OUT_DIR [SCENARIO]", file=sys.stderr)
        return 2

    out_dir = Path(sys.argv[1])
    scenario = sys.argv[2] if len(sys.argv) == 3 else "unknown"
    rows: list[dict[str, str]] = []

    check_status_files(out_dir, scenario, rows)
    check_cluster_health(out_dir, rows)
    check_indices(out_dir, rows)
    write_outputs(out_dir, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
