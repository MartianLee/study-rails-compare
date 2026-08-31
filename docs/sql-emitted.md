# The SQL every stack actually emits

Captured from MySQL's own `general_log` by `harness/verify.py`, one request per
endpoint. `Prepare` rows are dropped (a prepared statement is logged twice);
what is left is one line per statement executed for that request.

Formatting differs — every ORM writes SQL in its own dialect of backticks and
aliases — but the **statement set is identical**: 4 for the list, 6 for the
detail, hitting the same tables with the same predicates.

## `rails` — Rails 8 + Active Record

`GET /api/posts?page=3` — 4 statements

```sql
SELECT `posts`.* FROM `posts` WHERE `posts`.`status` = 'published' ORDER BY `posts`.`published_at` DESC, `posts`.`id` DESC LIMIT 20 OFFSET 40
SELECT `users`.* FROM `users` WHERE `users`.`id` IN (305, 143, 375, 146, 266, 320, 193, 301, 194, 206, 316, 60, 111, 339, 190, 104, 362, 128, 392, 3)
SELECT `post_tags`.* FROM `post_tags` WHERE `post_tags`.`post_id` IN (4960, 4959, 4957, 4956, 4955, 4954, 4953, 4952, 4951, 4950, 4949, 4948, 4947, 4945, 4944, 4942, 4941, 4940, 4939, 4938)
SELECT `tags`.* FROM `tags` WHERE `tags`.`id` IN (5, 6, 17, 19, 35, 1, 27, 28, 31, 34, 24, 37, 26, 3, 10, 33, 11, 21, 23, 7, 9, 12, 22, 36, 39, 32, 16, 40, 29, 8, 15)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT `posts`.* FROM `posts` WHERE `posts`.`id` = 4321 LIMIT 1
SELECT `users`.* FROM `users` WHERE `users`.`id` = 426
SELECT `post_tags`.* FROM `post_tags` WHERE `post_tags`.`post_id` = 4321
SELECT `tags`.* FROM `tags` WHERE `tags`.`id` IN (12, 31, 32, 35)
SELECT `comments`.* FROM `comments` WHERE `comments`.`post_id` = 4321 ORDER BY `comments`.`id` DESC LIMIT 20
SELECT `users`.* FROM `users` WHERE `users`.`id` IN (216, 437, 358, 285, 156, 410, 181, 340, 304, 193, 380, 463, 489, 219)
```

## `rails-bare` — Rack + raw SQL

