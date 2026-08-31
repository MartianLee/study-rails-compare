#!/usr/bin/env python3
"""How much memory does an extra Puma worker actually cost on Linux?

The naive answer is "one worker's RSS each". That is wrong, because Puma's
`preload_app!` forks after loading the app, and Linux hands the children
copy-on-write pages. This measures the real cost by scaling one Rails
container from 1 to 8 workers under identical load and reading the cgroup.

    python3 harness/workers_probe.py   # -> results/workers.json

Run it on its own; it needs more CPU than the main campaign's app limit.
"""
import json
import time

from common import ROOT, compose, loadgen, mem_mb, start, stop

WORKERS = [1, 2, 4, 8]
SERVICE = "rails"
PATH = "/api/posts?page=3"


def main():
    out = {"service": SERVICE, "path": PATH, "samples": []}
    for w in WORKERS:
        env = {"APP_CPUS": "6.0", "APP_MEM": "4g", "WEB_CONCURRENCY": str(w),
               "APP_THREADS": "5", "DB_POOL": "10", "RAILS_YJIT": "1"}
        boot = start(SERVICE, env=env)
        try:
            time.sleep(2)
            before = mem_mb(SERVICE)
            loadgen(SERVICE, PATH, max(8, w * 8), 8, warmup=4)
            after = mem_mb(SERVICE)
            res = loadgen(SERVICE, PATH, max(8, w * 8), 10, warmup=0)
            peak = mem_mb(SERVICE)
            out["samples"].append({
                "workers": w, "boot_ms": boot, "procs": peak.get("procs"),
                "mem_boot_mb": before.get("working_set_mb"),
                "mem_warm_mb": after.get("working_set_mb"),
                "mem_peak_mb": peak.get("working_set_mb"),
                "anon_mb": peak.get("anon_mb"),
                "rps": res["rps"], "p50_ms": res["p50_ms"], "p99_ms": res["p99_ms"],
            })
            print(json.dumps(out["samples"][-1]), flush=True)
        finally:
            stop(SERVICE)

    base = out["samples"][0]["mem_peak_mb"]
    for s in out["samples"]:
        s["naive_estimate_mb"] = round(base * s["workers"], 1)
        s["overestimate_x"] = round(s["naive_estimate_mb"] / s["mem_peak_mb"], 2)
        s["marginal_mb_per_worker"] = (
            round((s["mem_peak_mb"] - base) / (s["workers"] - 1), 1) if s["workers"] > 1 else None)
    with open(f"{ROOT}/results/workers.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nworkers  actual  naive(workers x 1-worker)  overestimate  marginal/worker  rps")
    for s in out["samples"]:
        print(f"{s['workers']:>7}  {s['mem_peak_mb']:>6.1f}  {s['naive_estimate_mb']:>24.1f}  "
              f"{s['overestimate_x']:>11}x  {str(s['marginal_mb_per_worker']):>15}  {s['rps']:>8.1f}")


if __name__ == "__main__":
    main()
