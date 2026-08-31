# Rails-only probes. Not part of the cross-stack comparison — these exist to
# split one Rails request into its layers by holding everything constant except
# how much Active Record runs.
class ProbesController < ApplicationController
  # Same middleware, same router, same renderer. Zero database.
  STATIC = (1..20).map do |i|
    {
      id: i, title: "Static post #{i}", slug: "static-#{i}",
      excerpt: "x" * ApplicationController::EXCERPT,
      published_at: "2024-01-01T00:00:00Z", view_count: i, comment_count: i,
      author: { id: i, name: "Static Author" },
      tags: [{ name: "static", slug: "static-1" }]
    }
  end.freeze

  def static
    render json: STATIC
  end

  # The same three statements as PostsController#index, but with `pluck` instead
  # of model instantiation: the rows never become Active Record objects.
  def pluck
    offset = (page_param - 1) * PER_PAGE
    rows = Post.published.order(published_at: :desc, id: :desc)
               .limit(PER_PAGE).offset(offset)
               .pluck(:id, :user_id, :title, :slug, :body, :view_count, :comments_count, :published_at)

    authors = User.where(id: rows.map { |r| r[1] }.uniq).pluck(:id, :name).to_h
    links = PostTag.where(post_id: rows.map(&:first)).pluck(:post_id, :tag_id)
    names = Tag.where(id: links.map(&:last).uniq).pluck(:id, :name, :slug)
               .each_with_object({}) { |(id, name, slug), h| h[id] = [name, slug] }
    tags = links.group_by(&:first)

    render json: rows.map { |id, uid, title, slug, body, views, ccount, pub|
      {
        id: id, title: title, slug: slug, excerpt: body[0, EXCERPT],
        published_at: iso(pub), view_count: views, comment_count: ccount,
        author: { id: uid, name: authors[uid] },
        tags: (tags[id] || []).map { |_, tid| { name: names[tid][0], slug: names[tid][1] } }
      }
    }
  end
end
