from django.urls import path
from blog import views

urlpatterns = [
    path("healthz", views.healthz),
    path("api/posts", views.post_list),
    path("api/posts/<int:post_id>", views.post_detail),
    path("api/comments", views.create_comment),
]
