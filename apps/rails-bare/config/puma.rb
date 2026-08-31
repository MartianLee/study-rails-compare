threads_count = Integer(ENV.fetch("RAILS_MAX_THREADS", 1))
threads threads_count, threads_count

# WEB_CONCURRENCY=1 means one process, no cluster master — the same thing
# node's cluster check does, so the two runtimes are configured alike.
web_concurrency = Integer(ENV.fetch("WEB_CONCURRENCY", 1))
if web_concurrency > 1
  workers web_concurrency
  preload_app!
else
  workers 0
end

bind "tcp://0.0.0.0:#{ENV.fetch('PORT', 3000)}"
environment "production"
log_requests false
quiet


