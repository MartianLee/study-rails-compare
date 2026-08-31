#!/usr/bin/env bash
# Rebuild the benchmark database from scratch. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f db/seed.sql ] || { echo "generating db/seed.sql ..."; python3 db/gen_seed.py > db/seed.sql; }

echo "loading schema ..."
docker compose exec -T mysql mysql -uroot -proot blogbench < db/schema.sql
echo "loading seed (this takes a minute) ..."
docker compose exec -T mysql mysql -uroot -proot blogbench < db/seed.sql
docker compose exec -T mysql mysql -uroot -proot blogbench -e "ANALYZE TABLE users, posts, comments, tags, post_tags;" >/dev/null
docker compose exec -T mysql mysql -uroot -proot blogbench -e "
  SELECT 'users' t, COUNT(*) n FROM users
  UNION ALL SELECT 'posts', COUNT(*) FROM posts
  UNION ALL SELECT 'published', COUNT(*) FROM posts WHERE status='published'
  UNION ALL SELECT 'comments', COUNT(*) FROM comments
  UNION ALL SELECT 'tags', COUNT(*) FROM tags
  UNION ALL SELECT 'post_tags', COUNT(*) FROM post_tags;"
