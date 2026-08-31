#!/usr/bin/env python3
"""Deterministic seed generator. Emits SQL on stdout.

Fixed PRNG seed, so every machine that runs this gets byte-identical data.
No third-party dependencies on purpose: `python3 db/gen_seed.py > db/seed.sql`.
"""
import random, sys, datetime

SEED = 20260831
N_USERS, N_POSTS, N_COMMENTS, N_TAGS = 500, 5000, 40000, 40
TAGS_PER_POST = (1, 5)
BODY_WORDS = (90, 160)
COMMENT_WORDS = (12, 45)
DRAFT_RATIO = 0.08
EPOCH = datetime.datetime(2023, 1, 1, 0, 0, 0)

WORDS = """the quick brown fox jumps over lazy dog cache miss latency throughput
allocation garbage collector heap slot object shape inline method table interpreter
bytecode frame stack pointer thread process fork worker request response middleware
router serializer query index buffer pool transaction lock deadlock replica primary
migration schema column row tuple join preload eager lazy batch pagination offset
cursor token session cookie header payload encoding compression handshake socket
buffer stream chunk boundary module package dependency version upgrade rollback
deploy rollout canary metric trace span log alert dashboard budget quota limit""".split()

rnd = random.Random(SEED)

def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")

def words(lo, hi):
    return " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(lo, hi)))

def dt(offset_minutes):
    return (EPOCH + datetime.timedelta(minutes=offset_minutes)).strftime("%Y-%m-%d %H:%M:%S")

def emit(table, cols, rows, chunk=500):
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        sys.stdout.write("INSERT INTO %s (%s) VALUES\n" % (table, ",".join(cols)))
        sys.stdout.write(",\n".join(part))
        sys.stdout.write(";\n")

out = sys.stdout
out.write("SET NAMES utf8mb4;\nSET autocommit=0;\nSET unique_checks=0;\nSET foreign_key_checks=0;\n")

# ---- users
users = []
for i in range(1, N_USERS + 1):
    name = "%s %s" % (rnd.choice(WORDS).capitalize(), rnd.choice(WORDS).capitalize())
    t = dt(i * 7)
    users.append("(%d,'%s','user%d@example.invalid','%s','%s','%s')"
                 % (i, esc(name), i, esc(words(8, 20)), t, t))
emit("users", ["id", "name", "email", "bio", "created_at", "updated_at"], users)

# ---- tags
tags = []
for i in range(1, N_TAGS + 1):
    base = WORDS[(i * 3) % len(WORDS)]
    tags.append("(%d,'%s','%s-%d')" % (i, esc(base), esc(base), i))
emit("tags", ["id", "name", "slug"], tags)

# ---- comment→post assignment first, so posts can be emitted with a correct
#      denormalised comments_count instead of being patched afterwards
counts = [0] * (N_POSTS + 1)
assignment = []
for _ in range(N_COMMENTS):
    # bias toward the high end of the id range: on a real blog, recent posts
    # collect most of the comments
    pid = min(N_POSTS, int(N_POSTS * (rnd.random() ** 0.45)) + 1)
    counts[pid] += 1
    assignment.append(pid)

# ---- posts (published_at strictly increasing, so feed order is stable)
posts, pub_counter, n_published = [], 0, 0
for i in range(1, N_POSTS + 1):
    draft = rnd.random() < DRAFT_RATIO
    status = "draft" if draft else "published"
    created = dt(1000 + i * 11)
    if draft:
        pub = "NULL"
    else:
        pub_counter += 1
        n_published += 1
        pub = "'%s'" % dt(1000 + pub_counter * 13)
    posts.append("(%d,%d,'%s','post-%d','%s','%s',%d,%d,%s,'%s','%s')"
                 % (i, rnd.randint(1, N_USERS), esc(words(5, 11).title()), i,
                    esc(words(*BODY_WORDS)), status, rnd.randint(0, 5000), counts[i],
                    pub, created, created))
emit("posts", ["id", "user_id", "title", "slug", "body", "status", "view_count",
               "comments_count", "published_at", "created_at", "updated_at"], posts, chunk=200)

# ---- comments
comments = []
for i, pid in enumerate(assignment, start=1):
    t = dt(20000 + i * 3)
    comments.append("(%d,%d,%d,'%s','%s','%s')"
                    % (i, pid, rnd.randint(1, N_USERS), esc(words(*COMMENT_WORDS)), t, t))
emit("comments", ["id", "post_id", "user_id", "body", "created_at", "updated_at"], comments, chunk=500)

# ---- post_tags
pt, pid_seq = [], 0
for pid in range(1, N_POSTS + 1):
    chosen = rnd.sample(range(1, N_TAGS + 1), rnd.randint(*TAGS_PER_POST))
    for tid in chosen:
        pid_seq += 1
        pt.append("(%d,%d,%d)" % (pid_seq, pid, tid))
emit("post_tags", ["id", "post_id", "tag_id"], pt, chunk=500)

out.write("SET foreign_key_checks=1;\nSET unique_checks=1;\nCOMMIT;\n")
sys.stderr.write("users=%d tags=%d posts=%d (published=%d) comments=%d post_tags=%d\n"
                 % (N_USERS, N_TAGS, N_POSTS, n_published, N_COMMENTS, pid_seq))
