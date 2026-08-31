#!/usr/bin/env python3
"""Do Puma threads help when the database is real?

The usual demonstration that they do not is run against a local SQLite file,
where a query returns before the thread has a chance to yield — so there is no
wait to overlap and of course nothing happens. Against MySQL over a socket
there is a wait. This holds the CPU limit, the process count and the load
concurrency fixed and changes only the thread count.

    python3 harness/threads_probe.py   # -> results/threads.json
"""
import json

from common import ROOT, loadgen, mem_mb, start, stop

import os

THREADS = [1, 2, 3, 5, 10]
PATH = "/api/posts?page=3"
CONC = int(os.environ.get("PROBE_CONC", "8"))
CPUS = os.environ.get("PROBE_CPUS", "1.0")


def sample(service, n):
    env = {"APP_CPUS": CPUS, "APP_MEM": "1g", "WEB_CONCURRENCY": "1",
           "APP_THREADS": str(n), "DB_POOL": str(max(2, n + 2)), "RAILS_YJIT": "1"}
    start(service, env=env)
    try:
        loadgen(service, PATH, CONC, 3, warmup=0)
        from common import sh, compose

        def cpu():
            cid = compose(f"ps -q {service}").stdout.strip()
            return int(sh(f"docker exec {cid} sh -c 'head -1 /sys/fs/cgroup/cpu.stat'"
                          ).stdout.split()[1])
        c0 = cpu()
        r = loadgen(service, PATH, CONC, 10, warmup=0)
        c1 = cpu()
        m = mem_mb(service)
        return {"threads": n, "rps": round(r["rps"], 1), "p50_ms": r["p50_ms"],
                "p99_ms": r["p99_ms"],
                "cpu_ms_per_req": round((c1 - c0) / 1000.0 / r["completed"], 4),
                "cores_used": round((c1 - c0) / 1e6 / r["duration_s"], 3),
                "mem_mb": m.get("working_set_mb")}
    finally:
        stop(service)


def main():
    out = {"path": PATH, "concurrency": CONC, "cpu_limit": float(CPUS), "workers": 1, "stacks": {}}
    for service in ("rails", "rails-bare"):
        rows = [sample(service, n) for n in THREADS]
        out["stacks"][service] = rows
        base = rows[0]
        print(f"\n{service} — {CPUS} CPU, 1 process, load concurrency {CONC}")
        print(f"{'threads':>8}{'rps':>9}{'vs 1 thread':>13}{'cores used':>12}"
              f"{'CPU ms/req':>12}{'p50':>8}{'p99':>9}{'mem MB':>9}")
        for r in rows:
            print(f"{r['threads']:>8}{r['rps']:>9.0f}{r['rps'] / base['rps']:>12.2f}x"
                  f"{r['cores_used']:>12.2f}{r['cpu_ms_per_req']:>12.3f}"
                  f"{r['p50_ms']:>8.2f}{r['p99_ms']:>9.2f}{r['mem_mb']:>9.1f}")
    with open(f"{ROOT}/results/threads-{CPUS.replace('.', '')}cpu-c{CONC}.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
