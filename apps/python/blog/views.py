"""Django "full": Django ORM + JsonResponse.

Deliberately no Django REST Framework: DRF is an optional extra layer, while
Active Record is not optional in Rails. Django ORM objects + a hand-built dict
is the same shape as the Rails controller in this repo.
"""
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse, HttpResponse

from .models import Comment, Post

EXCERPT = 160
PER_PAGE = 20


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _shape(post):
    return {
        "id": post.id,
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.body[:EXCERPT],
        "published_at": _iso(post.published_at),
        "view_count": post.view_count,
        "comment_count": post.comments_count,
        "author": {"id": post.user.id, "name": post.user.name},
        # prefetched through the join model, so this is two statements rather
        # than one join — matching Active Record's HABTM and GORM's many2many.
        "tags": [{"name": pt.tag.name, "slug": pt.tag.slug} for pt in post.posttag_set.all()],
    }


def healthz(_request):
    return JsonResponse({"ok": True})


def post_list(request):
    """3 statements: posts page, prefetch user, prefetch tags."""
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    offset = (page - 1) * PER_PAGE
    posts = (
        Post.objects.filter(status="published")
        .order_by("-published_at", "-id")
        .prefetch_related("user", "posttag_set__tag")[offset:offset + PER_PAGE]
    )
    return JsonResponse([_shape(p) for p in posts], safe=False)


def post_detail(_request, post_id):
    """5 statements."""
    posts = list(Post.objects.filter(pk=post_id).prefetch_related("user", "posttag_set__tag"))
    if not posts:
        return JsonResponse({"error": "not found"}, status=404)
    post = posts[0]
    comments = list(
        Comment.objects.filter(post_id=post_id).order_by("-id").prefetch_related("user")[:20]
    )
    payload = _shape(post)
    payload["body"] = post.body
    payload["comments"] = [
        {
            "id": c.id,
            "body": c.body,
            "created_at": _iso(c.created_at),
            "author": {"id": c.user.id, "name": c.user.name},
        }
        for c in comments
    ]
    return JsonResponse(payload)


def create_comment(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "bad json"}, status=400)

    from django.utils import timezone

    now = timezone.now()
    comment = Comment(
        post_id=payload.get("post_id"),
        user_id=payload.get("user_id"),
        body=payload.get("body") or "",
        created_at=now,
        updated_at=now,
    )
    try:
        comment.full_clean(exclude=["post", "user"], validate_constraints=False)
    except ValidationError as e:
        return JsonResponse({"errors": [m for ms in e.message_dict.values() for m in ms]}, status=422)

    with transaction.atomic():
        comment.save(force_insert=True)
        Post.objects.filter(pk=comment.post_id).update(comments_count=F("comments_count") + 1)

    return JsonResponse(
        {"id": comment.id, "post_id": comment.post_id, "user_id": comment.user_id, "body": comment.body},
        status=201,
    )
