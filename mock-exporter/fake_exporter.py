import time
import random
from prometheus_client import start_http_server, Gauge
from prometheus_client.core import CollectorRegistry

registry = CollectorRegistry()

cpu_usage = Gauge(
    'container_cpu_usage_seconds_total',
    'CPU usage per container',
    ['namespace', 'pod', 'node'],
    registry=registry
)

mem_usage = Gauge(
    'container_memory_working_set_bytes',
    'Memory usage per container',
    ['namespace', 'pod', 'node'],
    registry=registry
)

cpu_requests = Gauge(
    'kube_pod_container_resource_requests',
    'CPU requests per container',
    ['namespace', 'pod', 'node', 'resource'],
    registry=registry
)

PODS = [
    ("billing",       "api-7d9f",      "worker-node-1", 0.043, 0.200, 512),
    ("billing",       "worker-2",      "worker-node-1", 0.120, 0.500, 1024),
    ("billing",       "db-replica",    "worker-node-3", 0.180, 0.500, 2048),
    ("ml-inference",  "gpu-0",         "worker-node-1", 0.410, 2.000, 4096),
    ("ml-inference",  "gpu-1",         "worker-node-2", 0.380, 2.000, 4096),
    ("api-gateway",   "proxy",         "worker-node-2", 0.055, 0.250, 256),
    ("api-gateway",   "auth",          "worker-node-3", 0.030, 0.250, 256),
    ("monitoring",    "prometheus",    "worker-node-1", 0.008, 0.100, 512),
    ("logging",       "elasticsearch", "worker-node-2", 0.290, 1.000, 2048),
    ("logging",       "kibana",        "worker-node-3", 0.070, 0.500, 512),
]

cpu_counters = {pod[1]: 0.0 for pod in PODS}

def update_metrics():
    for ns, pod, node, cpu_base, cpu_req, mem_base in PODS:
        jitter = random.uniform(-0.15, 0.15)
        cpu_val = max(0.001, cpu_base * (1 + jitter))
        cpu_counters[pod] += cpu_val
        cpu_usage.labels(namespace=ns, pod=pod, node=node).set(cpu_counters[pod])
        mem_bytes = int(mem_base * 1024 * 1024 * random.uniform(0.95, 1.05))
        mem_usage.labels(namespace=ns, pod=pod, node=node).set(mem_bytes)
        cpu_requests.labels(namespace=ns, pod=pod, node=node, resource="cpu").set(cpu_req)

if __name__ == "__main__":
    start_http_server(9100, registry=registry)
    print("Fake Prometheus exporter running on :9100/metrics")
    while True:
        update_metrics()
        time.sleep(15)
