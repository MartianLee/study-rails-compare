// Node "full": Express + Sequelize — the mainstream Node web framework and a
// mainstream Node ORM. Preloads explicitly so it issues the same 3 statements
// the other stacks do (Sequelize's default `include` would emit a JOIN instead).
const cluster = require('node:cluster')
const express = require('express')
const { Op } = require('sequelize')
const { sequelize, User, Tag, Post, Comment, PostTag } = require('./models')

const PORT = Number(process.env.PORT || 3000)
const WORKERS = Number(process.env.WEB_CONCURRENCY || 1)
const EXCERPT = 160

const iso = (d) => (d ? new Date(d).toISOString().replace(/\.\d{3}Z$/, 'Z') : null)
const excerpt = (s) => ([...s].length <= EXCERPT ? s : [...s].slice(0, EXCERPT).join(''))

async function preloadAuthors(ids) {
  if (!ids.length) return new Map()
  const rows = await User.findAll({ where: { id: { [Op.in]: ids } }, attributes: ['id', 'name'] })
  return new Map(rows.map((u) => [String(u.id), { id: Number(u.id), name: u.name }]))
}

// Two statements, not an `include` join: Active Record's HABTM preload and
// GORM's many2many preload both load the join rows first and the tags second,
// so every stack in this repo issues the same four statements. See SPEC.md.
async function preloadTags(postIds) {
  if (!postIds.length) return new Map()
  const links = await PostTag.findAll({
    where: { post_id: { [Op.in]: postIds } },
    attributes: ['post_id', 'tag_id'],
  })
  const tagIds = [...new Set(links.map((l) => String(l.tag_id)))]
  if (!tagIds.length) return new Map()
  const tags = await Tag.findAll({ where: { id: { [Op.in]: tagIds } }, attributes: ['id', 'name', 'slug'] })
  const byId = new Map(tags.map((t) => [String(t.id), { name: t.name, slug: t.slug }]))
  const m = new Map()
  for (const l of links) {
    const k = String(l.post_id)
    if (!m.has(k)) m.set(k, [])
    m.get(k).push(byId.get(String(l.tag_id)))
  }
  return m
}

function serialisePost(p, authors, tags) {
  return {
    id: Number(p.id),
    title: p.title,
    slug: p.slug,
    excerpt: excerpt(p.body),
    published_at: iso(p.published_at),
    view_count: p.view_count,
    comment_count: p.comments_count,
    author: authors.get(String(p.user_id)) || null,
    tags: tags.get(String(p.id)) || [],
  }
}

function buildApp() {
  const app = express()
  app.disable('x-powered-by')
  app.disable('etag')
  app.use(express.json({ limit: '1mb' }))

  app.get('/healthz', (_req, res) => res.json({ ok: true }))

  app.get('/api/posts', async (req, res, next) => {
    try {
      const page = Math.max(1, Number(req.query.page) || 1)
      const posts = await Post.findAll({
        where: { status: 'published' },
        order: [
          ['published_at', 'DESC'],
          ['id', 'DESC'],
        ],
        limit: 20,
        offset: (page - 1) * 20,
      })
      const [authors, tags] = [
        await preloadAuthors([...new Set(posts.map((p) => p.user_id))]),
        await preloadTags(posts.map((p) => p.id)),
      ]
      res.json(posts.map((p) => serialisePost(p, authors, tags)))
    } catch (e) {
      next(e)
    }
  })

  app.get('/api/posts/:id', async (req, res, next) => {
    try {
      const post = await Post.findByPk(req.params.id)
      if (!post) return res.status(404).json({ error: 'not found' })
      const authors = await preloadAuthors([post.user_id])
      const tags = await preloadTags([post.id])
      const comments = await Comment.findAll({
        where: { post_id: post.id },
        order: [['id', 'DESC']],
        limit: 20,
      })
      const cauthors = await preloadAuthors([...new Set(comments.map((c) => c.user_id))])
      res.json({
        ...serialisePost(post, authors, tags),
        body: post.body,
        comments: comments.map((c) => ({
          id: Number(c.id),
          body: c.body,
          created_at: iso(c.created_at),
          author: cauthors.get(String(c.user_id)) || null,
        })),
      })
    } catch (e) {
      next(e)
    }
  })

  app.post('/api/comments', async (req, res, next) => {
    try {
      const { post_id, user_id, body } = req.body || {}
      const created = await sequelize.transaction(async (tx) => {
        const now = new Date()
        const c = await Comment.create(
          { post_id, user_id, body, created_at: now, updated_at: now },
          { transaction: tx }
        )
        await Post.increment('comments_count', { by: 1, where: { id: post_id }, transaction: tx })
        return c
      })
      res.status(201).json({
        id: Number(created.id),
        post_id: Number(created.post_id),
        user_id: Number(created.user_id),
        body: created.body,
      })
    } catch (e) {
      if (e.name === 'SequelizeValidationError') {
        return res.status(422).json({ errors: e.errors.map((x) => x.message) })
      }
      next(e)
    }
  })

  app.use((err, _req, res, _next) => {
    console.error(err.message)
    res.status(500).json({ error: err.message })
  })
  return app
}

if (WORKERS > 1 && cluster.isPrimary) {
  for (let i = 0; i < WORKERS; i++) cluster.fork()
  cluster.on('exit', () => cluster.fork())
} else {
  buildApp().listen(PORT, () => console.error(`node/express listening on ${PORT}`))
}
