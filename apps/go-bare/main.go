// Go "bare": net/http + database/sql + encoding/json. Same three SQL statements
// as the Gin+GORM app, hand-written. No framework, no ORM.
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
)

var db *sql.DB

type author struct {
	ID   uint64 `json:"id"`
	Name string `json:"name"`
}
type tag struct {
	Name string `json:"name"`
	Slug string `json:"slug"`
}
type postOut struct {
	ID           uint64  `json:"id"`
	Title        string  `json:"title"`
	Slug         string  `json:"slug"`
	Excerpt      string  `json:"excerpt"`
	PublishedAt  *string `json:"published_at"`
	ViewCount    int     `json:"view_count"`
	CommentCount int     `json:"comment_count"`
	Author       author  `json:"author"`
	Tags         []tag   `json:"tags"`
}
type commentOut struct {
	ID        uint64 `json:"id"`
	Body      string `json:"body"`
	CreatedAt string `json:"created_at"`
	Author    author `json:"author"`
}
type postDetail struct {
	postOut
	Body     string       `json:"body"`
	Comments []commentOut `json:"comments"`
}

const excerptLen = 160

func excerpt(s string) string {
	r := []rune(s)
	if len(r) <= excerptLen {
		return s
	}
	return string(r[:excerptLen])
}

