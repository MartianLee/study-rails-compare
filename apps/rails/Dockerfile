FROM ruby:3.4-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential pkg-config default-libmysqlclient-dev curl git \
 && rm -rf /var/lib/apt/lists/*
ENV BUNDLE_WITHOUT=development:test BUNDLE_DEPLOYMENT=false
# Gemfile.lock is committed; `frozen` makes bundler refuse to resolve anything else
COPY Gemfile Gemfile.lock ./
RUN bundle config set --local frozen true && bundle install --jobs 4 && bundle clean --force
COPY . .
ENV RAILS_ENV=production \
    RAILS_LOG_TO_STDOUT=1 \
    SECRET_KEY_BASE=benchmark_only_not_a_secret_0000000000000000000000000000 \
    MALLOC_ARENA_MAX=2
RUN bundle exec bootsnap precompile --gemfile app/ config/ 2>/dev/null || true
EXPOSE 3000
CMD ["bundle", "exec", "puma", "-C", "config/puma.rb"]