`GET /api/posts?page=3` — 4 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE status = 'published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET 40
SELECT id, name FROM users WHERE id IN (305,143,375,146,266,320,193,301,194,206,316,60,111,339,190,104,362,128,392,3)
SELECT post_tags.post_id, post_tags.tag_id FROM post_tags WHERE post_tags.post_id IN (4960,4959,4957,4956,4955,4954,4953,4952,4951,4950,4949,4948,4947,4945,4944,4942,4941,4940,4939,4938)
SELECT id, name, slug FROM tags WHERE id IN (5,6,17,19,35,1,27,28,31,34,24,37,26,3,10,33,11,21,23,7,9,12,22,36,39,32,16,40,29,8,15)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE id = 4321
SELECT id, name FROM users WHERE id IN (426)
SELECT post_tags.post_id, post_tags.tag_id FROM post_tags WHERE post_tags.post_id IN (4321)
SELECT id, name, slug FROM tags WHERE id IN (12,31,32,35)
SELECT id, user_id, body, created_at FROM comments WHERE post_id = 4321 ORDER BY id DESC LIMIT 20
SELECT id, name FROM users WHERE id IN (216,437,358,285,156,410,181,340,304,193,380,463,489,219)
```

## `node` — Express + Sequelize

`GET /api/posts?page=3` — 4 statements

```sql
SELECT `id`, `user_id`, `title`, `slug`, `body`, `status`, `view_count`, `comments_count`, `published_at`, `created_at`, `updated_at` FROM `posts` AS `Post` WHERE `Post`.`status` = 'published' ORDER BY `Post`.`published_at` DESC, `Post`.`id` DESC LIMIT 40, 20
SELECT `id`, `name` FROM `users` AS `User` WHERE `User`.`id` IN (305, 143, 375, 146, 266, 320, 193, 301, 194, 206, 316, 60, 111, 339, 190, 104, 362, 128, 392, 3)
SELECT `post_id`, `tag_id` FROM `post_tags` AS `PostTag` WHERE `PostTag`.`post_id` IN (4960, 4959, 4957, 4956, 4955, 4954, 4953, 4952, 4951, 4950, 4949, 4948, 4947, 4945, 4944, 4942, 4941, 4940, 4939, 4938)
SELECT `id`, `name`, `slug` FROM `tags` AS `Tag` WHERE `Tag`.`id` IN ('5', '6', '17', '19', '35', '1', '27', '28', '31', '34', '24', '37', '26', '3', '10', '33', '11', '21', '23', '7', '9', '12', '22', '36', '39', '32', '16', '40', '29', '8', '15')
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT `id`, `user_id`, `title`, `slug`, `body`, `status`, `view_count`, `comments_count`, `published_at`, `created_at`, `updated_at` FROM `posts` AS `Post` WHERE `Post`.`id` = '4321'
SELECT `id`, `name` FROM `users` AS `User` WHERE `User`.`id` IN (426)
SELECT `post_id`, `tag_id` FROM `post_tags` AS `PostTag` WHERE `PostTag`.`post_id` IN (4321)
SELECT `id`, `name`, `slug` FROM `tags` AS `Tag` WHERE `Tag`.`id` IN ('12', '31', '32', '35')
SELECT `id`, `post_id`, `user_id`, `body`, `created_at`, `updated_at` FROM `comments` AS `Comment` WHERE `Comment`.`post_id` = 4321 ORDER BY `Comment`.`id` DESC LIMIT 20
SELECT `id`, `name` FROM `users` AS `User` WHERE `User`.`id` IN (216, 437, 358, 285, 156, 410, 181, 340, 304, 193, 380, 463, 489, 219)
```

## `node-bare` — node:http + raw SQL

`GET /api/posts?page=3` — 4 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at\n FROM posts WHERE status = 'published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET 40
SELECT id, name FROM users WHERE id IN (305,143,375,146,266,320,193,301,194,206,316,60,111,339,190,104,362,128,392,3)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4960,4959,4957,4956,4955,4954,4953,4952,4951,4950,4949,4948,4947,4945,4944,4942,4941,4940,4939,4938)
SELECT id, name, slug FROM tags WHERE id IN (5,6,17,19,35,1,27,28,31,34,24,37,26,3,10,33,11,21,23,7,9,12,22,36,39,32,16,40,29,8,15)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at\n FROM posts WHERE id = 4321
SELECT id, name FROM users WHERE id IN (426)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4321)
SELECT id, name, slug FROM tags WHERE id IN (12,31,32,35)
SELECT id, user_id, body, created_at FROM comments WHERE post_id = 4321 ORDER BY id DESC LIMIT 20
SELECT id, name FROM users WHERE id IN (216,437,358,285,156,410,181,340,304,193,380,463,489,219)
```

## `python` — Django + Django ORM

`GET /api/posts?page=3` — 4 statements

```sql
SELECT `posts`.`id`, `posts`.`user_id`, `posts`.`title`, `posts`.`slug`, `posts`.`body`, `posts`.`status`, `posts`.`view_count`, `posts`.`comments_count`, `posts`.`published_at`, `posts`.`created_at`, `posts`.`updated_at` FROM `posts` WHERE `posts`.`status` = 'published' ORDER BY `posts`.`published_at` DESC, `posts`.`id` DESC LIMIT 20 OFFSET 40
SELECT `users`.`id`, `users`.`name`, `users`.`email`, `users`.`bio`, `users`.`created_at`, `users`.`updated_at` FROM `users` WHERE `users`.`id` IN (128, 3, 392, 266, 143, 146, 301, 305, 60, 316, 190, 320, 193, 194, 206, 339, 104, 362, 111, 375)
SELECT `post_tags`.`id`, `post_tags`.`post_id`, `post_tags`.`tag_id` FROM `post_tags` WHERE `post_tags`.`post_id` IN (4960, 4959, 4957, 4956, 4955, 4954, 4953, 4952, 4951, 4950, 4949, 4948, 4947, 4945, 4944, 4942, 4941, 4940, 4939, 4938)
SELECT `tags`.`id`, `tags`.`name`, `tags`.`slug` FROM `tags` WHERE `tags`.`id` IN (1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 19, 21, 22, 23, 24, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36, 37, 39, 40)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT `posts`.`id`, `posts`.`user_id`, `posts`.`title`, `posts`.`slug`, `posts`.`body`, `posts`.`status`, `posts`.`view_count`, `posts`.`comments_count`, `posts`.`published_at`, `posts`.`created_at`, `posts`.`updated_at` FROM `posts` WHERE `posts`.`id` = 4321
SELECT `users`.`id`, `users`.`name`, `users`.`email`, `users`.`bio`, `users`.`created_at`, `users`.`updated_at` FROM `users` WHERE `users`.`id` IN (426)
SELECT `post_tags`.`id`, `post_tags`.`post_id`, `post_tags`.`tag_id` FROM `post_tags` WHERE `post_tags`.`post_id` IN (4321)
SELECT `tags`.`id`, `tags`.`name`, `tags`.`slug` FROM `tags` WHERE `tags`.`id` IN (32, 35, 12, 31)
SELECT `comments`.`id`, `comments`.`post_id`, `comments`.`user_id`, `comments`.`body`, `comments`.`created_at`, `comments`.`updated_at` FROM `comments` WHERE `comments`.`post_id` = 4321 ORDER BY `comments`.`id` DESC LIMIT 20
SELECT `users`.`id`, `users`.`name`, `users`.`email`, `users`.`bio`, `users`.`created_at`, `users`.`updated_at` FROM `users` WHERE `users`.`id` IN (193, 358, 489, 463, 304, 340, 437, 181, 216, 380, 410, 219, 156, 285)
```

