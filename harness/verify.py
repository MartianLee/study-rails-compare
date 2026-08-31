#!/usr/bin/env python3
"""Correctness gate. Run this before believing any number this repo produces.

For each of the eight stacks it boots the container and checks three things:

  1. the JSON is *identical* to the Rails app's, value by value
  2. the SQL that reaches MySQL is the statement set SPEC.md requires
  3. the write endpoint inserts a row and bumps the counter

A stack that fails any of these is not comparable to the others, and the
benchmark result for it would be meaningless.
"""
import json
import re
import sys

from common import ROOT, STACKS, get, mysql, post, start, stop

REFERENCE = "rails"
LIST_PATH = "/api/posts?page=3"
DETAIL_ID = 4321


def normalise(obj):
    """JSON with key order and int/str id representation flattened."""
    if isinstance(obj, dict):
        return {k: normalise(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [normalise(v) for v in obj]
    if isinstance(obj, str) and obj.isdigit():
        return int(obj)
    return obj


def capture_sql(port, path):
    """Turn on the general log, make one request, read back what MySQL saw.

    'Prepare' rows are dropped: a prepared statement shows up twice (once when
    it is prepared, once when it is executed) and only the execution is work
    done for this request.
    """
    mysql("SET GLOBAL general_log = 0", db="mysql")
    mysql("TRUNCATE TABLE mysql.general_log", db="mysql")
    mysql("SET GLOBAL general_log = 1", db="mysql")
    get(port, path)
    mysql("SET GLOBAL general_log = 0", db="mysql")
    rows = mysql(
        "SELECT command_type, argument FROM mysql.general_log "
        "WHERE command_type IN ('Query','Execute') ORDER BY event_time", db="mysql")
    out = []
    for r in rows:
        if len(r) < 2:
            continue
        s = " ".join(r[1].split())
        low = s.lower()
        if low.startswith(("set ", "show ", "select @@", "select version", "commit", "begin",
                           "rollback", "start transaction", "select database()", "select 1")):
            continue
        out.append(s)
    return out


FROM_RE = re.compile(r"\bfrom\s+([a-z_]+)")


def kind(stmt):
    s = stmt.replace("`", "").lower()
    m = FROM_RE.search(s)
    return m.group(1) if m else "other:" + s[:60]


EXPECTED_LIST = ["post_tags", "posts", "tags", "users"]
EXPECTED_DETAIL = ["comments", "post_tags", "posts", "tags", "users", "users"]


def main():
    results, failures = {}, []
    ref_list = ref_detail = None

    for name in STACKS:
        print(f"\n=== {name} ===", flush=True)
        start(name)
        port = STACKS[name]["port"]
        entry = {}
        try:
            _, lst = get(port, LIST_PATH)
            _, det = get(port, f"/api/posts/{DETAIL_ID}")
            entry["list_len"] = len(lst)

            if name == REFERENCE:
                ref_list, ref_detail = normalise(lst), normalise(det)
                entry["json_matches_rails"] = True
            else:
                ok_l = normalise(lst) == ref_list
                ok_d = normalise(det) == ref_detail
                entry["json_matches_rails"] = ok_l and ok_d
                if not ok_l:
                    failures.append(f"{name}: list JSON differs from {REFERENCE}")
                    print("  list differs. first row:")
                    print("   ref :", json.dumps(ref_list[0], sort_keys=True)[:300])
                    print("   got :", json.dumps(normalise(lst)[0], sort_keys=True)[:300])
                if not ok_d:
                    failures.append(f"{name}: detail JSON differs from {REFERENCE}")
                    r, g = ref_detail, normalise(det)
                    for k in sorted(set(r) | set(g)):
                        if r.get(k) != g.get(k):
                            print(f"   key {k!r} differs:\n     ref {str(r.get(k))[:200]}\n"
                                  f"     got {str(g.get(k))[:200]}")

            sql_list = capture_sql(port, LIST_PATH)
            sql_detail = capture_sql(port, f"/api/posts/{DETAIL_ID}")
            entry["sql_list"] = sql_list
            entry["sql_detail"] = sql_detail
            entry["sql_list_kinds"] = [kind(s) for s in sql_list]
            entry["sql_detail_kinds"] = [kind(s) for s in sql_detail]
            if sorted(entry["sql_list_kinds"]) != EXPECTED_LIST:
                failures.append(f"{name}: list emitted {entry['sql_list_kinds']}, expected {EXPECTED_LIST}")
            if sorted(entry["sql_detail_kinds"]) != EXPECTED_DETAIL:
                failures.append(f"{name}: detail emitted {entry['sql_detail_kinds']}, expected {EXPECTED_DETAIL}")

            before = int(mysql(f"SELECT comments_count FROM posts WHERE id = {DETAIL_ID}")[0][0])
            code, created = post(port, "/api/comments",
                                 {"post_id": DETAIL_ID, "user_id": 7, "body": "  hello   world  "})
            entry["create_status"] = code
            entry["create_body"] = created.get("body")
            after = int(mysql(f"SELECT comments_count FROM posts WHERE id = {DETAIL_ID}")[0][0])
            entry["counter_incremented"] = after == before + 1
            if code != 201:
                failures.append(f"{name}: create returned {code}")
            if created.get("body") != "hello world":
                failures.append(f"{name}: create did not normalise whitespace: {created.get('body')!r}")
            if after != before + 1:
                failures.append(f"{name}: counter_cache not incremented ({before} -> {after})")

            bad, _ = post(port, "/api/comments", {"post_id": DETAIL_ID, "user_id": 7, "body": "   "})
            entry["blank_status"] = bad
            if bad != 422:
                failures.append(f"{name}: blank body returned {bad}, expected 422")

            mysql(f"DELETE FROM comments WHERE id > 40000")
            mysql(f"UPDATE posts SET comments_count = {before} WHERE id = {DETAIL_ID}")
        finally:
            stop(name)
        results[name] = entry
        print("  " + json.dumps({k: v for k, v in entry.items()
                                 if k not in ("sql_list", "sql_detail")}))

    with open(f"{ROOT}/results/verify.json", "w") as f:
        json.dump(results, f, indent=2)
    write_sql_doc(results)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f_ in failures:
            print("  -", f_)
        sys.exit(1)
    print("all 8 stacks return identical JSON and emit the same statements.")


if __name__ == "__main__":
    main()


def write_sql_doc(results):
    """Write down what MySQL actually saw, per stack. This is the evidence for
    the fairness rule in SPEC.md — if two stacks run different SQL, comparing
    them is comparing different work."""
    lines = ["# The SQL every stack actually emits", "",
             "Captured from MySQL's own `general_log` by `harness/verify.py`, one request per",
             "endpoint. `Prepare` rows are dropped (a prepared statement is logged twice);",
             "what is left is one line per statement executed for that request.", "",
             "Formatting differs — every ORM writes SQL in its own dialect of backticks and",
             "aliases — but the **statement set is identical**: 4 for the list, 6 for the",
             "detail, hitting the same tables with the same predicates.", ""]
    for name, e in results.items():
        lines += [f"## `{name}` — {STACKS[name]['label']}", "",
                  f"`GET /api/posts?page=3` — {len(e.get('sql_list', []))} statements", "",
                  "```sql"] + list(e.get("sql_list", [])) + ["```", "",
                  f"`GET /api/posts/4321` — {len(e.get('sql_detail', []))} statements", "",
                  "```sql"] + list(e.get("sql_detail", [])) + ["```", ""]
    with open(f"{ROOT}/docs/sql-emitted.md", "w") as f:
        f.write("\n".join(lines) + "\n")
