"""Safe, explicit and idempotent Israel geographic baseline seed (Stage 02.2)."""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.locations.geo_seed import ALIASES, CITIES, DISTRICTS
from apps.locations.models import City, CityAlias, District


def validate_manifest():
    """Validate all static identifiers and translations before any writes."""
    districts = []
    cities = []
    aliases = []
    all_district_slugs = set()
    all_city_slugs = set()
    all_alias_slugs = set()
    valid_slug = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')

    for slug, ru, en, he in DISTRICTS:
        if slug in all_district_slugs:
            raise CommandError(f'Duplicate district slug: {slug}')
        all_district_slugs.add(slug)
        districts.append((slug, {'name_ru': ru, 'name_en': en, 'name_he': he}))

    for slug, ru, en, he, district_slug in CITIES:
        if slug in all_city_slugs:
            raise CommandError(f'Duplicate city slug: {slug}')
        if district_slug not in all_district_slugs:
            raise CommandError(f'Unknown district for city {slug}: {district_slug}')
        all_city_slugs.add(slug)
        cities.append((
            slug, district_slug, {'name_ru': ru, 'name_en': en, 'name_he': he}
        ))

    for alias_slug, city_slug in ALIASES:
        if alias_slug in all_alias_slugs or alias_slug in all_city_slugs:
            raise CommandError(f'Conflicting alias slug: {alias_slug}')
        if city_slug not in all_city_slugs:
            raise CommandError(f'Unknown alias target: {city_slug}')
        all_alias_slugs.add(alias_slug)
        aliases.append((alias_slug, city_slug))

    for slug in (*all_district_slugs, *all_city_slugs, *all_alias_slugs):
        if len(slug) > 50 or not valid_slug.fullmatch(slug):
            raise CommandError(f'Unsafe geography slug: {slug}')

    for _, values in districts:
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise CommandError('District translations must be non-empty')
    for _, _, values in cities:
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise CommandError('City translations must be non-empty')
    return districts, cities, aliases


def missing_names(instance, names, *, check):
    missing = [key for key, value in names.items() if not getattr(instance, key)]
    if not check and missing:
        for key in missing:
            setattr(instance, key, names[key])
        instance.save(update_fields=missing)
    return len(missing)


class Command(BaseCommand):
    help = 'Seed 6 districts and 25 existing pilot cities, preserving IDs and admin edits'

    def add_arguments(self, parser):
        parser.add_argument('--plan', action='store_true', help='Validate manifest without DB access')
        parser.add_argument('--check', action='store_true', help='Validate DB state without writes')

    def handle(self, *args, **options):
        districts, cities, aliases = validate_manifest()
        if options['plan']:
            self.stdout.write(
                f'PLAN: {len(districts)} districts, {len(cities)} cities, '
                f'{len(aliases)} aliases; no database writes'
            )
            return

        check = options['check']
        created = {'districts': 0, 'cities': 0, 'aliases': 0}
        missing = 0
        with transaction.atomic():
            district_by_slug = {}
            for slug, values in districts:
                district = District.objects.filter(slug=slug).first()
                if district is None:
                    if check:
                        missing += 1
                        continue
                    district = District.objects.create(slug=slug, **values)
                    created['districts'] += 1
                else:
                    missing += missing_names(district, values, check=check)
                district_by_slug[slug] = district

            city_by_slug = {}
            for slug, district_slug, values in cities:
                district = district_by_slug.get(district_slug)
                if district is None:
                    missing += 1
                    continue
                city = City.objects.filter(slug=slug).first()
                if city is None:
                    if check:
                        missing += 1
                        continue
                    city = City.objects.create(slug=slug, district=district, **values)
                    created['cities'] += 1
                else:
                    if city.district_id not in (None, district.pk):
                        raise CommandError(
                            f'City {slug} belongs to a different district; '
                            'no automatic re-parenting is allowed'
                        )
                    missing += missing_names(city, values, check=check)
                    if city.district_id is None:
                        if check:
                            missing += 1
                        else:
                            city.district = district
                            city.save(update_fields=['district'])
                city_by_slug[slug] = city

            for alias_slug, city_slug in aliases:
                city = city_by_slug.get(city_slug)
                if city is None:
                    missing += 1
                    continue
                # Never allow an alias to shadow a canonical slug, including
                # slugs of administrator-created cities outside this manifest.
                if City.objects.filter(slug=alias_slug).exists():
                    raise CommandError(f'Alias conflicts with canonical city: {alias_slug}')
                alias = CityAlias.objects.filter(slug=alias_slug).first()
                if alias is None:
                    if check:
                        missing += 1
                        continue
                    CityAlias.objects.create(slug=alias_slug, city=city)
                    created['aliases'] += 1
                elif alias.city_id != city.pk:
                    raise CommandError(f'Alias {alias_slug} points to a different city')

            if check and missing:
                raise CommandError(f'Incomplete geography: {missing} missing item(s)/translation(s)')

        self.stdout.write(self.style.SUCCESS(
            f'Geography OK: {len(districts)} districts, {len(cities)} cities, '
            f'{len(aliases)} aliases. Created: {created}'
        ))
