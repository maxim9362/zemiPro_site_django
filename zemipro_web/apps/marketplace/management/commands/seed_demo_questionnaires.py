"""Safe manually invoked seed for draft examples, optional explicit publishing."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.marketplace.models import ServiceQuestionnaire, Subcategory
from apps.marketplace.questionnaire_examples import DEMO_QUESTIONNAIRES
from apps.marketplace.questionnaire_services import publish_questionnaire
from apps.marketplace.questionnaires import validate_question_schema


class Command(BaseCommand):
    help = 'Stage 02.5: create 4 example drafts; --publish explicitly creates versions'

    def add_arguments(self, parser):
        parser.add_argument('--plan', action='store_true')
        parser.add_argument('--check', action='store_true')
        parser.add_argument('--publish', action='store_true')

    def handle(self, *args, **options):
        if options['plan'] and (options['check'] or options['publish']):
            raise CommandError('--plan is exclusive')
        if options['check'] and options['publish']:
            raise CommandError('--check and --publish cannot be combined')
        seen = set()
        for category_slug, service_slug, schema in DEMO_QUESTIONNAIRES:
            if (category_slug, service_slug) in seen:
                raise CommandError('Duplicate questionnaire service in manifest')
            seen.add((category_slug, service_slug))
            validate_question_schema(schema)
        if options['plan']:
            self.stdout.write(f'PLAN: {len(seen)} questionnaires; no database writes')
            return

        created = published = missing = 0
        with transaction.atomic():
            for category_slug, service_slug, schema in DEMO_QUESTIONNAIRES:
                service = Subcategory.objects.filter(
                    category__slug=category_slug, slug=service_slug,
                ).first()
                if service is None:
                    raise CommandError(
                        f'Missing service {category_slug}/{service_slug}; seed catalog first'
                    )
                obj = ServiceQuestionnaire.objects.filter(service=service).first()
                if obj is None:
                    if options['check']:
                        missing += 1
                        continue
                    obj = ServiceQuestionnaire.objects.create(
                        service=service, draft_schema=schema,
                    )
                    created += 1
                # Never overwrite administrator edits of existing drafts.
                if options['check'] and not obj.draft_schema:
                    missing += 1
                if options['publish']:
                    _, fresh = publish_questionnaire(obj.pk)
                    published += int(fresh)

            if missing:
                raise CommandError(f'Questionnaire drafts missing/empty: {missing}')

        self.stdout.write(self.style.SUCCESS(
            f'Questionnaires OK: {len(seen)} drafts, created {created}, '
            f'new versions {published}'
        ))
