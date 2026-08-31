// Node "bare": node:http + mysql2 raw SQL + JSON.stringify. Same 3 statements,
// same JSON, same runtime, same driver as the Express+Sequelize app.
const http = require('node:http')
const cluster = require('node:cluster')
const mysql = require('mysql2/promise')

const PORT = Number(process.env.PORT || 3000)
const WORKERS = Number(process.env.WEB_CONCURRENCY || 1)
const EXCERPT = 160

const pool = mysql.createPool({
  host: process.env.DB_HOST || 'mysql',
  user: process.env.DB_USER || 'bench',
  password: process.env.DB_PASSWORD || 'bench',
  database: process.env.DB_NAME || 'blogbench',
  connectionLimit: Number(process.env.DB_POOL || 5),
  timezone: 'Z',
  namedPlaceholders: false,
})

const iso = (d) => (d ? new Date(d).toISOString().replace(/\.\d{3}Z$/, 'Z') : null)
const excerpt = (s) => ([...s].length <= EXCERPT ? s : [...s].slice(0, EXCERPT).join(''))
const marks = (n) => Array(n).fill('?').join(',')

async function loadAuthors(ids) {
  const m = new Map()
  if (!ids.length) return m
  const [rows] = await pool.query(`SELECT id, name FROM users WHERE id IN (${marks(ids.length)})`, ids)
  for (const r of rows) m.set(String(r.id), { id: r.id, name: r.name })
  return m
}

// two statements, matching what the ORMs' preloads emit (see SPEC.md)
async function loadTags(ids) {
  const m = new Map()
  if (!ids.length) return m
  const [links] = await pool.query(
    `SELECT post_id, tag_id FROM post_tags WHERE post_id IN (${marks(ids.length)})`,
    ids
  )
  const tagIds = [...new Set(links.map((l) => l.tag_id))]
  if (!tagIds.length) return m
  const [tags] = await pool.query(
    `SELECT id, name, slug FROM tags WHERE id IN (${marks(tagIds.length)})`,
    tagIds
  )
  const byId = new Map(tags.map((t) => [String(t.id), { name: t.name, slug: t.slug }]))
  for (const l of links) {
    const k = String(l.post_id)
    if (!m.has(k)) m.set(k, [])
    m.get(k).push(byId.get(String(l.tag_id)))
  }
  return m
}

const shape = (p, authors, tags) => ({
  id: p.id,
  title: p.title,
  slug: p.slug,
  excerpt: excerpt(p.body),
  published_at: iso(p.published_at),
  view_count: p.view_count,
  comment_count: p.comments_count,
  author: authors.get(String(p.user_id)) || null,
  tags: tags.get(String(p.id)) || [],
})

function send(res, code, obj) {
  const b = JSON.stringify(obj)
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(b) })
  res.end(b)
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let d = ''
    req.on('data', (c) => {
      d += c
      if (d.length > 1e6) reject(new Error('too large'))
    })
    req.on('end', () => resolve(d))
    req.on('error', reject)
  })
}

async function list(res, page) {
  const [rows] = await pool.query(
    `SELECT id, user_id, title, slug, body, view_count, comments_count, published_at
     FROM posts WHERE status = ? ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET ?`,
    ['published', (page - 1) * 20]
  )
  const authors = await loadAuthors([...new Set(rows.map((r) => r.user_id))])
  const tags = await loadTags(rows.map((r) => r.id))
  send(res, 200, rows.map((p) => shape(p, authors, tags)))
}

async function detail(res, id) {
  const [prows] = await pool.query(
    `SELECT id, user_id, title, slug, body, view_count, comments_count, published_at
     FROM posts WHERE id = ?`,
    [id]
  )
  if (!prows.length) return send(res, 404, { error: 'not found' })
  const p = prows[0]
  const authors = await loadAuthors([p.user_id])
  const tags = await loadTags([p.id])
  const [crows] = await pool.query(
    `SELECT id, user_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id DESC LIMIT 20`,
    [id]
  )
  const cauthors = await loadAuthors([...new Set(crows.map((c) => c.user_id))])
  send(res, 200, {
    ...shape(p, authors, tags),
    body: p.body,
    comments: crows.map((c) => ({
      id: c.id,
      body: c.body,
      created_at: iso(c.created_at),
      author: cauthors.get(String(c.user_id)) || null,
    })),
  })
}

async function create(req, res) {
  let payload
  try {
    payload = JSON.parse(await readBody(req))
  } catch {
    return send(res, 400, { error: 'bad json' })
  }
  const body = String(payload.body ?? '').trim().split(/\s+/).join(' ')
  if (!body || [...body].length > 2000) return send(res, 422, { errors: ['body is invalid'] })
  const conn = await pool.getConnection()
  try {
    await conn.beginTransaction()
    const now = new Date()
    const [r] = await conn.execute(
      'INSERT INTO comments (post_id, user_id, body, created_at, updated_at) VALUES (?,?,?,?,?)',
      [payload.post_id, payload.user_id, body, now, now]
    )
    await conn.execute('UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?', [payload.post_id])
    await conn.commit()
    send(res, 201, { id: r.insertId, post_id: payload.post_id, user_id: payload.user_id, body })
  } catch (e) {
    await conn.rollback()
    send(res, 500, { error: e.message })
  } finally {
    conn.release()
  }
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, 'http://x')
    if (u.pathname === '/healthz') return send(res, 200, { ok: true })
    if (req.method === 'GET' && u.pathname === '/api/posts')
      return await list(res, Math.max(1, Number(u.searchParams.get('page')) || 1))
    if (req.method === 'POST' && u.pathname === '/api/comments') return await create(req, res)
    const m = u.pathname.match(/^\/api\/posts\/(\d+)$/)
    if (req.method === 'GET' && m) return await detail(res, Number(m[1]))
    send(res, 404, { error: 'not found' })
  } catch (e) {
    send(res, 500, { error: e.message })
  }
})

if (WORKERS > 1 && cluster.isPrimary) {
  for (let i = 0; i < WORKERS; i++) cluster.fork()
  cluster.on('exit', () => cluster.fork())
} else {
  server.listen(PORT, () => console.error(`node/bare listening on ${PORT}`))
}
