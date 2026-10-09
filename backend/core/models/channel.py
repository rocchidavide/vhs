from django.db import models


class Channel(models.Model):
    """The source channel of archived videos: metadata and a library filter.

    Subscriptions (auto-download, polling) are post-MVP and would add fields here.
    """

    name = models.CharField(max_length=255)
    # A key of engine.platforms, checked by the services: no choices, so that a new platform
    # needs no migration.
    platform = models.CharField(max_length=32)
    platform_id = models.CharField(max_length=128)
    url = models.URLField(max_length=2048, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "platform_id"], name="unique_channel_per_platform"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name
