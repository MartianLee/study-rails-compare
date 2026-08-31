from django.core.exceptions import ValidationError
from django.db import models


class User(models.Model):
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=190)
    bio = models.TextField(null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "users"
        managed = False


class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.CharField(max_length=50)

    class Meta:
        db_table = "tags"
        managed = False


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column="user_id",
                             related_name="posts")
    title = models.CharField(max_length=200)
    slug = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20)
    view_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    published_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    tags = models.ManyToManyField(Tag, through="PostTag", related_name="posts")

    class Meta:
        db_table = "posts"
        managed = False


class PostTag(models.Model):
    post = models.ForeignKey(Post, on_delete=models.DO_NOTHING, db_column="post_id")
    tag = models.ForeignKey(Tag, on_delete=models.DO_NOTHING, db_column="tag_id")

    class Meta:
        db_table = "post_tags"
        managed = False


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.DO_NOTHING, db_column="post_id",
                             related_name="comments")
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column="user_id",
                             related_name="comments")
    body = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "comments"
        managed = False

    def clean(self):
        # the Django equivalent of Rails' before_validation + validates
        self.body = " ".join((self.body or "").split())
        if not self.body:
            raise ValidationError({"body": "can't be blank"})
        if len(self.body) > 2000:
            raise ValidationError({"body": "is too long (maximum is 2000 characters)"})
