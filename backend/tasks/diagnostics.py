import logging

logger = logging.getLogger("vhs.tasks")


def ping() -> str:
    """Smoke-test task to check that the django-q2 worker is running."""
    logger.info("ping received by worker")
    return "pong"
