#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


def load_result(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data.get("data", {}).get("result", []) if isinstance(data, dict) else []


def value_sum(path: Path) -> float:
    total = 0.0
    for item in load_result(path):
        value = item.get("value", [None, 0])[1]
        try:
            total += float(value)
        except (TypeError, ValueError):
            pass
    return total


def series_count(path: Path) -> int:
    return len(load_result(path))


def add(rows: list[dict[str, str]], check: str, result: str, detail: str) -> None:
    rows.append({"check": check, "result": result, "detail": detail})


def check_up(out_dir: Path, rows: list[dict[str, str]]) -> None:
    for path in sorted(out_dir.glob("up_job__*.json")):
        values = []
        for item in load_result(path):
            try:
                values.append(float(item.get("value", [None, 0])[1]))
            except (TypeError, ValueError):
                values.append(0.0)

        if values and all(value == 1.0 for value in values):
            add(rows, f"target:{path.stem}", "PASS", f"series={len(values)} up=1")
        else:
            add(rows, f"target:{path.stem}", "FAIL", f"values={values}")


def check_zero_sum(out_dir: Path, rows: list[dict[str, str]], pattern: str, label: str) -> None:
    matches = sorted(out_dir.glob(pattern))
    if not matches:
        add(rows, label, "WARN", "metric file not found")
        return

    for path in matches:
        total = value_sum(path)
        count = series_count(path)
        if total == 0.0:
            add(rows, f"{label}:{path.stem}", "PASS", f"sum=0 series={count}")
        else:
            add(rows, f"{label}:{path.stem}", "FAIL", f"sum={total} series={count}")


def check_positive_series(out_dir: Path, rows: list[dict[str, str]], filename: str, label: str) -> None:
    path = out_dir / filename
    count = series_count(path)
    total = value_sum(path)
    if count > 0 and total > 0:
        add(rows, label, "PASS", f"sum={total:g} series={count}")
    else:
        add(rows, label, "WARN", f"sum={total:g} series={count}")


def write_outputs(out_dir: Path, rows: list[dict[str, str]]) -> None:
    csv_path = out_dir / "prometheus_summary.csv"
    json_path = out_dir / "prometheus_summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["check", "result", "detail"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "passes": sum(1 for row in rows if row["result"] == "PASS"),
        "warnings": sum(1 for row in rows if row["result"] == "WARN"),
        "failures": sum(1 for row in rows if row["result"] == "FAIL"),
        "checks": rows,
    }
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] Generado {csv_path}")
    print(f"[OK] Generado {json_path}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: summarize_prometheus_snapshot.py PROMETHEUS_OUT_DIR", file=sys.stderr)
        return 2

    out_dir = Path(sys.argv[1])
    rows: list[dict[str, str]] = []

    check_up(out_dir, rows)
    check_zero_sum(out_dir, rows, "otelcol_exporter_send_failed_*_total_.json", "otelcol_exporter_send_failed")
    check_zero_sum(out_dir, rows, "*recordsWriteFailed_total_.json", "dataprepper_records_write_failed")
    check_zero_sum(out_dir, rows, "otelcol_exporter_queue_size_.json", "otelcol_exporter_queue")
    check_zero_sum(out_dir, rows, "entry_pipeline_BlockingBuffer_recordsInBuffer_.json", "dataprepper_entry_buffer")
    check_zero_sum(out_dir, rows, "entry_pipeline_BlockingBuffer_recordsInFlight_.json", "dataprepper_entry_in_flight")
    check_zero_sum(out_dir, rows, "elasticsearch_thread_pool_rejected_count_.json", "opensearch_thread_pool_rejected")

    check_positive_series(out_dir, rows, "otelcol_receiver_accepted_spans_total_.json", "otelcol_received_spans")
    check_positive_series(out_dir, rows, "otelcol_receiver_accepted_log_records_total_.json", "otelcol_received_logs")
    check_positive_series(out_dir, rows, "traces_raw_pipeline_opensearch_recordsIn_total_.json", "dataprepper_traces_to_opensearch")
    check_positive_series(out_dir, rows, "logs_pipeline_opensearch_recordsIn_total_.json", "dataprepper_logs_to_opensearch")
    check_positive_series(out_dir, rows, "elasticsearch_indices_docs_.json", "opensearch_indexed_docs")

    write_outputs(out_dir, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
