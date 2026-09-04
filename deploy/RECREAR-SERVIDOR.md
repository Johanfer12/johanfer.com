# Recrear el servidor desde cero

Todo lo que vive en la Raspberry **fuera del repositorio** y que un `git clone`
no reproduce. Si la SD muere, esto es lo que hay que rehacer.

Levantado del estado real de la máquina en **agosto de 2026**. Si cambias algo en
el servidor, cámbialo también aquí: los ficheros de esta carpeta son la copia
maestra, y en la Pi hay que instalarlos a mano porque `deploy.sh` no los toca.

---

## 1. Lo que hay que respaldar (no se puede regenerar)

| Qué | Dónde | Tamaño | Se puede regenerar |
|---|---|---|---|
| Base de datos | `/home/johan/My_Bookshelf/database.db` | 12 MB | **No** |
| Portadas de libros | `/home/johan/My_Bookshelf/media/` | 9,5 MB | Sí, rascando Goodreads otra vez |
| Certificados SSL | `/home/johan/ssl/` | 12 KB | Sí, reemitiéndolos en Cloudflare |
| Claves y tokens | `/home/johan/My_Bookshelf/.env` | — | **No** (hay que pedirlas de nuevo) |
| Umbrales de fail2ban | `/etc/fail2ban/jail.d/*.local` | — | Sí, pero hay que reafinarlos |
| Vectores | `/var/lib/qdrant/storage/` | 37 MB | Sí, pero cuesta una llamada a Gemini por noticia |

> **Este repositorio es público.** Ni el `.env` ni los umbrales de fail2ban se
> versionan: los valores concretos de baneo le dirían a un escáner a qué ritmo
> puede sondear sin que lo bloqueen.
>
> Pero sí están respaldados, porque el proyecto vive dentro de OneDrive. Los
> ficheros están en disco y sincronizados, y `.gitignore` solo impide que suban
> a GitHub:
>
> - `.env` — claves y tokens
> - `deploy/fail2ban/jail.d/*.local` — umbrales de baneo y la IP de casa
>
> Al clonar el repo en una máquina nueva **no aparecerán**: hay que traerlos de
> OneDrive. En el repo queda la estructura y el procedimiento, que es lo que de
> verdad cuesta reconstruir de memoria.

La base de datos es lo único verdaderamente irrecuperable: dentro están las
noticias, los libros y el histórico de Spotify.

Los vectores de Qdrant sí se pueden reconstruir sin respaldo: `python manage.py
qdrant_backfill` los regenera y `retry_missing_embeddings` recupera los que
fallen. Solo cuesta cuota de API y tiempo.

---

## 2. Orden de instalación

### 2.1 Paquetes base

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx fail2ban ufw logrotate
```

### 2.2 Qdrant

**No viene por apt.** Es un binario suelto que corre como servicio propio, y es
la pieza que más fácil se olvida al recrear la máquina: sin ella no hay
detección de duplicados.

```bash
sudo mkdir -p /opt/qdrant /var/lib/qdrant/storage
sudo curl -L -o /opt/qdrant/qdrant \
  https://github.com/qdrant/qdrant/releases/download/v1.15.4/qdrant-aarch64-unknown-linux-musl
sudo chmod +x /opt/qdrant/qdrant
sudo chown -R johan:johan /var/lib/qdrant
sudo cp deploy/qdrant.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now qdrant
curl -s http://127.0.0.1:6333/collections   # debe responder
```

Escucha solo en `127.0.0.1`. No abrir el 6333 al exterior.

### 2.3 El proyecto

```bash
cd /home/johan
git clone https://github.com/Johanfer12/johanfer.com.git My_Bookshelf
cd My_Bookshelf
python3 -m venv env && source env/bin/activate
pip install -U pip setuptools wheel && pip install -r requirements.txt

