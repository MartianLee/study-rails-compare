"""Shared plumbing for the harness: compose control, readiness, container memory."""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# service -> published host port. Host ports are used for readiness and
# correctness checks only. Throughput is always measured from inside the
# network, by the loadgen container.
STACKS = {
    "rails":       {"port": 3001, "runtime": "Ruby",   "variant": "full", "label": "Rails 8 + Active Record"},
    "rails-bare":  {"port": 3002, "runtime": "Ruby",   "variant": "bare", "label": "Rack + raw SQL"},
    "node":        {"port": 3003, "runtime": "Node",   "variant": "full", "label": "Express + Sequelize"},
    "node-bare":   {"port": 3004, "runtime": "Node",   "variant": "bare", "label": "node:http + raw SQL"},
    "python":      {"port": 3005, "runtime": "Python", "variant": "full", "label": "Django + Django ORM"},
    "python-bare": {"port": 3006, "runtime": "Python", "variant": "bare", "label": "WSGI + raw SQL"},
    "go":          {"port": 3007, "runtime": "Go",     "variant": "full", "label": "Gin + GORM"},
    "go-bare":     {"port": 3008, "runtime": "Go",     "variant": "bare", "label": "net/http + database/sql"},
}
PAIRS = [("Ruby", "rails", "rails-bare"), ("Node", "node", "node-bare"),
         ("Python", "python", "python-bare"), ("Go", "go", "go-bare")]


def sh(cmd, env=None, check=False, capture=True):
    e = dict(os.environ)
    if env:
        e.update({k: str(v) for k, v in env.items()})
    return subprocess.run(cmd, shell=True, cwd=ROOT, env=e, check=check,
                          capture_output=capture, text=True)


def compose(args, env=None, check=False):
    return sh(f"docker compose {args}", env=env, check=check)


def mysql(sql, db="blogbench"):
    q = sql.replace("'", "'\\''")
    r = sh(f"docker compose exec -T mysql mysql -uroot -proot -N -B {db} -e '{q}' 2>/dev/null")
    return [line.split("\t") for line in r.stdout.strip().splitlines() if line]


def get(port, path, timeout=10):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return r.status, json.loads(r.read())


def post(port, path, payload, timeout=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def start(service, env=None, timeout=180):
    compose(f"up -d --force-recreate {service}", env=env)
    port = STACKS[service]["port"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if get(port, "/healthz", timeout=2)[0] == 200:
                return round((time.time() - t0) * 1000)
        except Exception:
            pass
        time.sleep(0.15)
    raise RuntimeError(f"{service} did not become ready in {timeout}s\n"
                       + compose(f"logs --tail 40 {service}").stdout)


def stop(service):
    compose(f"stop -t 10 {service}")
    compose(f"rm -f {service}")


def container_id(service):
    return compose(f"ps -q {service}").stdout.strip()


def mem_mb(service):
    """Read the container's memory straight from its cgroup.

    `docker stats` prints a pre-formatted string that is easy to misparse, so
    this goes to the source instead:

      working_set = memory.current - inactive_file   (what Kubernetes evicts on)
      anon        = memory.stat's anon               (heap: the app's own pages)
      rss         = sum of /proc/*/statm resident    (per-process view)
    """
    cid = container_id(service)
    if not cid:
        return {}
    out = {}
    r = sh(f"docker exec {cid} sh -c 'cat /sys/fs/cgroup/memory.current; echo ---; "
           f"cat /sys/fs/cgroup/memory.stat'")
    try:
        head, _, tail = r.stdout.partition("---")
        current = int(head.strip())
        stat = {}
        for line in tail.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                stat[parts[0]] = int(parts[1])
        out["working_set_mb"] = round((current - stat.get("inactive_file", 0)) / 1048576.0, 1)
        out["container_mb"] = out["working_set_mb"]
        out["anon_mb"] = round(stat.get("anon", 0) / 1048576.0, 1)
        out["file_mb"] = round((stat.get("active_file", 0) + stat.get("inactive_file", 0)) / 1048576.0, 1)
    except Exception:
        pass
    ps2 = sh(f"docker exec {cid} sh -c 'ls -d /proc/[0-9]* | wc -l'")
    try:
        out["procs"] = int(ps2.stdout.strip())
    except Exception:
        pass
    return out


def db_cores(seconds=2.0):
    """MySQL's CPU usage right now, in cores. Used to wait for InnoDB to finish
    purging after the write test before measuring anything else — a background
    purge left running is a bottleneck the next stack would be charged for."""
    cid = container_id("mysql")
    if not cid:
        return 0.0
    def usec():
        r = sh(f"docker exec {cid} sh -c 'head -1 /sys/fs/cgroup/cpu.stat'")
        try:
            return int(r.stdout.split()[1])
        except Exception:
            return 0
    a = usec()
    time.sleep(seconds)
    return (usec() - a) / 1e6 / seconds


def wait_db_idle(threshold=0.25, limit=120):
    t0 = time.time()
    while time.time() - t0 < limit:
        if db_cores(1.5) < threshold:
            return round(time.time() - t0, 1)
    return round(time.time() - t0, 1)


def loadgen(target, path, conc, duration, warmup=3, method="GET", body=None):
    args = (f"-url http://{target}:3000{path} -c {conc} -d {duration}s -warmup {warmup}s "
            f"-method {method}")
    if body:
        args += f" -body '{body}'"
    r = compose(f"run --rm -T loadgen {args}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"loadgen failed:\nSTDOUT{r.stdout}\nSTDERR{r.stderr}")
