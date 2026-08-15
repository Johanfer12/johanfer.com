from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone as dj_timezone

from .middleware import VisitLogMiddleware, get_client_ip
from .models import OwnerSignature
from .visit_stats import invalidate_badge


@receiver(user_logged_in)
def record_owner_signature(sender, request, user, **kwargs):
    """Nadie más usa el login, así que quien entra por ahí soy yo: anotar sus señas."""
    try:
        ip = get_client_ip(request) or ''
        visitor_id = (request.session.get(VisitLogMiddleware.SESSION_VISITOR_KEY) or '').strip()
        if not ip and not visitor_id:
            return

        signature, created = OwnerSignature.objects.get_or_create(
            ip_address=ip,
            visitor_id=visitor_id,
        )
        if not created:
            OwnerSignature.objects.filter(pk=signature.pk).update(
                last_seen=dj_timezone.now(),
            )
        invalidate_badge()
    except Exception:
        # Un fallo aquí nunca debe impedir el login.
        pass
