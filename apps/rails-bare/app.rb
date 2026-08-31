# frozen_string_literal: true

# Ruby "bare": Rack + mysql2 raw SQL + stdlib JSON, served by the same Puma with
# the same settings as the Rails app next door. Same three statements, same JSON.
# Everything Rails does that this does not IS the framework + Active Record.

require "json"
require "mysql2"
require "rack"

module Bare
  PER_PAGE = 20
  EXCERPT  = 160

  POST_COLS = "id, user_id, title, slug, body, view_count, comments_count, published_at"

  SQL = {
    list: "SELECT #{POST_COLS} FROM posts WHERE status = ? " \
          "ORDER BY published_at DESC, id DESC LIMIT #{PER_PAGE} OFFSET ?",
    one:  "SELECT #{POST_COLS} FROM posts WHERE id = ?",
    comments: "SELECT id, user_id, body, created_at FROM comments " \
              "WHERE post_id = ? ORDER BY id DESC LIMIT 20",
    insert: "INSERT INTO comments (post_id, user_id, body, created_at, updated_at) " \
            "VALUES (?, ?, ?, ?, ?)",
    bump: "UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?"
  }.freeze

  # One connection per Puma thread, mirroring how Active Record hands one
  # pooled connection to the thread serving the request.
  def self.conn
    Thread.current[:bare_conn] ||= Mysql2::Client.new(
      host: ENV.fetch("DB_HOST", "mysql"),
      username: ENV.fetch("DB_USER", "bench"),
      password: ENV.fetch("DB_PASSWORD", "bench"),
      database: ENV.fetch("DB_NAME", "blogbench"),
      encoding: "utf8mb4",
      cast_booleans: false,
      database_timezone: :utc,
      application_timezone: :utc
    )
  end

  def self.stmt(key, sql = nil)
    cache = (Thread.current[:bare_stmts] ||= {})
    cache[key] ||= conn.prepare(sql || SQL.fetch(key))
  end

  def self.iso(time)
    time&.utc&.strftime("%Y-%m-%dT%H:%M:%SZ")
  end

  def self.authors(ids)
    return {} if ids.empty?

    marks = (["?"] * ids.size).join(",")
    rows = stmt(:"authors_#{ids.size}", "SELECT id, name FROM users WHERE id IN (#{marks})")
           .execute(*ids, as: :array)
    rows.each_with_object({}) { |(id, name), h| h[id] = { id: id, name: name } }
  end

  # Two statements, not a join: Active Record's HABTM preload loads the join
  # rows first and the tags second, so the bare app does the same. See SPEC.md.
  def self.tags(ids)
    return {} if ids.empty?

    marks = (["?"] * ids.size).join(",")
    joins = stmt(:"pt_#{ids.size}",
                 "SELECT post_tags.post_id, post_tags.tag_id FROM post_tags " \
                 "WHERE post_tags.post_id IN (#{marks})").execute(*ids, as: :array).to_a
    tag_ids = joins.map(&:last).uniq
    return {} if tag_ids.empty?

    tmarks = (["?"] * tag_ids.size).join(",")
    names = stmt(:"tg_#{tag_ids.size}", "SELECT id, name, slug FROM tags WHERE id IN (#{tmarks})")
            .execute(*tag_ids, as: :array)
            .each_with_object({}) { |(id, name, slug), h| h[id] = { name: name, slug: slug } }

    joins.each_with_object(Hash.new { |h, k| h[k] = [] }) do |(pid, tid), h|
      h[pid] << names[tid]
    end
  end

  def self.shape(row, authors, tags)
    id, uid, title, slug, body, views, ccount, pub = row
    {
      id: id, title: title, slug: slug, excerpt: body[0, EXCERPT],
      published_at: iso(pub), view_count: views, comment_count: ccount,
      author: authors[uid], tags: tags[id] || []
    }
  end

  def self.list(page)
    rows = stmt(:list).execute("published", (page - 1) * PER_PAGE, as: :array).to_a
    a = authors(rows.map { |r| r[1] }.uniq)
    t = tags(rows.map(&:first))
    [200, rows.map { |r| shape(r, a, t) }]
  end

  def self.detail(id)
    row = stmt(:one).execute(id, as: :array).first
    return [404, { error: "not found" }] if row.nil?

    payload = shape(row, authors([row[1]]), tags([row[0]]))
    payload[:body] = row[4]
    crows = stmt(:comments).execute(id, as: :array).to_a
    ca = authors(crows.map { |c| c[1] }.uniq)
    payload[:comments] = crows.map do |cid, cuid, body, created|
      { id: cid, body: body, created_at: iso(created), author: ca[cuid] }
    end
    [200, payload]
  end

  def self.create(raw)
    payload = JSON.parse(raw.to_s.empty? ? "{}" : raw)
    body = payload["body"].to_s.split.join(" ")
    return [422, { errors: ["body is invalid"] }] if body.empty? || body.length > 2000

    now = Time.now.utc.strftime("%Y-%m-%d %H:%M:%S")
    c = conn
    c.query("BEGIN")
    begin
      stmt(:insert).execute(payload["post_id"], payload["user_id"], body, now, now)
      new_id = c.last_id
      stmt(:bump).execute(payload["post_id"])
      c.query("COMMIT")
    rescue StandardError => e
      c.query("ROLLBACK")
      return [500, { error: e.message }]
    end
    [201, { id: new_id, post_id: payload["post_id"], user_id: payload["user_id"], body: body }]
  rescue JSON::ParserError
    [400, { error: "bad json" }]
  end

  DETAIL = %r{\A/api/posts/(\d+)\z}

  APP = lambda do |env|
    path = env["PATH_INFO"]
    code, payload =
      if path == "/healthz"
        [200, { ok: true }]
      elsif env["REQUEST_METHOD"] == "GET" && path == "/api/posts"
        page = Rack::Utils.parse_query(env["QUERY_STRING"])["page"].to_i
        list(page < 1 ? 1 : page)
      elsif env["REQUEST_METHOD"] == "POST" && path == "/api/comments"
        create(env["rack.input"].read)
      elsif env["REQUEST_METHOD"] == "GET" && (m = DETAIL.match(path))
        detail(m[1].to_i)
      else
        [404, { error: "not found" }]
      end
    body = JSON.generate(payload)
    [code, { "content-type" => "application/json", "content-length" => body.bytesize.to_s }, [body]]
  end
end
