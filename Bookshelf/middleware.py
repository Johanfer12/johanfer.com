"""Middleware comunes del sitio."""


class HeadWithoutBodyMiddleware:
    """Una respuesta a HEAD sale sin cuerpo, con las cabeceras del GET.

    Django responde a HEAD como a GET y deja que sea el servidor quien descarte
    el cuerpo. Gunicorn lo descarta, pero lo anota en el journal ("WSGI app sent
    body bytes on a no-body response"), y el monitor de disponibilidad hace un
    HEAD a la portada cada 30 minutos: 48 avisos al día en la SD por nada. Va el
    primero de la lista para ser el último en tocar la respuesta; el
    Content-Length que ya llevara se conserva, como pide la norma para HEAD.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == 'HEAD':
            if response.streaming:
                response.streaming_content = []
            else:
                length = response.get('Content-Length')
                response.content = b''
                if length is not None:
                    response['Content-Length'] = length
        return response
