require "active_support/core_ext/integer/time"

Rails.application.configure do
  config.enable_reloading = true
  config.eager_load = false
  config.consider_all_requests_local = true

  # Caching
  if Rails.root.join("tmp/caching-dev.txt").exist?
    config.action_controller.perform_caching = true
    config.cache_store = :memory_store
  else
    config.action_controller.perform_caching = false
    config.cache_store = :null_store
  end

  # Logging
  config.log_level = :debug
  config.log_tags = [:request_id]

  # Active Record
  config.active_record.migration_error = :page_load
  config.active_record.verbose_query_logs = true
end
