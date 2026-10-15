# Load the Celery app with Django so @shared_task binds to it (and its broker
# settings) in the web process too, not only in the worker.
from .celery import app as celery_app

__all__ = ("celery_app",)
