"""Safe visible-content metadata for Stage 09 public pages."""
import json


def _json_script(value):
    serialized = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return serialized.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def page_metadata(request, *, title, description, breadcrumbs=(), service=None,
                  city=None, profile=None):
    canonical = request.build_absolute_uri(request.path)
    graph = [{
        '@type': 'WebPage',
        '@id': canonical,
        'url': canonical,
        'name': title,
        'description': description,
        'inLanguage': request.LANGUAGE_CODE,
    }]
    items = []
    for position, crumb in enumerate(breadcrumbs, 1):
        item = {
            '@type': 'ListItem', 'position': position, 'name': str(crumb['label']),
        }
        if crumb.get('url'):
            item['item'] = request.build_absolute_uri(crumb['url'])
        items.append(item)
    if items:
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': items})
    if service is not None:
        structured = {
            '@type': 'Service',
            'name': service.localized_name,
            'description': description,
            'serviceType': service.localized_name,
            'url': canonical,
        }
        if city is not None:
            structured['areaServed'] = {
                '@type': 'City', 'name': city.localized_name,
            }
        graph.append(structured)
    if profile is not None:
        graph.append({
            '@type': 'ProfilePage',
            'mainEntity': {
                '@type': 'Person' if profile.provider_type == 'individual' else 'Organization',
                'name': profile.public_display_name,
                'description': profile.public_description,
            },
        })
    return {
        'seo_title': title,
        'seo_description': description,
        'seo_og_type': 'profile' if profile is not None else 'website',
        'seo_json_ld': _json_script({
            '@context': 'https://schema.org', '@graph': graph,
        }),
    }
