from django.conf import settings


def site_branding(request):
    return {
        'site_name': settings.SITE_NAME,
        'site_tagline': settings.SITE_TAGLINE,
        'site_meta_description': settings.SITE_META_DESCRIPTION,
    }
