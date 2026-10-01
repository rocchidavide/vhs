"""Django admin registrations (read-only: changes go through the services)."""

from django.contrib import admin

from core.models import Channel, Collection, Download, Tag, Video


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Channel)
class ChannelAdmin(ReadOnlyAdmin):
    list_display = ["name", "platform", "platform_id"]
    search_fields = ["name", "platform_id"]


@admin.register(Video)
class VideoAdmin(ReadOnlyAdmin):
    list_display = ["title", "platform_id", "channel", "local_status", "source_status"]
    list_filter = ["platform", "local_status", "source_status"]
    search_fields = ["title", "platform_id"]


@admin.register(Download)
class DownloadAdmin(ReadOnlyAdmin):
    list_display = ["id", "video", "status", "progress", "error_code", "created_at"]
    list_filter = ["status", "error_code"]
    list_select_related = ["video"]


@admin.register(Tag)
class TagAdmin(ReadOnlyAdmin):
    list_display = ["name", "slug", "color"]
    search_fields = ["name"]


@admin.register(Collection)
class CollectionAdmin(ReadOnlyAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
