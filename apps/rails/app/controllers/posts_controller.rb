class PostsController < ApplicationController
  # 3 statements: the posts page, preload users, preload tags.
  def index
    posts = Post.published
                .order(published_at: :desc, id: :desc)
                .limit(PER_PAGE)
                .offset((page_param - 1) * PER_PAGE)
                .includes(:user, :tags)

    render json: posts.map { |post| serialize(post) }
  end

  # 5 statements.
  def show
    post = Post.includes(:user, :tags).find_by(id: params[:id])
    return render(json: { error: "not found" }, status: :not_found) if post.nil?

    comments = post.comments.includes(:user).order(id: :desc).limit(20)

    render json: serialize(post).merge(
      body: post.body,
      comments: comments.map do |comment|
        {
          id: comment.id,
          body: comment.body,
          created_at: iso(comment.created_at),
          author: { id: comment.user.id, name: comment.user.name }
        }
      end
    )
  end

  private

  def serialize(post)
    {
      id: post.id,
      title: post.title,
      slug: post.slug,
      excerpt: post.body[0, EXCERPT],
      published_at: iso(post.published_at),
      view_count: post.view_count,
      comment_count: post.comments_count,
      author: { id: post.user.id, name: post.user.name },
      tags: post.tags.map { |tag| { name: tag.name, slug: tag.slug } }
    }
  end
end
