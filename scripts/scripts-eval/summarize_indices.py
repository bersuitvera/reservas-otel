#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text or text == "-":
        return 0.0
    match = re.search(r"[0-9.]+", text)
    return float(match.group(0)) if match else 0.0


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: summarize_indices.py OUT_DIR", file=sys.stderr)
        return 2

    out_dir = Path(sys.argv[1])
    indices_path = out_dir / "indices.json"
    summary_path = out_dir / "indices_summary.csv"
    total_path = out_dir / "indices_total.csv"

    indices = load_json_list(indices_path)

    rows = []
    for item in indices:
        index_name = item.get("index") or item.get("idx") or ""
        docs_count = int(parse_number(item.get("docs.count") or item.get("docsCount")))
        store_mb = parse_number(item.get("store.size") or item.get("storeSize"))

        rows.append(
            {
                "index": index_name,
                "health": item.get("health", ""),
                "status": item.get("status", ""),
                "docs_count": docs_count,
                "store_size_mb": store_mb,
                "pri_store_size_mb": parse_number(item.get("pri.store.size")),
            }
        )

    rows.sort(key=lambda r: r["index"])

    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "index",
                "health",
                "status",
                "docs_count",
                "store_size_mb",
                "pri_store_size_mb",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    total_docs = sum(int(row["docs_count"]) for row in rows)
    total_store_mb = sum(float(row["store_size_mb"]) for row in rows)

    avg_kb_per_doc = 0.0
    if total_docs > 0:
        avg_kb_per_doc = (total_store_mb * 1024) / total_docs

    total_row = {
        "index_count": len(rows),
        "total_docs_count": total_docs,
        "total_store_size_mb": round(total_store_mb, 4),
        "avg_kb_per_doc": round(avg_kb_per_doc, 4),
    }

    with total_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "index_count",
                "total_docs_count",
                "total_store_size_mb",
                "avg_kb_per_doc",
            ],
        )
        writer.writeheader()
        writer.writerow(total_row)

    print(f"[OK] Generado {summary_path}")
    print(f"[OK] Generado {total_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
