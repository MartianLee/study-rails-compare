Rails.application.configure do
  config.cache_classes = true if config.respond_to?(:cache_classes=)
  config.enable_reloading = false
  config.eager_load = true
  config.consider_all_requests_local = false
  config.log_level = :warn
  config.active_support.report_deprecations = false
  config.active_record.dump_schema_after_migration = false
end
