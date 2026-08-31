require_relative "boot"

require "rails"
require "active_model/railtie"
require "active_record/railtie"
require "action_controller/railtie"

Bundler.require(*Rails.groups)

module Blogbench
  class Application < Rails::Application
    config.load_defaults 8.1
    config.api_only = true
    config.eager_load = true

    # Rails 7.2+ turns YJIT on by default. Keep that, but let the harness
    # measure with it off so the JIT's contribution is visible rather than assumed.
    config.yjit = ENV["RAILS_YJIT"] != "0"

    config.time_zone = "UTC"
    config.active_record.default_timezone = :utc

    config.logger = ActiveSupport::Logger.new($stdout)
    config.log_level = :warn
    config.active_record.verbose_query_logs = false

    # No migrations in this repo: the schema is loaded from db/schema.sql, the
    # same file every other stack reads.
    config.active_record.maintain_test_schema = false
  end
end
