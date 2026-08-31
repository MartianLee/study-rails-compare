class CommentsController < ApplicationController
  def create
    comment = Comment.new(comment_params)

    if comment.save
      render json: comment.slice(:id, :post_id, :user_id, :body), status: :created
    else
      render json: { errors: comment.errors.full_messages }, status: :unprocessable_entity
    end
  end

  private

  def comment_params
    params.permit(:post_id, :user_id, :body).to_h.slice("post_id", "user_id", "body")
  end
end
