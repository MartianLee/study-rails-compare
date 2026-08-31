class Comment < ApplicationRecord
  # `optional: true` is deliberate. Rails' default belongs_to presence check
  # would add two SELECTs per create that no other stack in this repo issues,
  # which would make the write comparison a comparison of different work.
  # The cost of leaving it on is discussed in SPEC.md.
  belongs_to :post, counter_cache: true, optional: true
  belongs_to :user, optional: true

  before_validation :normalize_body
  validates :body, presence: true, length: { maximum: 2000 }

  private

  def normalize_body
    self.body = body.to_s.split.join(" ")
  end
end
