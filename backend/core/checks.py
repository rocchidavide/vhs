from django.conf import settings
from django.core.checks import Error, Warning, register
from django.utils.translation import gettext


@register()
def q_cluster_retry_check(app_configs, **kwargs):
    """A task must not be redelivered while the first attempt is still running."""
    conf = getattr(settings, "Q_CLUSTER", {})
    timeout = conf.get("timeout")
    retry = conf.get("retry")
    if not timeout or not retry or retry <= timeout:
        return [
            Error(
                "Q_CLUSTER: 'timeout' and 'retry' must be set, with retry > timeout.",
                hint="Set VHS_TASK_TIMEOUT and VHS_TASK_RETRY accordingly.",
                id="vhs.E001",
            )
        ]
    return []


@register()
def library_available_check(app_configs, **kwargs):
    """Report at startup when the library cannot be used (never creates anything)."""
    from django.db import DatabaseError

    from services.library_service import library_state

    try:
        info = library_state()
    except DatabaseError:
        return []  # Before migrations: nothing to report yet.
    if info.usable:
        return []
    return [
        Warning(
            gettext("Library not available ({state}): {message}").format(
                state=info.state, message=info.message
            ),
            hint=gettext("VHS does not write to the library until this state is resolved."),
            id="vhs.W002",
        )
    ]


@register()
def insecure_cookies_check(app_configs, **kwargs):
    """Make an explicit plain-HTTP install visible outside development."""
    if settings.DEBUG or settings.VHS_SECURE_COOKIES:
        return []
    return [
        Warning(
            "DJANGO_SECURE_COOKIES=false: login credentials and the session cookie are sent "
            "without encryption over HTTP.",
            hint="Only acceptable on a trusted local network. Use HTTPS to protect them.",
            id="vhs.W001",
        )
    ]
