# SPEC — what every stack must implement

Eight servers. Four runtimes (Ruby, Node, Python, Go), each in two variants:

| variant | HTTP layer | data layer | JSON |
|---|---|---|---|
| **full** | the runtime's mainstream web framework | that framework's mainstream ORM | the framework's renderer |
| **bare** | the *same* HTTP server, hand-rolled routing | raw SQL over the *same* driver | the standard-library JSON encoder |

The pair inside one runtime differs **only** by framework + ORM. Whatever is left
over when you subtract `bare` from `full` is what this repo calls the **magic tax**.

| runtime | full | bare | shared HTTP server | shared driver |
|---|---|---|---|---|
| Ruby | Rails 8.1 + Active Record | Rack + raw SQL | Puma 6 | `mysql2` (C) |
| Node | Express 4 + Sequelize 6 | `node:http` + raw SQL | node itself | `mysql2` (JS) |
| Python | Django 5.1 + Django ORM | bare WSGI + raw SQL | gunicorn (gthread) | `mysqlclient` (C) |
| Go | Gin + GORM | `net/http` + `database/sql` | net/http | `go-sql-driver/mysql` |

Cross-runtime numbers are interesting; the **within-runtime ratio is the point**,
because it cancels out the runtime, the driver, the OS and the machine.

## Domain

A small blog. Five tables, seeded identically for every stack from `db/schema.sql`
plus a generated `db/seed.sql` (fixed PRNG seed → byte-identical data everywhere).

```
users(500) ──< posts(5,000) ──< comments(40,000)
                   └──< post_tags(15,167) >── tags(40)
```

`posts.comments_count` is a real denormalised column, so no stack has to run an
aggregate the others don't. That is also what a real blog does.

## Endpoints

Every stack exposes all three at the same paths and returns **JSON that is equal
value-for-value**. `harness/verify.py` diffs each stack against the Rails app and
fails the run on any difference.

### 1. `GET /api/posts?page=N` — the headline measurement

20 published posts, newest first, each with author, tags and comment count.

```json
[{"id":4981,"title":"...","slug":"post-4981","excerpt":"...160 chars...",
  "published_at":"2023-02-12T13:21:00Z","view_count":812,"comment_count":7,
  "author":{"id":233,"name":"..."},
  "tags":[{"name":"heap","slug":"heap-5"}]}]
```

**Fairness rule — exactly four statements**, in every stack:

```sql
SELECT ... FROM posts WHERE status='published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET ?
SELECT ... FROM users     WHERE id      IN (...)
SELECT ... FROM post_tags WHERE post_id IN (...)
SELECT ... FROM tags      WHERE id      IN (...)
```

So every ORM must **preload, never join** — Rails `includes`, Django
`prefetch_related`, Sequelize explicit finders, GORM `Preload`.

The tag load is deliberately two statements rather than one join. That is not a
stylistic choice: Active Record's `has_and_belongs_to_many` preload and GORM's
`many2many` preload both fetch the join rows first and the tags second, and
neither can be talked out of it. Rather than bend two ORMs into an unnatural
shape, the other six stacks were written to emit what those two emit.

### 2. `GET /api/posts/:id` — nested serialisation

One post + author + tags + its 20 newest comments + each comment's author.
Six statements, same rule.

### 3. `POST /api/comments` — the write path

`{"post_id":N,"user_id":N,"body":"..."}` → `201` and the created comment.

Each stack must, in one transaction: collapse whitespace in `body`, reject blank
or >2,000 characters with `422`, `INSERT` the comment, and
`UPDATE posts SET comments_count = comments_count + 1`.

Rails does it with `before_validation`, `validates` and
`belongs_to :post, counter_cache: true`. The other three use their own
equivalents (Sequelize hooks + validators, Django `full_clean`, a GORM
transaction with hand-written checks).

Two honest caveats on this endpoint:

- It is the **least symmetric** of the three, because "equivalent validation"
  across four frameworks is a judgement call. It is reported separately and no
  headline claim rests on it.
- Rails' `belongs_to` is declared `optional: true`. Left at its default, Rails
  would issue two extra `SELECT`s per create to prove the post and user exist —
  work no other stack does. Turning that off keeps the statement sets equal.
  It is a real Rails cost that this benchmark deliberately does not charge.

### Probes (Rails only)

`/api/static` (fixed JSON, no database) and `/api/posts_pluck` (the same four
statements via `pluck`, hand-built hashes, no Active Record objects). They are
not part of the cross-stack comparison. They exist to split one Rails request
into layers by holding the middleware, the router and the renderer constant and
varying only how much Active Record runs.

`/healthz` on every stack: `{"ok":true}`, no database. Readiness only.

## Wire protocol

Within each pair the two variants use the same MySQL protocol, because a
prepared-statement stack and a text-protocol stack are not comparable:

