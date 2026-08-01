"""Obtiene el access token de Simkl por flujo PIN.

Se corre a mano una sola vez (el token dura ~5 años y no hay refresh):

    python manage.py simkl_auth

Imprime un código, se escribe en https://simkl.com/pin, y al autorizar muestra el
token para pegarlo en el .env como SIMKL_ACCESS_TOKEN.
"""

import time

from django.core.management.base import BaseCommand, CommandError

from watching import simkl


class Command(BaseCommand):
    help = "Autentica contra Simkl por flujo PIN y muestra el access token."

    def handle(self, *args, **options):
        pin = simkl.request_pin()
        user_code = pin.get('user_code')
        if not user_code:
            raise CommandError(f"Simkl no devolvió un código: {pin}")

        interval = int(pin.get('interval') or 5)
        expires_in = int(pin.get('expires_in') or 900)

        self.stdout.write("")
        self.stdout.write(f"  Abre  {pin.get('verification_uri') or simkl.PIN_VERIFICATION_URL}")
        self.stdout.write(self.style.SUCCESS(f"  Código:  {user_code}"))
        self.stdout.write(f"  (vence en {expires_in // 60} minutos)")
        self.stdout.write("")

        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            result = simkl.check_pin(user_code)
            token = result.get('access_token')
            if token:
                self.stdout.write(self.style.SUCCESS("\nAutorizado. Agregá esto al .env:\n"))
                self.stdout.write(f"SIMKL_ACCESS_TOKEN={token}\n")
                return
            if result.get('device_code'):
                raise CommandError("El código expiró o se invalidó. Volvé a correr el comando.")
            self.stdout.write(f"  ... {result.get('message') or 'esperando'}")
            time.sleep(interval)

        raise CommandError("Se agotó el tiempo del PIN.")
