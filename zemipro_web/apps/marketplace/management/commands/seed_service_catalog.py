"""Stage 02.1 additive Django catalog seed (no legacy imports or deletes)."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.marketplace.catalog_seed import (
    NEW_CATEGORIES, REPAIR_CATEGORY_NAMES, REPAIR_SERVICE_NAMES, SECTIONS,
)
from apps.marketplace.models import Category, ServiceSection, Subcategory
from .seed_repair_categories import CATEGORIES_DATA


def localized_fields(names, *, kind, russian_description=None):
    ru, en, he = names
    if not all(isinstance(v, str) and v.strip() for v in names):
        raise CommandError(f'{kind}: all RU/EN/HE names are required')
    descriptions = (
        russian_description or f'Услуги: {ru}',
        f'Information about {en} services',
        f'מידע על שירותי {he}',
    )
    return {
        **dict(zip(('name_ru', 'name_en', 'name_he'), names)),
        **dict(zip(('description_ru', 'description_en', 'description_he'), descriptions)),
        **{f'seo_title_{lang}': f'{name} | ZemiPro'
           for lang, name in zip(('ru', 'en', 'he'), names)},
        **{f'seo_description_{lang}': description
           for lang, description in zip(('ru', 'en', 'he'), descriptions)},
    }


def build_seed_plan():
    """Pure/deterministic manifest; validates slugs and translations before writes."""
    import re
    sections = []
    categories = []
    section_seen = set()
    category_seen = set()

    for index, (slug, ru, en, he) in enumerate(SECTIONS):
        if slug in section_seen:
            raise CommandError(f'Duplicate section slug: {slug}')
        section_seen.add(slug)
        fields = localized_fields((ru, en, he), kind=f'section {slug}')
        fields['slug'] = slug
        fields['sort_order'] = (index + 1) * 10
        sections.append(fields)

    repair_names = {slug: (en, he) for slug, en, he in REPAIR_CATEGORY_NAMES}
    service_names = {slug: (en, he) for slug, en, he in REPAIR_SERVICE_NAMES}
    if len(repair_names) != len(REPAIR_CATEGORY_NAMES):
        raise CommandError('Duplicate repair category translations')
    if len(service_names) != len(REPAIR_SERVICE_NAMES):
        raise CommandError('Duplicate repair service translations')

    for source in CATEGORIES_DATA:
        slug = source['slug']
        if slug not in repair_names:
            raise CommandError(f'Missing repair category translation: {slug}')
        en, he = repair_names[slug]
        fields = localized_fields(
            (source['name_ru'], en, he), kind=f'category {slug}',
            russian_description=source['description'],
        )
        fields['description'] = fields.pop('description_ru')
        fields.update({
            'slug': slug, 'emoji': source['emoji'],
            'sort_order': source['sort_order'], 'work_mode': 'onsite',
        })
        services = []
        for index, (ru_name, service_slug) in enumerate(source['subcategories']):
            if service_slug not in service_names:
                raise CommandError(f'Missing repair service translation: {service_slug}')
            service_en, service_he = service_names[service_slug]
            service = localized_fields(
                (ru_name, service_en, service_he), kind=f'service {service_slug}',
            )
            service.update({
                'slug': service_slug, 'sort_order': (index + 1) * 10,
                'work_mode': 'onsite',
            })
            services.append(service)
        categories.append(('repairs', fields, services))

    for source in NEW_CATEGORIES:
        fields = localized_fields(
            (source['ru'], source['en'], source['he']),
            kind=f"category {source['slug']}",
        )
        fields['description'] = fields.pop('description_ru')
        fields.update({
            'slug': source['slug'],
            'sort_order': 100,
            'work_mode': source['mode'],
            'emoji': '',
        })
        services = []
        for index, (slug, ru, en, he) in enumerate(source['services']):
            item = localized_fields((ru, en, he), kind=f'service {slug}')
            item.update({
                'slug': slug, 'sort_order': (index + 1) * 10,
                'work_mode': source['mode'],
            })
            services.append(item)
        categories.append((source['section'], fields, services))

    for section_slug, category, services in categories:
        slug = category['slug']
        if section_slug not in section_seen:
            raise CommandError(f'Unknown section for category {slug}: {section_slug}')
        if slug in category_seen:
            raise CommandError(f'Duplicate category slug: {slug}')
        category_seen.add(slug)
        service_seen = set()
        for service in services:
            if service['slug'] in service_seen:
                raise CommandError(f"Duplicate service slug in {slug}: {service['slug']}")
            service_seen.add(service['slug'])

    for slug in [
        *section_seen, *category_seen,
        *(service['slug'] for _, _, services in categories for service in services)
    ]:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or len(slug) > 50:
            raise CommandError(f'Unsafe or oversized catalog slug: {slug}')

    return sections, categories


def fill_missing(instance, fields, *, check):
    """Keep admin edits, is_active, IDs, slugs and sort order unchanged."""
    missing = []
    for name in (
        'name_en', 'name_he', 'description', 'description_ru', 'description_en', 'description_he',
        'seo_title_ru', 'seo_title_en', 'seo_title_he',
        'seo_description_ru', 'seo_description_en', 'seo_description_he',
    ):
        if hasattr(instance, name) and not getattr(instance, name):
            missing.append(name)
            if not check:
                setattr(instance, name, fields[name])
    if not check and missing:
        instance.save(update_fields=missing)
    return bool(missing)


class Command(BaseCommand):
    help = 'Additive idempotent catalog: 12 sections, 8 preserved repair categories, new services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--plan', action='store_true', help='Validate embedded seed without DB writes'
        )
        parser.add_argument(
            '--check', action='store_true', help='Verify already seeded DB; never write'
        )

    def handle(self, *args, **options):
        sections, categories = build_seed_plan()
        expected_services = sum(len(services) for _, _, services in categories)
        if options['plan']:
            self.stdout.write(
                f'PLAN: {len(sections)} sections, {len(categories)} categories, '
                f'{expected_services} services; no changes'
            )
            return

        created = {'sections': 0, 'categories': 0, 'services': 0}
        missing = 0
        with transaction.atomic():
            section_by_slug = {}
            for values in sections:
                slug = values['slug']
                if options['check']:
                    section = ServiceSection.objects.filter(slug=slug).first()
                    if section is None:
                        missing += 1
                        continue
                    missing += fill_missing(section, values, check=True)
                else:
                    section, inserted = ServiceSection.objects.get_or_create(
                        slug=slug, defaults={k: v for k, v in values.items() if k != 'slug'}
                    )
                    created['sections'] += inserted
                    if not inserted:
                        fill_missing(section, values, check=False)
                section_by_slug[slug] = section

            for section_slug, values, services in categories:
                slug = values['slug']
                section = section_by_slug.get(section_slug)
                if section is None:
                    missing += 1
                    continue
                if options['check']:
                    category = Category.objects.filter(slug=slug).first()
                    if category is None:
                        missing += 1
                        continue
                    missing += fill_missing(category, values, check=True)
                else:
                    category, inserted = Category.objects.get_or_create(
                        slug=slug,
                        defaults={
                            **{k: v for k, v in values.items() if k != 'slug'},
                            'section': section,
                        },
                    )
                    created['categories'] += inserted
                    if not inserted:
                        fill_missing(category, values, check=False)

                if category.section_id not in (None, section.pk):
                    raise CommandError(
                        f'Category {slug} is assigned to another section; '
                        'no silent re-parenting permitted'
                    )
                if category.section_id is None:
                    if options['check']:
                        missing += 1
                    else:
                        category.section = section
                        category.save(update_fields=['section'])

                for service_values in services:
                    service_slug = service_values['slug']
                    if options['check']:
                        service = Subcategory.objects.filter(
                            category=category, slug=service_slug
                        ).first()
                        if service is None:
                            missing += 1
                            continue
                        missing += fill_missing(service, service_values, check=True)
                    else:
                        service, inserted = Subcategory.objects.get_or_create(
                            category=category,
                            slug=service_slug,
                            defaults={
                                k: v for k, v in service_values.items() if k != 'slug'
                            },
                        )
                        created['services'] += inserted
                        if not inserted:
                            fill_missing(service, service_values, check=False)

            if options['check'] and missing:
                raise CommandError(f'Catalog incomplete: {missing} missing/blank item(s)')
        self.stdout.write(self.style.SUCCESS(
            f'Catalog OK: {len(sections)} sections, {len(categories)} categories, '
            f'{expected_services} services. Created: {created}'
        ))
