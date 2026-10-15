from django.urls import path

from .views import MediaFileView, MediaItemView, MediaListView, MediaReorderView

urlpatterns = []
for kind in ("photos", "documents"):
    urlpatterns += [
        path(f"jobs/<int:pk>/{kind}/", MediaListView.as_view(kind=kind), name=f"{kind}-list"),
        path(f"jobs/<int:pk>/{kind}/reorder/", MediaReorderView.as_view(kind=kind), name=f"{kind}-reorder"),
        path(f"jobs/<int:pk>/{kind}/<int:item_id>/", MediaItemView.as_view(kind=kind), name=f"{kind}-item"),
        path(f"jobs/<int:pk>/{kind}/<int:item_id>/file/", MediaFileView.as_view(kind=kind), name=f"{kind}-file"),
        path(
            f"jobs/<int:pk>/{kind}/<int:item_id>/thumb/",
            MediaFileView.as_view(kind=kind, thumb=True),
            name=f"{kind}-thumb",
        ),
    ]
