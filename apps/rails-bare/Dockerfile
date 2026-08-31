FROM ruby:3.4-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential pkg-config default-libmysqlclient-dev curl \
 && rm -rf /var/lib/apt/lists/*
COPY Gemfile Gemfile.lock* ./
RUN bundle install --jobs 4 && bundle clean --force
COPY . .
ENV MALLOC_ARENA_MAX=2
EXPOSE 3000
CMD ["bundle", "exec", "puma", "-C", "config/puma.rb"]
