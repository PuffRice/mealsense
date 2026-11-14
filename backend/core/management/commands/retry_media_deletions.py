from django.core.management.base import BaseCommand

from core.models import MediaDeletionJob
from core.services import process_media_deletion, prune_expired_records


class Command(BaseCommand):
    help = 'Retry pending deletion of private media objects and prune expired idempotency/orphan records.'

    def handle(self, *args, **options):
        job_ids = list(MediaDeletionJob.objects.filter(completed_at__isnull=True).values_list('pk', flat=True))
        for job_id in job_ids:
            process_media_deletion(job_id)
        remaining = MediaDeletionJob.objects.filter(completed_at__isnull=True).count()
        pruned = prune_expired_records()
        self.stdout.write(
            f'Processed {len(job_ids)} jobs; {remaining} still pending; '
            f'pruned {pruned["idempotency_records"]} idempotency records and {pruned["orphan_images"]} orphan images.'
        )
