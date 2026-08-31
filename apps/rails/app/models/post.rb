class Post < ApplicationRecord
  belongs_to :user
  has_many :comments
  # HABTM (not has_many :through) so preloading tags is one statement, matching
  # what GORM, Django and the hand-written SQL all emit. See SPEC.md.
  has_and_belongs_to_many :tags, join_table: "post_tags"

  scope :published, -> { where(status: "published") }
end