func iso(t sql.NullTime) *string {
	if !t.Valid {
		return nil
	}
	s := t.Time.UTC().Format("2006-01-02T15:04:05Z")
	return &s
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func placeholders(n int) string {
	return strings.TrimSuffix(strings.Repeat("?,", n), ",")
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

// loadAuthors and loadTags are statements 2 and 3.
func loadAuthors(ids []any) (map[uint64]author, error) {
	m := map[uint64]author{}
	if len(ids) == 0 {
		return m, nil
	}
	rows, err := db.Query("SELECT id, name FROM users WHERE id IN ("+placeholders(len(ids))+")", ids...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var a author
		if err := rows.Scan(&a.ID, &a.Name); err != nil {
			return nil, err
		}
		m[a.ID] = a
	}
	return m, rows.Err()
}

// loadTags is deliberately two statements, not a join: GORM's many2many preload
// loads the join rows first and the tags second, so the bare app does the same.
func loadTags(ids []any) (map[uint64][]tag, error) {
	m := map[uint64][]tag{}
	if len(ids) == 0 {
		return m, nil
	}
	rows, err := db.Query(
		"SELECT post_id, tag_id FROM post_tags WHERE post_id IN ("+placeholders(len(ids))+")", ids...)
	if err != nil {
		return nil, err
	}
	type link struct{ post, tag uint64 }
	var links []link
	var tagIDs []any
	seen := map[uint64]bool{}
	for rows.Next() {
		var l link
		if err := rows.Scan(&l.post, &l.tag); err != nil {
			rows.Close()
			return nil, err
		}
		links = append(links, l)
		if !seen[l.tag] {
			seen[l.tag] = true
			tagIDs = append(tagIDs, l.tag)
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(tagIDs) == 0 {
		return m, nil
	}
	trows, err := db.Query(
		"SELECT id, name, slug FROM tags WHERE id IN ("+placeholders(len(tagIDs))+")", tagIDs...)
	if err != nil {
		return nil, err
	}
	defer trows.Close()
	byID := map[uint64]tag{}
	for trows.Next() {
		var id uint64
		var t tag
		if err := trows.Scan(&id, &t.Name, &t.Slug); err != nil {
			return nil, err
		}
		byID[id] = t
	}
	for _, l := range links {
		m[l.post] = append(m[l.post], byID[l.tag])
	}
	return m, trows.Err()
}

func handleList(w http.ResponseWriter, r *http.Request) {
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	rows, err := db.Query(
		"SELECT id, user_id, title, slug, body, view_count, comments_count, published_at "+
			"FROM posts WHERE status = ? ORDER BY published_at DESC, id DESC LIMIT 20 OFFSET ?",
		"published", (page-1)*20)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	out := make([]postOut, 0, 20)
	var uids, pids []any
	seen := map[uint64]bool{}
	for rows.Next() {
		var p postOut
		var uid uint64
		var body string
		var pub sql.NullTime
		if err := rows.Scan(&p.ID, &uid, &p.Title, &p.Slug, &body, &p.ViewCount, &p.CommentCount, &pub); err != nil {
			rows.Close()
			writeJSON(w, 500, map[string]string{"error": err.Error()})
			return
		}
		p.Excerpt, p.PublishedAt, p.Author.ID = excerpt(body), iso(pub), uid
		out = append(out, p)
		pids = append(pids, p.ID)
		if !seen[uid] {
			seen[uid] = true
			uids = append(uids, uid)
		}
	}
	rows.Close()
	authors, err := loadAuthors(uids)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	tags, err := loadTags(pids)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	for i := range out {
		out[i].Author = authors[out[i].Author.ID]
		if t := tags[out[i].ID]; t != nil {
			out[i].Tags = t
		} else {
			out[i].Tags = []tag{}
		}
	}
	writeJSON(w, 200, out)
}

func handleDetail(w http.ResponseWriter, r *http.Request, id uint64) {
	var p postOut
	var uid uint64
	var body string
	var pub sql.NullTime
	err := db.QueryRow(
		"SELECT id, user_id, title, slug, body, view_count, comments_count, published_at FROM posts WHERE id = ?", id).
		Scan(&p.ID, &uid, &p.Title, &p.Slug, &body, &p.ViewCount, &p.CommentCount, &pub)
	if err != nil {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	p.Excerpt, p.PublishedAt = excerpt(body), iso(pub)
	authors, err := loadAuthors([]any{uid})
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	p.Author = authors[uid]
	tags, _ := loadTags([]any{p.ID})
	if p.Tags = tags[p.ID]; p.Tags == nil {
		p.Tags = []tag{}
	}

	rows, err := db.Query(
		"SELECT id, user_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id DESC LIMIT 20", id)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	cs := make([]commentOut, 0, 20)
	var cuids []any
	cseen := map[uint64]bool{}
	for rows.Next() {
		var c commentOut
		var cuid uint64
		var ct time.Time
		if err := rows.Scan(&c.ID, &cuid, &c.Body, &ct); err != nil {
			rows.Close()
			writeJSON(w, 500, map[string]string{"error": err.Error()})
			return
		}
		c.CreatedAt, c.Author.ID = ct.UTC().Format("2006-01-02T15:04:05Z"), cuid
		cs = append(cs, c)
		if !cseen[cuid] {
			cseen[cuid] = true
			cuids = append(cuids, cuid)
		}
	}
	rows.Close()
	cauthors, _ := loadAuthors(cuids)
	for i := range cs {
		cs[i].Author = cauthors[cs[i].Author.ID]
	}
	writeJSON(w, 200, postDetail{postOut: p, Body: body, Comments: cs})
}

func normalise(s string) string {
	return strings.Join(strings.Fields(s), " ")
}

func handleCreate(w http.ResponseWriter, r *http.Request) {
	var in struct {
		PostID uint64 `json:"post_id"`
		UserID uint64 `json:"user_id"`
		Body   string `json:"body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeJSON(w, 400, map[string]string{"error": "bad json"})
		return
	}
	body := normalise(in.Body)
	if body == "" || len([]rune(body)) > 2000 {
		writeJSON(w, 422, map[string]any{"errors": []string{"body is invalid"}})
		return
	}
	tx, err := db.Begin()
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	now := time.Now().UTC()
	res, err := tx.Exec(
		"INSERT INTO comments (post_id, user_id, body, created_at, updated_at) VALUES (?,?,?,?,?)",
		in.PostID, in.UserID, body, now, now)
	if err == nil {
		_, err = tx.Exec("UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?", in.PostID)
	}
	if err != nil {
		tx.Rollback()
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	if err := tx.Commit(); err != nil {
		writeJSON(w, 500, map[string]string{"error": err.Error()})
		return
	}
	id, _ := res.LastInsertId()
	writeJSON(w, 201, map[string]any{"id": id, "post_id": in.PostID, "user_id": in.UserID, "body": body})
}

func main() {
	pool, _ := strconv.Atoi(env("DB_POOL", "5"))
	dsn := fmt.Sprintf("%s:%s@tcp(%s:3306)/%s?charset=utf8mb4&parseTime=true&loc=UTC",
		env("DB_USER", "bench"), env("DB_PASSWORD", "bench"),
		env("DB_HOST", "mysql"), env("DB_NAME", "blogbench"))
	var err error
	db, err = sql.Open("mysql", dsn)
	if err != nil {
		log.Fatal(err)
	}
	db.SetMaxOpenConns(pool)
	db.SetMaxIdleConns(pool)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]bool{"ok": true})
	})
	mux.HandleFunc("/api/posts", handleList)
	mux.HandleFunc("/api/comments", handleCreate)
	mux.HandleFunc("/api/posts/", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseUint(strings.TrimPrefix(r.URL.Path, "/api/posts/"), 10, 64)
		if err != nil {
			writeJSON(w, 404, map[string]string{"error": "not found"})
			return
		}
		handleDetail(w, r, id)
	})
	log.Fatal((&http.Server{Addr: ":" + env("PORT", "3000"), Handler: mux}).ListenAndServe())
}
