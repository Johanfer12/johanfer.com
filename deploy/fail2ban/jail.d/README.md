# Jaulas de fail2ban

Los ficheros `jail.d/*.local` **están en esta carpeta pero no se versionan**:
los valores afinados (cuántos fallos, en cuánto tiempo, cuánto dura el baneo) le
dirían a un escáner a qué ritmo puede sondear sin que lo bloqueen, y este
repositorio es público.

Siguen respaldados porque el proyecto vive dentro de OneDrive: el fichero está
en disco y sincronizado, y `.gitignore` solo impide que suba a GitHub. Si clonas
el repo en una máquina nueva **no estarán**; hay que traerlos de OneDrive.

Igual que el `.env`, que también está aquí al lado y también ignorado.

## Qué hay que reponer en `/etc/fail2ban/jail.d/`

| Fichero | Qué hace |
|---|---|
| `nginx-400.local` | Banea por ráfagas de respuestas 400 |
| `nginx-404.local` | Banea por ráfagas de 404 (los escaneos de rutas de WordPress y demás) |
| `nginx-444.local` | Banea a quien ya cayó en el bloqueo por URI o por lista negra |
| `nginx-realip-map.local` | Sustituye la acción de las tres por `nginx-block-map-safe` y reajusta la de 404. Se carga el último por orden alfabético, así que sus valores mandan |
| `home-ip-ignore.local` | `[DEFAULT] ignoreip` con la IP fija de casa. **Imprescindible**: sin ella te autobaneas navegando |

Las tres jaulas comparten forma:

```ini
[nginx-4XX]
enabled = true
port = http,https
filter = nginx-4XX          # los filtros SÍ están versionados, en filter.d/
logpath = /var/log/nginx/access.log
maxretry = <en la copia de seguridad>
findtime = <en la copia de seguridad>
bantime  = <en la copia de seguridad>
backend = auto
action = nginx-block-map-safe[blck_lst_file=/etc/nginx/blacklisted-ips.map]
```

## Cómo funciona el bloqueo

No se tocan iptables. La acción `nginx-block-map-safe` (ver `../action.d/` y
`../bin/fail2ban-nginx-map`) escribe las IPs en `/etc/nginx/blacklisted-ips.map`,
que nginx lee con un `geo` y responde `444`: cierra la conexión sin dar ni un
código de estado del que aprender.

Cada jaula tiene su propio fichero de estado en `/run`, y el mapa final es la
unión de todos: desbanear en una no borra los baneos de las otras.

## Comprobar

```bash
sudo fail2ban-client status
sudo fail2ban-client status nginx-404
```