| pair | protocol | statements cached? |
|---|---|---|
| Ruby | prepared | yes both sides — Rails' per-connection cache, `Mysql2::Statement` per Puma thread |
| Go | prepared | yes both sides — GORM `PrepareStmt: true`, a `sync.Map` of `*sql.Stmt` in the bare app |
| Node | text | n/a — Sequelize's default and `pool.query` both send text |
| Python | text | n/a — Django's client-side interpolation and `cursor.execute` args both send text |

The Go row needed fixing and is worth calling out, because it is exactly the kind
of thing that quietly decides a benchmark. `database/sql`'s `db.Query(sql, args...)`
does **not** cache: with `go-sql-driver` it prepares, executes and closes the
statement on every call — three round trips instead of one, and a fresh parse in
MySQL each time. GORM with `PrepareStmt: true` caches. Left alone, GORM would have
looked better than it is purely because the thing it was compared against was
handicapped. The bare app now keeps its own statement cache.

Across runtimes the protocol therefore differs. That is one more reason the
within-runtime ratio is the number to quote.

## Framework choices worth arguing about

- **Django without DRF.** Django REST Framework is an optional extra layer;
  Active Record is not optional in Rails. Django ORM objects plus a hand-built
  dict is the same shape as the Rails controller here. Adding DRF would make
  Django's magic tax larger, not smaller.
- **Sequelize, not Prisma or TypeORM.** Sequelize is the closest analogue to
  Active Record: models with instances, validations, hooks and associations.
- **Express 4, not 5 or Fastify.** Express is still what most Node services run.
- **YJIT is on for Rails**, because Rails 7.2+ turns it on by default and this
  repo measures what you would actually deploy. The harness also measures Rails
  with `RAILS_YJIT=0` so the JIT's contribution is a number rather than a claim.

## Measurement rules

- **One app container at a time.** MySQL and the load generator are the only
  other things running. Measuring stacks in parallel contaminates throughput.
- **The load generator is a container on the same bridge network.** Measuring
  from the macOS host would put Docker's port forwarder in every latency sample.
  Host ports exist only for readiness and correctness checks.
- Identical CPU limit, memory limit and image base family per mode.
- Production mode everywhere, logging at `warn`, access logs off.
- The connection pool is sized to the load concurrency, so no stack is ever
  throttled by the pool instead of by its own CPU. An async runtime has to be
  allowed to keep as many queries in flight as it can.
- Each endpoint gets a throwaway warm-up pass, then a fresh 10-second window.
  The CPU counter is read around the measured window only.
- **The database is rebuilt from `schema.sql` + `seed.sql` before every run.** The
  write test inserts and deletes on the order of a hundred thousand rows, which
  leaves the tables fragmented and the auto_increment far from where it started.
  Two runs against differently-aged tables are not the same experiment.
- **MySQL gets 8 CPUs and the load generator 3**, far above what any app under
  test can drive them to. An earlier campaign gave MySQL 4, and the fastest bare
  stacks pushed it to 3.2 cores and began queueing on the database — at which
  point the benchmark was measuring MySQL, not the app. Every result records
  `mysql_cores` for the window so a reader can check this directly.
- 3 independent runs. The reported number is the **median**, with the spread.

## Which number to quote

**CPU-ms per request is the robust one.** Two campaigns run days apart with
different MySQL configurations produced app CPU per request within a few percent
of each other (Rails 1.13 → 1.11, Rack 0.144 → 0.140) while *throughput* moved by
a third. The reason is structural: a `bare` stack does so little work per request
that its throughput is dominated by database round-trip latency, so anything that
changes round-trip latency changes the throughput ratio without changing what
either application actually does.

The practical consequence is worth stating plainly, because it cuts against how
these comparisons are usually quoted: **the magic tax measured as a throughput
ratio depends on how fast your database is.** Against a local, unloaded MySQL the
ratio is at its largest. Against a managed database across a network — which is
what you actually run — the framework's share of the request shrinks and the
ratio comes down. The CPU ratio does not move, because it is a property of the
code, not of the wire.

## Modes

| mode | app CPUs | processes × threads | load concurrency | pool |
|---|---|---|---|---|
| `single` | 1.0 | 1 × 1 | 8 | 8 |
| `tuned` | 2.0 | 2 × 5 (Go: `GOMAXPROCS=2`) | 50 | 50 |

`single` isolates per-request cost; the number to read there is **CPU-ms per
request**, which is immune to queueing. `tuned` is what you would deploy on a
2-vCPU box; the numbers to read there are throughput and latency.

One artefact worth knowing about in `single`: Puma's default `max_fast_inline`
serves up to ten keep-alive requests on one connection before yielding to the
others, so a single-threaded Puma shows a very low p50 and a very high p99. That
is real Puma behaviour, not a measurement bug, but it makes single-threaded
latency percentiles a poor cross-stack comparison. Compare latency in `tuned`.