## `python-bare` — WSGI + raw SQL

`GET /api/posts?page=3` — 4 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE status = 'published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET 40
SELECT id, name FROM users WHERE id IN (3,60,104,111,128,143,146,190,193,194,206,266,301,305,316,320,339,362,375,392)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4960,4959,4957,4956,4955,4954,4953,4952,4951,4950,4949,4948,4947,4945,4944,4942,4941,4940,4939,4938)
SELECT id, name, slug FROM tags WHERE id IN (1,3,5,6,7,8,9,10,11,12,15,16,17,19,21,22,23,24,26,27,28,29,31,32,33,34,35,36,37,39,40)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE id = 4321
SELECT id, name FROM users WHERE id IN (426)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4321)
SELECT id, name, slug FROM tags WHERE id IN (12,31,32,35)
SELECT id, user_id, body, created_at FROM comments WHERE post_id = 4321 ORDER BY id DESC LIMIT 20
SELECT id, name FROM users WHERE id IN (156,181,193,216,219,285,304,340,358,380,410,437,463,489)
```

## `go` — Gin + GORM

`GET /api/posts?page=3` — 4 statements

```sql
SELECT * FROM `posts` WHERE status = 'published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET 40
SELECT * FROM `post_tags` WHERE `post_tags`.`post_id` IN (4960,4959,4957,4956,4955,4954,4953,4952,4951,4950,4949,4948,4947,4945,4944,4942,4941,4940,4939,4938)
SELECT * FROM `tags` WHERE `tags`.`id` IN (5,6,17,19,35,1,27,28,31,34,24,37,26,3,10,33,11,21,23,7,9,12,22,36,39,32,16,40,29,8,15)
SELECT * FROM `users` WHERE `users`.`id` IN (305,143,375,146,266,320,193,301,194,206,316,60,111,339,190,104,362,128,392,3)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT * FROM `posts` WHERE `posts`.`id` = 4321 ORDER BY `posts`.`id` LIMIT 1
SELECT * FROM `post_tags` WHERE `post_tags`.`post_id` = 4321
SELECT * FROM `tags` WHERE `tags`.`id` IN (12,31,32,35)
SELECT * FROM `users` WHERE `users`.`id` = 426
SELECT * FROM `comments` WHERE post_id = 4321 ORDER BY id DESC LIMIT 20
SELECT * FROM `users` WHERE `users`.`id` IN (216,437,358,285,156,410,181,340,304,193,380,463,489,219)
```

## `go-bare` — net/http + database/sql

`GET /api/posts?page=3` — 4 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE status = 'published' ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET 40
SELECT id, name FROM users WHERE id IN (305,143,375,146,266,320,193,301,194,206,316,60,111,339,190,104,362,128,392,3)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4960,4959,4957,4956,4955,4954,4953,4952,4951,4950,4949,4948,4947,4945,4944,4942,4941,4940,4939,4938)
SELECT id, name, slug FROM tags WHERE id IN (5,6,17,19,35,1,27,28,31,34,24,37,26,3,10,33,11,21,23,7,9,12,22,36,39,32,16,40,29,8,15)
```

`GET /api/posts/4321` — 6 statements

```sql
SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE id = 4321
SELECT id, name FROM users WHERE id IN (426)
SELECT post_id, tag_id FROM post_tags WHERE post_id IN (4321)
SELECT id, name, slug FROM tags WHERE id IN (12,31,32,35)
SELECT id, user_id, body, created_at FROM comments WHERE post_id = 4321 ORDER BY id DESC LIMIT 20
SELECT id, name FROM users WHERE id IN (216,437,358,285,156,410,181,340,304,193,380,463,489,219)
```