cp deploy/env.example .env    # y rellenarlo con las claves reales
# restaurar aquí database.db y media/ desde la copia de seguridad
python manage.py migrate
python manage.py collectstatic --noinput
```

### 2.4 Gunicorn

```bash
sudo cp deploy/my_bookshelf.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now my_bookshelf
```

`deploy.sh` hace `sudo systemctl restart` sin pedir contraseña: el usuario
`johan` necesita sudo sin password para ese comando.

### 2.5 Nginx

El orden importa: los ficheros de `conf.d/` definen variables que usa el sitio.
Sin ellos nginx no arranca con un `unknown variable`.

```bash
sudo cp deploy/nginx/conf.d/*.conf /etc/nginx/conf.d/
sudo cp deploy/nginx/my_bookshelf.conf /etc/nginx/sites-available/my_bookshelf
sudo ln -sf /etc/nginx/sites-available/my_bookshelf /etc/nginx/sites-enabled/

# Los dos mapas tienen que existir aunque estén vacíos, o nginx falla al leerlos
sudo touch /etc/nginx/blacklisted-ips.map /etc/nginx/bad_uri_map.conf

sudo nginx -t && sudo systemctl reload nginx
```

Los certificados van en `/home/johan/ssl/` (`johanfer.com.pem` y `.key`), son
los *origin certificates* de Cloudflare.

### 2.6 fail2ban

```bash
sudo cp deploy/bin/fail2ban-nginx-map /usr/local/sbin/
sudo chown root:root /usr/local/sbin/fail2ban-nginx-map
sudo chmod 0755 /usr/local/sbin/fail2ban-nginx-map

sudo cp deploy/fail2ban/filter.d/*.conf /etc/fail2ban/filter.d/
sudo cp deploy/fail2ban/action.d/*.conf /etc/fail2ban/action.d/

# Los jail.d/*.local NO vienen en el clon (están gitignorados). Cópialos desde
# OneDrive antes de este paso; ver deploy/fail2ban/jail.d/README.md.
# Entre ellos va home-ip-ignore.local con la IP de casa: sin ese, te autobaneas
# navegando por tu propio sitio.
sudo cp deploy/fail2ban/jail.d/*.local /etc/fail2ban/jail.d/

sudo systemctl restart fail2ban && sudo fail2ban-client status
```

En vez de tocar iptables, las jaulas escriben en `/etc/nginx/blacklisted-ips.map`
y nginx devuelve `444` (cierra sin responder) a las IPs de esa lista.

### 2.7 Cortafuegos

Política por defecto ALLOW. Los puertos 80/443 solo aceptan la LAN y los rangos
de Cloudflare, de modo que los escáneres de internet no llegan ni al handshake.

```bash
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow from 192.168.1.0/24 to any port 80,443 proto tcp comment 'LAN'
for cidr in $(curl -s https://www.cloudflare.com/ips-v4); do
  sudo ufw allow from "$cidr" to any port 80,443 proto tcp comment 'Cloudflare'
done
sudo ufw enable && sudo ufw status numbered
```

Si Cloudflare añade rangos y el sitio deja de responder por dominio pero sí por
LAN, volver a lanzar ese bucle.

### 2.8 Cron y logs

```bash
cd /home/johan/My_Bookshelf && source env/bin/activate
python manage.py crontab add
crontab -l

sudo cp deploy/logrotate-bookshelf-cron /etc/logrotate.d/bookshelf-cron
sudo /usr/sbin/logrotate --debug /etc/logrotate.d/bookshelf-cron
```

`crontab add` genera las cuatro líneas de Django con el marcador
`# django-cronjobs for Bookshelf` y la redirección a
`/home/johan/log_cron_bookshelf.txt`. Las líneas ajenas (LED ACT, Cloudflare,
wifi_watchdog, PowerSave-USB) hay que reponerlas a mano; ver §3.

### 2.9 Ajustes de la máquina

```bash
sudo cp deploy/sysctl-99-swappiness.conf /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system

sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp deploy/journald-size-limit.conf /etc/systemd/journald.conf.d/size-limit.conf
sudo systemctl restart systemd-journald
```

El swap lo gestiona `dphys-swapfile`, no fstab (~453 MB sobre la SD).

### 2.10 El script de despliegue

```bash
cp deploy/deploy.sh /home/johan/deploy.sh && chmod +x /home/johan/deploy.sh
```

Va fuera del repo a propósito: hace `git checkout .` y no puede estar dentro de
lo que revierte.

---

## 3. Cosas ajenas al proyecto que están en la misma máquina

No son de esta aplicación, pero comparten crontab y se perderían igual:

- `/home/johan/actualizar_cloudflare.sh` — DNS dinámico, cada 10 min. **No versionado.**
- `/home/johan/wifi_watchdog.sh` — reconecta el WiFi, cada 5 min. **No versionado.**
- `/usr/local/bin/update_bad_uri_blocklist.py` — alimenta `bad_uri_map.conf`. **No versionado.**
- Líneas del crontab que apagan y encienden el LED ACT (22:00 y 09:00).
- `@reboot ... buspower` — apaga el bus USB entero para ahorrar energía, con
  `sleep 120` que deja dos minutos para enchufar un teclado tras arrancar.
  Revertir en caliente: `echo 1 | sudo tee /sys/devices/platform/soc/3f980000.usb/buspower`

Convendría respaldar esos tres scripts junto con el `.env`.

---

## 4. Comprobación final

```bash
systemctl is-active qdrant my_bookshelf nginx fail2ban
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/noticias/   # 200
curl -s -o /dev/null -w '%{http_code}\n' https://johanfer.com/noticias/    # 200
crontab -l | grep -c 'django-cronjobs'                                      # 4
python manage.py shell -c "from my_news.models import News; print(News.objects.count())"
```

La primera petición tras reiniciar puede tardar ~20 s: es el arranque en frío de
gunicorn con `--preload` en una Pi 3. No es un fallo.
