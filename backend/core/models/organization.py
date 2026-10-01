"""Local organization created in VHS (§11, §12). Never imported from the platform."""

from django.db import models
from django.db.models.functions import Lower

from core.models.video import Video


class Tag(models.Model):
    """A personal tag. Platform tags stay in Video.platform_metadata and are never copied."""

    name = models.CharField(max_length=60)
    slug = models.SlugField(max_length=80, unique=True)
    color = models.CharField(max_length=7)
    videos = models.ManyToManyField(Video, related_name="tags", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("name"), name="unique_tag_name_ci")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Collection(models.Model):
    """A user-ordered group of videos, independent of any platform playlist."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    # The cover is the local thumbnail of a video in the collection (no image uploads).
    cover_video = models.ForeignKey(
        Video, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    videos = models.ManyToManyField(
        Video, through="CollectionVideo", related_name="collections", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CollectionVideo(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="collection_items")
    position = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "video"], name="unique_video_per_collection"
            ),
            # Deferred: a reorder renumbers every row inside one transaction.
            models.UniqueConstraint(
                fields=["collection", "position"],
                name="unique_position_per_collection",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]
        ordering = ["position"]

    def __str__(self):
        return f"{self.collection_id}#{self.position}: {self.video_id}"
