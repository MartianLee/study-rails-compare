#!/usr/bin/env python3
"""Why Active Record costs what it costs — measured inside the Rails process.

The endpoint benchmarks say Active Record is expensive. They do not say what it
is spending. This walks the same query up in four steps, holding the SQL
constant, and counts objects allocated and time spent at each step:

  1. raw mysql2, hashes built by hand      — the floor
  2. the same 4 statements through AR, but `pluck` (no models)
  3. `includes(:user, :tags).to_a`          — models exist, attributes untouched
  4. + full serialisation                   — every attribute actually read

Step 3 minus step 2 is what instantiation costs. Step 4 minus step 3 is what
reading the attributes costs, which is where the type casts live.

    python3 harness/ar_anatomy.py   # -> docs/activerecord-anatomy.md
"""
import json

from common import ROOT, compose, sh, start, stop

RUBY = r'''
require "/app/config/environment"
require "json"
require "objspace"

PER, OFFSET, N = 20, 40, 40

SQL = {
  posts: "SELECT id, user_id, title, slug, body, view_count, comments_count, published_at " \
         "FROM posts WHERE status = 'published' ORDER BY published_at DESC, id DESC " \
         "LIMIT #{PER} OFFSET #{OFFSET}",
}

def raw_conn = ActiveRecord::Base.connection.raw_connection

# ---- 1. what the bare Rack app does, running inside this very process
def raw_sql
  rows = raw_conn.query(SQL[:posts], as: :array).to_a
  uids = rows.map { |r| r[1] }.uniq
  names = raw_conn.query("SELECT id, name FROM users WHERE id IN (#{uids.join(',')})", as: :array)
                  .each_with_object({}) { |(id, name), h| h[id] = { id: id, name: name } }
  pids = rows.map(&:first)
  links = raw_conn.query("SELECT post_id, tag_id FROM post_tags WHERE post_id IN (#{pids.join(',')})",
                         as: :array).to_a
  tids = links.map(&:last).uniq
  tags = raw_conn.query("SELECT id, name, slug FROM tags WHERE id IN (#{tids.join(',')})", as: :array)
                 .each_with_object({}) { |(id, name, slug), h| h[id] = { name: name, slug: slug } }
  by_post = links.each_with_object(Hash.new { |h, k| h[k] = [] }) { |(p, t), h| h[p] << tags[t] }
  rows.map do |id, uid, title, slug, body, views, ccount, pub|
    { id: id, title: title, slug: slug, excerpt: body[0, 160],
      published_at: pub&.utc&.strftime("%Y-%m-%dT%H:%M:%SZ"),
      view_count: views, comment_count: ccount, author: names[uid], tags: by_post[id] || [] }
  end
end

def scope = Post.published.order(published_at: :desc, id: :desc).limit(PER).offset(OFFSET)

# ---- 2. same statements through Active Record, but no models
def ar_pluck
  rows = scope.pluck(:id, :user_id, :title, :slug, :body, :view_count, :comments_count, :published_at)
  names = User.where(id: rows.map { |r| r[1] }.uniq).pluck(:id, :name).to_h
  links = PostTag.where(post_id: rows.map(&:first)).pluck(:post_id, :tag_id)
  tags  = Tag.where(id: links.map(&:last).uniq).pluck(:id, :name, :slug)
             .each_with_object({}) { |(id, n, s), h| h[id] = { name: n, slug: s } }
  by_post = links.each_with_object(Hash.new { |h, k| h[k] = [] }) { |(p, t), h| h[p] << tags[t] }
  rows.map do |id, uid, title, slug, body, views, ccount, pub|
    { id: id, title: title, slug: slug, excerpt: body[0, 160],
      published_at: pub&.utc&.strftime("%Y-%m-%dT%H:%M:%SZ"),
      view_count: views, comment_count: ccount,
      author: { id: uid, name: names[uid] }, tags: by_post[id] || [] }
  end
end

# ---- 3. models exist, attributes never read
def ar_instantiate = scope.includes(:user, :tags).to_a

# ---- 4. every attribute actually read (this is where the type casts happen)
def ar_full
  scope.includes(:user, :tags).map do |p|
    { id: p.id, title: p.title, slug: p.slug, excerpt: p.body[0, 160],
      published_at: p.published_at&.utc&.strftime("%Y-%m-%dT%H:%M:%SZ"),
      view_count: p.view_count, comment_count: p.comments_count,
      author: { id: p.user.id, name: p.user.name },
      tags: p.tags.map { |t| { name: t.name, slug: t.slug } } }
  end
end

# Minimum of several batches, not the mean: in a microbenchmark the noise is
# one-sided (GC, scheduling, YJIT tiering all only ever add time), so the
# minimum is the closest estimate of the actual cost.
def measure(name)
  20.times { yield }
  best = nil
  6.times do
    GC.start
    t0 = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    N.times { yield }
    t1 = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    ms = (t1 - t0) / N * 1000
    best = ms if best.nil? || ms < best
  end
  GC.start
  a0 = GC.stat[:total_allocated_objects]
  N.times { yield }
  { "step" => name, "ms" => best.round(4),
    "objects" => ((GC.stat[:total_allocated_objects] - a0) / N.to_f).round(1) }
end

# per-type allocation for one full request, GC off so nothing is freed underneath
def by_type
  GC.start
  GC.disable
  before = ObjectSpace.count_objects
  ar_full
  after = ObjectSpace.count_objects
  GC.enable
  keys = %i[T_OBJECT T_STRING T_HASH T_ARRAY T_DATA T_STRUCT T_IMEMO]
  keys.each_with_object({}) { |k, h| h[k.to_s] = after.fetch(k, 0) - before.fetch(k, 0) }
end

def by_class
  names = %w[Post User Tag
             ActiveModel::Attribute ActiveModel::AttributeSet
             ActiveModel::LazyAttributeSet ActiveModel::LazyAttributeHash
             ActiveModel::AttributeMutationTracker
             ActiveRecord::Associations::BelongsToAssociation
             ActiveRecord::Associations::HasAndBelongsToManyAssociation
             ActiveRecord::Result ActiveRecord::Relation]
  watch = names.each_with_object({}) do |n, h|
    begin
      h[n] = Object.const_get(n)
    rescue NameError
      next                       # class renamed or gone in this Rails version
    end
  end
  GC.start
  GC.disable
  before = watch.transform_values { |k| ObjectSpace.each_object(k).count }
  ar_full
  after = watch.transform_values { |k| ObjectSpace.each_object(k).count }
  GC.enable
  watch.keys.each_with_object({}) { |k, h| v = after[k] - before[k]; h[k] = v if v > 0 }
end

# Does the width of the table cost anything per request? Same 20 rows, same
# table, same index — only how many columns become attributes changes.
def by_width
  cols = { 2 => %i[id title], 4 => %i[id title slug status],
           7 => %i[id user_id title slug status view_count comments_count],
           11 => Post.column_names.map(&:to_sym) }
  cols.each_with_object({}) do |(n, cs), h|
    m = measure("#{n} columns") do
      scope.select(*cs).to_a.each { |p| cs.each { |c| p.public_send(c) } }
    end
    h[n.to_s] = { "ms" => m["ms"], "objects" => m["objects"] }
  end
end

out = {
  "rows_per_request" => PER,
  "post_columns" => Post.column_names.size,
  "steps" => [
    measure("1. raw mysql2 + hand-built hashes") { raw_sql },
    measure("2. same 4 statements via AR, pluck (no models)") { ar_pluck },
    measure("3. includes(:user, :tags).to_a (models, attributes untouched)") { ar_instantiate },
    measure("4. + full serialisation (every attribute read)") { ar_full },
  ],
  "by_column_count" => by_width,
  "allocations_by_type_one_request" => by_type,
  "allocations_by_class_one_request" => by_class,
}
puts JSON.generate(out)
'''


