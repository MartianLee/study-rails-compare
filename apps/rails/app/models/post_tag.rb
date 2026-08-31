class PostTag < ApplicationRecord
  self.table_name = "post_tags"
  belongs_to :post
  belongs_to :tag
end
