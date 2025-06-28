import os

from celery import Celery

redis_url = os.environ.get('REDISTOGO_URL', 'redis://localhost:6379')

celery_app = Celery(
    'tally_job_scheduler',
    broker=redis_url,
    backend=redis_url,
    include=['tally_job_scheduler.services']
)

celery_app.conf.update(
    task_track_started=True,
)