def main():
    start("rails", env={"APP_CPUS": "4.0", "WEB_CONCURRENCY": "1", "APP_THREADS": "1",
                        "DB_POOL": "2", "RAILS_YJIT": "1"})
    try:
        cid = compose("ps -q rails").stdout.strip()
        with open("/tmp/_ar_anatomy.rb", "w") as f:
            f.write(RUBY)
        sh(f"docker cp /tmp/_ar_anatomy.rb {cid}:/tmp/anatomy.rb")
        r = sh(f"docker exec -e RAILS_ENV=production {cid} bundle exec ruby /tmp/anatomy.rb")
        line = [l for l in r.stdout.strip().splitlines() if l.startswith("{")]
        if not line:
            raise RuntimeError(r.stdout + r.stderr)
        data = json.loads(line[-1])
    finally:
        stop("rails")

    with open(f"{ROOT}/results/ar_anatomy.json", "w") as f:
        json.dump(data, f, indent=2)

    steps = data["steps"]
    lines = ["# What Active Record is actually spending", "",
             f"Measured inside the Rails process by `harness/ar_anatomy.py`. "
             f"{data['rows_per_request']} rows, a {data['post_columns']}-column table, "
             f"the same four SQL statements at every step.", "",
             "| step | ms | objects allocated | vs previous |",
             "|---|--:|--:|--:|"]
    prev = None
    for s in steps:
        d = f"+{s['ms'] - prev['ms']:.3f} ms, +{s['objects'] - prev['objects']:,.0f} objects" if prev else "-"
        lines.append(f"| {s['step']} | {s['ms']:.3f} | {s['objects']:,.0f} | {d} |")
        prev = s
    rows = data["rows_per_request"]
    lines += ["",
              f"Per row that is **{(steps[3]['objects'] - steps[1]['objects']) / rows:.1f} extra objects** "
              f"and **{(steps[3]['ms'] - steps[1]['ms']) / rows * 1000:.0f} µs** for the model, "
              f"on top of running exactly the same SQL.", "",
              "## What those objects are, for one request", "",
              "| Ruby type | allocated |", "|---|--:|"]
    for k, v in data["allocations_by_type_one_request"].items():
        lines.append(f"| `{k}` | {v:,} |")
    byc = data.get("allocations_by_class_one_request") or {}
    if byc and "error" not in byc:
        lines += ["", "| class | instances |", "|---|--:|"]
        for k, v in sorted(byc.items(), key=lambda x: -x[1]):
            lines.append(f"| `{k}` | {v:,} |")
    w = data.get("by_column_count") or {}
    if w:
        lines += ["", "## Does a wider table cost more per request?", "",
                  "Same 20 rows, same table, same index. Only the number of columns that",
                  "become Active Record attributes changes. This is the measured version of",
                  '"a god model is slower" — and it says the cost is columns, not model size.',
                  "", "| columns selected | ms | objects | µs per row |", "|---|--:|--:|--:|"]
        for k in sorted(w, key=int):
            v = w[k]
            lines.append(f"| {k} | {v['ms']:.3f} | {v['objects']:,.0f} | "
                         f"{v['ms'] / rows * 1000:.0f} |")
        ks = sorted(w, key=int)
        lo, hi = w[ks[0]], w[ks[-1]]
        span = int(ks[-1]) - int(ks[0])
        lines += ["", f"Going from {ks[0]} to {ks[-1]} columns costs "
                      f"**+{hi['ms'] - lo['ms']:.3f} ms** and "
                      f"**+{hi['objects'] - lo['objects']:,.0f} objects** per request — "
                      f"about **{(hi['ms'] - lo['ms']) / span / rows * 1000:.1f} µs and "
                      f"{(hi['objects'] - lo['objects']) / span / rows:.1f} objects per row per column**."]
    with open(f"{ROOT}/docs/activerecord-anatomy.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
