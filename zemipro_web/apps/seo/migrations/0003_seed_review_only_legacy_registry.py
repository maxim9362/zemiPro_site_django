from django.db import migrations


EVIDENCE = 'docs/SEO_URL_INVENTORY.csv; Stage09.1 external HTTP/GSC pending'
ROWS = (
    ('/', 'home'),
    ('/master/lachish/', 'region_hub'),
    ('/master/center/', 'region_hub'),
    ('/master/remont-strojka/', 'category_hub'),
    ('/master/lachish/remont-strojka/', 'region_category_hub'),
    ('/master/center/remont-strojka/', 'region_category_hub'),
    ('/master/lachish/event/', 'region_category_hub'),
    ('/master/lachish/remont-strojka/santehnika/', 'service_page'),
    ('/master/lachish/remont-strojka/kompleksnyj-remont-kvartiry/', 'service_page'),
    ('/master/center/remont-strojka/lestnitsy/', 'service_page'),
    ('/master/lachish/event/fotografy/', 'service_page'),
    ('/master/lachish/mastera-po-remontu/bytovaya-tehnika/', 'service_page'),
    ('/master/lachish/yuristy-buhgalter/yuristy/', 'service_page'),
    ('/master/lachish/krasota-zdorove/makiyazh/', 'service_page'),
    ('/master/lachish/mastera-po-remontu/remont-velosipedov/', 'service_page'),
    ('/master/center/avto/tonirovka-avto/', 'service_page'),
    ('/master/center/krasota-zdorove/parfyumeriya-i-kosmetika/', 'service_page'),
    ('/master/center/yuristy-buhgalter/yuristy/', 'service_page'),
    ('/master/center/perevozki/gruzchiki/', 'service_page'),
    ('/master/center/krasota-zdorove/stilist-imidzhmejker/', 'service_page'),
    ('/master/center/remont-strojka/kompleksnyj-remont-kvartiry/', 'service_page'),
)


def seed_registry(apps, schema_editor):
    model = apps.get_model('seo', 'SeoLegacyUrl')
    for path, page_type in ROWS:
        model.objects.get_or_create(
            path=path,
            defaults={
                'page_type': page_type,
                'decision': 'review',
                'evidence_source': EVIDENCE,
                'is_active': False,
            },
        )


def unseed_registry(apps, schema_editor):
    model = apps.get_model('seo', 'SeoLegacyUrl')
    model.objects.filter(
        path__in=[row[0] for row in ROWS],
        decision='review', is_active=False, evidence_source=EVIDENCE,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [('seo', '0002_seocontentpage_seo_published_has_timestamp_and_more')]
    operations = [migrations.RunPython(seed_registry, unseed_registry)]
