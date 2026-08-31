"""Python "bare": a plain WSGI callable + MySQLdb raw SQL + json.dumps.

Same runtime, same server (gunicorn), same C driver as the Django app.
Everything the Django app does that this does not IS the framework + ORM.
"""
import json
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import parse_qs

import MySQLdb

EXCERPT = 160
PER_PAGE = 20
_local = threading.local()

_DB = dict(
    host=os.environ.get("DB_HOST", "mysql"),
    user=os.environ.get("DB_USER", "bench"),
    passwd=os.environ.get("DB_PASSWORD", "bench"),
    db=os.environ.get("DB_NAME", "blogbench"),
    charset="utf8mb4",
    autocommit=True,
)


def conn():
    """One persistent connection per worker thread — the same shape as Django's
    CONN_MAX_AGE, so the comparison isn't a pooling comparison."""
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = MySQLdb.connect(**_DB)
    else:
        try:
            c.ping(True)
        except MySQLdb.Error:
            c = _local.conn = MySQLdb.connect(**_DB)
    return c


def _iso(dt):
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _marks(n):
    return ",".join(["%s"] * n)


def _authors(cur, ids):
    if not ids:
        return {}
    cur.execute("SELECT id, name FROM users WHERE id IN (%s)" % _marks(len(ids)), tuple(ids))
    return {r[0]: {"id": r[0], "name": r[1]} for r in cur.fetchall()}


def _tags(cur, ids):
    """Two statements, matching what the ORMs' preloads emit (see SPEC.md)."""
    out = {}
    if not ids:
        return out
    cur.execute(
        "SELECT post_id, tag_id FROM post_tags WHERE post_id IN (%s)" % _marks(len(ids)),
        tuple(ids),
    )
    links = cur.fetchall()
    tag_ids = sorted({t for _, t in links})
    if not tag_ids:
        return out
    cur.execute(
        "SELECT id, name, slug FROM tags WHERE id IN (%s)" % _marks(len(tag_ids)),
        tuple(tag_ids),
    )
    by_id = {r[0]: {"name": r[1], "slug": r[2]} for r in cur.fetchall()}
    for pid, tid in links:
        out.setdefault(pid, []).append(by_id[tid])
    return out


POST_COLS = "id, user_id, title, slug, body, view_count, comments_count, published_at"


def _shape(row, authors, tags):
    pid, uid, title, slug, body, views, ccount, pub = row
    return {
        "id": pid,
        "title": title,
        "slug": slug,
        "excerpt": body[:EXCERPT],
        "published_at": _iso(pub),
        "view_count": views,
        "comment_count": ccount,
        "author": authors.get(uid),
        "tags": tags.get(pid, []),
    }


def post_list(page):
    cur = conn().cursor()
    cur.execute(
        "SELECT %s FROM posts WHERE status = %%s ORDER BY published_at DESC, id DESC "
        "LIMIT %d OFFSET %%s" % (POST_COLS, PER_PAGE),
        ("published", (page - 1) * PER_PAGE),
    )
    rows = cur.fetchall()
    authors = _authors(cur, sorted({r[1] for r in rows}))
    tags = _tags(cur, [r[0] for r in rows])
    cur.close()
    return 200, [_shape(r, authors, tags) for r in rows]


def post_detail(post_id):
    cur = conn().cursor()
    cur.execute("SELECT %s FROM posts WHERE id = %%s" % POST_COLS, (post_id,))
    row = cur.fetchone()
    if row is None:
        cur.close()
        return 404, {"error": "not found"}
    authors = _authors(cur, [row[1]])
    tags = _tags(cur, [row[0]])
    payload = _shape(row, authors, tags)
    payload["body"] = row[4]
    cur.execute(
        "SELECT id, user_id, body, created_at FROM comments WHERE post_id = %s ORDER BY id DESC LIMIT 20",
        (post_id,),
    )
    crows = cur.fetchall()
    cauthors = _authors(cur, sorted({c[1] for c in crows}))
    cur.close()
    payload["comments"] = [
        {"id": c[0], "body": c[2], "created_at": _iso(c[3]), "author": cauthors.get(c[1])}
        for c in crows
    ]
    return 200, payload


_WS = re.compile(r"\s+")


def create_comment(raw):
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return 400, {"error": "bad json"}
    body = _WS.sub(" ", (payload.get("body") or "")).strip()
    if not body or len(body) > 2000:
        return 422, {"errors": ["body is invalid"]}
    c = conn()
    cur = c.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.begin()
        cur.execute(
            "INSERT INTO comments (post_id, user_id, body, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            (payload.get("post_id"), payload.get("user_id"), body, now, now),
        )
        new_id = cur.lastrowid
        cur.execute(
            "UPDATE posts SET comments_count = comments_count + 1 WHERE id = %s",
            (payload.get("post_id"),),
        )
        c.commit()
    except MySQLdb.Error as e:
        c.rollback()
        cur.close()
        return 500, {"error": str(e)}
    cur.close()
    return 201, {
        "id": new_id,
        "post_id": payload.get("post_id"),
        "user_id": payload.get("user_id"),
        "body": body,
    }


_DETAIL = re.compile(r"^/api/posts/(\d+)$")


def application(environ, start_response):
    path, method = environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "GET")
    try:
        if path == "/healthz":
            code, payload = 200, {"ok": True}
        elif method == "GET" and path == "/api/posts":
            q = parse_qs(environ.get("QUERY_STRING", ""))
            try:
                page = max(1, int(q.get("page", ["1"])[0]))
            except ValueError:
                page = 1
            code, payload = post_list(page)
        elif method == "POST" and path == "/api/comments":
            n = int(environ.get("CONTENT_LENGTH") or 0)
            code, payload = create_comment(environ["wsgi.input"].read(n))
        else:
            m = _DETAIL.match(path)
            if method == "GET" and m:
                code, payload = post_detail(int(m.group(1)))
            else:
                code, payload = 404, {"error": "not found"}
    except Exception as e:  # noqa: BLE001 - benchmark server, surface the error
        code, payload = 500, {"error": str(e)}

    body = json.dumps(payload, separators=(",", ":")).encode()
    start_response(
        "%d %s" % (code, {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found",
                          405: "Method Not Allowed", 422: "Unprocessable Entity",
                          500: "Internal Server Error"}[code]),
        [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
    )
    return [body]
