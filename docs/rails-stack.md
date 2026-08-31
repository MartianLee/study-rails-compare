# What the Rails app in this repo actually is

Read out of the running process by `harness/rails_stack.py`, not written by hand.

```json
{
  "rails_version": "8.1.3.1",
  "ruby": "ruby 3.4.10 (2026-06-30 revision 2b0b7728dc) +YJIT +PRISM [aarch64-linux]",
  "yjit_enabled": true,
  "api_only": true,
  "eager_load": true,
  "prepared_statements": true,
  "association_methods": [
    "autosave_associated_records_for_comments",
    "autosave_associated_records_for_posts_tags",
    "autosave_associated_records_for_tags",
    "autosave_associated_records_for_user",
    "validate_associated_records_for_comments",
    "validate_associated_records_for_posts_tags",
    "validate_associated_records_for_tags"
  ],
  "generated_association_methods": [
    "build_user",
    "comment_ids",
    "comment_ids=",
    "comments",
    "comments=",
    "create_user",
    "create_user!",
    "reload_user",
    "reset_user",
    "tag_ids",
    "tag_ids=",
    "tags",
    "tags=",
    "user",
    "user=",
    "user_changed?",
    "user_previously_changed?"
  ],
  "attribute_methods_before_first_use": 0,
  "attribute_methods_after_first_use": 245,
  "post_columns": [
    "id",
    "user_id",
    "title",
    "slug",
    "body",
    "status",
    "view_count",
    "comments_count",
    "published_at",
    "created_at",
    "updated_at"
  ]
}
```

## Middleware stack (13 entries)

This is the live `Rails.application.middleware`. It is what `rails new --api`
gives you, minus nothing — no middleware was removed to make the numbers better.

```
use Rack::Sendfile
use ActionDispatch::Static
use ActionDispatch::Executor
use Rack::Runtime
use ActionDispatch::RequestId
use ActionDispatch::RemoteIp
use Rails::Rack::Logger
use ActionDispatch::ShowExceptions
use ActionDispatch::DebugExceptions
use ActionDispatch::Callbacks
use Rack::Head
use Rack::ConditionalGet
use Rack::ETag
```
