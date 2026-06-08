import httpx
import csv
import os
import time
import duckdb
from datetime import datetime, timezone

PROMETHEUS_URL = "http://localhost:9100"
CSV_PATH = os.path.join(os.path.dirname(__file__), "../data/raw_container_metrics.csv")
DB_PATH  = os.path.join(os.path.dirname(__file__), "../data/poweraudit.duckdb")

QUERIES = {
    "cpu_usage":   'container_cpu_usage_seconds_total',
    "mem_usage":   'container_memory_working_set_bytes',
    "cpu_request": 'kube_pod_container_resource_requests{resource="cpu"}',
}

def scrape(metric_name: str, promql: str) -> list[dict]:
    resp = httpx.get(
        f"{PROMETHEUS_URL}/metrics",
        timeout=5
    )
    rows = []
    for line in resp.text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if not line.startswith(metric_name.split("{")[0]):
            continue
        # Parse : metric{labels} value
        try:
            if "{" in line:
                label_part = line.split("{")[1].split("}")[0]
                value = float(line.split("} ")[1].split()[0])
                labels = {}
                for kv in label_part.split(","):
                    k, v = kv.split("=")
                    labels[k.strip()] = v.strip().strip('"')
            else:
                labels = {}
                value = float(line.split()[1])
            rows.append({"labels": labels, "value": value})
        except Exception:
            continue
    return rows

def collect_and_write():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    cpu_data    = scrape("container_cpu_usage_seconds_total",    QUERIES["cpu_usage"])
    mem_data    = scrape("container_memory_working_set_bytes",   QUERIES["mem_usage"])
    req_data    = scrape("kube_pod_container_resource_requests", QUERIES["cpu_request"])

    # Index par (namespace, pod)
    cpu_map = {(r["labels"].get("namespace",""), r["labels"].get("pod","")): r["value"] for r in cpu_data}
    mem_map = {(r["labels"].get("namespace",""), r["labels"].get("pod","")): r["value"] for r in mem_data}
    req_map = {(r["labels"].get("namespace",""), r["labels"].get("pod","")): r["value"] for r in req_data}
    node_map= {(r["labels"].get("namespace",""), r["labels"].get("pod","")): r["labels"].get("node","") for r in cpu_data}

    all_keys = set(cpu_map.keys()) | set(mem_map.keys())
    for ns, pod in sorted(all_keys):
        if not ns or not pod:
            continue
        rows.append({
            "namespace":        ns,
            "pod":              pod,
            "node_name":        node_map.get((ns, pod), ""),
            "cpu_usage_cores":  round(cpu_map.get((ns, pod), 0.0), 6),
            "mem_bytes":        int(mem_map.get((ns, pod), 0)),
            "cpu_request_cores":round(req_map.get((ns, pod), 0.0), 6),
            "collected_at":     ts,
        })

    # Écriture CSV
    write_header = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    # Ingestion DuckDB
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_container_metrics AS
        SELECT * FROM read_csv_auto(?) WHERE 1=0
    """, [CSV_PATH])
    con.execute("""
        INSERT INTO raw_container_metrics
        SELECT * FROM read_csv_auto(?)
    """, [CSV_PATH])
    con.close()

    print(f"[{ts}] Collected {len(rows)} pods → CSV + DuckDB")
    for r in rows:
        print(f"  {r['namespace']:15} / {r['pod']:15} → {r['cpu_usage_cores']:.4f} CPU | {r['mem_bytes']//1024//1024} MB | node: {r['node_name']}")

if __name__ == "__main__":
    print("Prometheus collector started — polling every 15s")
    while True:
        try:
            collect_and_write()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(15)
