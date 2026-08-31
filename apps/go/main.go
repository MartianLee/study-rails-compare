// Go "full": Gin + GORM — the mainstream Go web framework and the mainstream Go ORM.
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

type User struct {
	ID        uint64 `gorm:"primaryKey"`
	Name      string
	Email     string
	Bio       *string
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Tag struct {
	ID   uint64 `gorm:"primaryKey"`
	Name string
	Slug string
}

type Post struct {
	ID            uint64 `gorm:"primaryKey"`
	UserID        uint64
	Title         string
	Slug          string
	Body          string
	Status        string
	ViewCount     int
	CommentsCount int
	PublishedAt   *time.Time
	CreatedAt     time.Time
	UpdatedAt     time.Time
	User          User  `gorm:"foreignKey:UserID"`
	Tags          []Tag `gorm:"many2many:post_tags;joinForeignKey:post_id;joinReferences:tag_id"`
}

type Comment struct {
	ID        uint64 `gorm:"primaryKey"`
	PostID    uint64
	UserID    uint64
	Body      string
	CreatedAt time.Time
	UpdatedAt time.Time
	User      User `gorm:"foreignKey:UserID"`
}

type authorJSON struct {
	ID   uint64 `json:"id"`
	Name string `json:"name"`
}
type tagJSON struct {
	Name string `json:"name"`
	Slug string `json:"slug"`
}
type postJSON struct {
	ID           uint64     `json:"id"`
	Title        string     `json:"title"`
	Slug         string     `json:"slug"`
	Excerpt      string     `json:"excerpt"`
	PublishedAt  *string    `json:"published_at"`
	ViewCount    int        `json:"view_count"`
	CommentCount int        `json:"comment_count"`
	Author       authorJSON `json:"author"`
	Tags         []tagJSON  `json:"tags"`
}
type commentJSON struct {
	ID        uint64     `json:"id"`
	Body      string     `json:"body"`
	CreatedAt string     `json:"created_at"`
	Author    authorJSON `json:"author"`
}
type postDetailJSON struct {
	postJSON
	Body     string        `json:"body"`
	Comments []commentJSON `json:"comments"`
}

const excerptLen = 160

func excerpt(s string) string {
	r := []rune(s)
	if len(r) <= excerptLen {
		return s
	}
	return string(r[:excerptLen])
}

func iso(t *time.Time) *string {
	if t == nil {
		return nil
	}
	s := t.UTC().Format("2006-01-02T15:04:05Z")
	return &s
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func toPostJSON(p *Post) postJSON {
	tags := make([]tagJSON, 0, len(p.Tags))
	for _, t := range p.Tags {
		tags = append(tags, tagJSON{Name: t.Name, Slug: t.Slug})
	}
	return postJSON{
		ID: p.ID, Title: p.Title, Slug: p.Slug, Excerpt: excerpt(p.Body),
		PublishedAt: iso(p.PublishedAt), ViewCount: p.ViewCount, CommentCount: p.CommentsCount,
		Author: authorJSON{ID: p.User.ID, Name: p.User.Name}, Tags: tags,
	}
}

func main() {
	pool, _ := strconv.Atoi(env("DB_POOL", "5"))
	dsn := fmt.Sprintf("%s:%s@tcp(%s:3306)/%s?charset=utf8mb4&parseTime=true&loc=UTC",
		env("DB_USER", "bench"), env("DB_PASSWORD", "bench"),
		env("DB_HOST", "mysql"), env("DB_NAME", "blogbench"))

	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger:                 logger.Default.LogMode(logger.Silent),
		SkipDefaultTransaction: true,
		PrepareStmt:            true,
	})
	if err != nil {
		log.Fatal(err)
	}
	sqlDB, _ := db.DB()
	sqlDB.SetMaxOpenConns(pool)
	sqlDB.SetMaxIdleConns(pool)

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/healthz", func(c *gin.Context) { c.JSON(200, gin.H{"ok": true}) })

	// 3 statements: posts page, Preload(User), Preload(Tags)
	r.GET("/api/posts", func(c *gin.Context) {
		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		if page < 1 {
			page = 1
		}
		var posts []Post
		if err := db.Preload("User").Preload("Tags").
			Where("status = ?", "published").
			Order("published_at DESC, id DESC").
			Limit(20).Offset((page - 1) * 20).Find(&posts).Error; err != nil {
			c.JSON(500, gin.H{"error": err.Error()})
			return
		}
		out := make([]postJSON, 0, len(posts))
		for i := range posts {
			out = append(out, toPostJSON(&posts[i]))
		}
		c.JSON(200, out)
	})

	// 5 statements: post, Preload(User), Preload(Tags), comments, comment authors
	r.GET("/api/posts/:id", func(c *gin.Context) {
		id, _ := strconv.ParseUint(c.Param("id"), 10, 64)
		var p Post
		if err := db.Preload("User").Preload("Tags").First(&p, id).Error; err != nil {
			c.JSON(404, gin.H{"error": "not found"})
			return
		}
		var comments []Comment
		if err := db.Preload("User").Where("post_id = ?", id).
			Order("id DESC").Limit(20).Find(&comments).Error; err != nil {
			c.JSON(500, gin.H{"error": err.Error()})
			return
		}
		cs := make([]commentJSON, 0, len(comments))
		for i := range comments {
			cm := &comments[i]
			cs = append(cs, commentJSON{ID: cm.ID, Body: cm.Body,
				CreatedAt: cm.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
				Author:    authorJSON{ID: cm.User.ID, Name: cm.User.Name}})
		}
		c.JSON(200, postDetailJSON{postJSON: toPostJSON(&p), Body: p.Body, Comments: cs})
	})

	// write path: normalise, validate, insert, bump the counter — all in one transaction
	r.POST("/api/comments", func(c *gin.Context) {
		var in struct {
			PostID uint64 `json:"post_id"`
			UserID uint64 `json:"user_id"`
			Body   string `json:"body"`
		}
		if err := c.ShouldBindJSON(&in); err != nil {
			c.JSON(400, gin.H{"error": "bad json"})
			return
		}
		body := normalise(in.Body)
		if body == "" || len([]rune(body)) > 2000 {
			c.JSON(422, gin.H{"errors": []string{"body is invalid"}})
			return
		}
		cm := Comment{PostID: in.PostID, UserID: in.UserID, Body: body}
		err := db.Transaction(func(tx *gorm.DB) error {
			if err := tx.Create(&cm).Error; err != nil {
				return err
			}
			return tx.Model(&Post{}).Where("id = ?", in.PostID).
				UpdateColumn("comments_count", gorm.Expr("comments_count + 1")).Error
		})
		if err != nil {
			c.JSON(500, gin.H{"error": err.Error()})
			return
		}
		c.JSON(201, gin.H{"id": cm.ID, "post_id": cm.PostID, "user_id": cm.UserID, "body": cm.Body})
	})

	srv := &http.Server{Addr: ":" + env("PORT", "3000"), Handler: r}
	log.Fatal(srv.ListenAndServe())
}

func normalise(s string) string {
	out := make([]rune, 0, len(s))
	sp := false
	for _, r := range s {
		if r == ' ' || r == '\t' || r == '\n' || r == '\r' {
			sp = true
			continue
		}
		if sp && len(out) > 0 {
			out = append(out, ' ')
		}
		sp = false
		out = append(out, r)
	}
	return string(out)
}
