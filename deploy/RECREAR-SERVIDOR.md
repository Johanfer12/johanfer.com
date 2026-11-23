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
> Pero sí están respaldados en la copia privada del proyecto, fuera de GitHub;
> `.gitignore` solo impide que suban aquí:
>
> - `.env` — claves y tokens
> - `deploy/fail2ban/jail.d/*.local` — umbrales de baneo y la IP de casa
> - `/etc/johanfer-backup.env` — destino y credenciales de restic
>
> Al clonar el repo en una máquina nueva **no aparecerán**: hay que traerlos de
> esa copia. En el repo queda la estructura y el procedimiento, que es lo que de
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
# Antes, el tmpfs de los snapshots de deploy/fstab-tmpfs (ver 2.9): la unidad
# lo exige (RequiresMountsFor) y sin él Qdrant no arranca.
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
# (el storage de Qdrant se restaura aparte; ver 'Copias de seguridad')
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
# Nivel de log en INFO: el fail2ban.conf del paquete se dejó una vez en DEBUG y
# escribía ~8 MB por semana en la SD.
sudo cp deploy/fail2ban/fail2ban.local /etc/fail2ban/

# Los jail.d/*.local NO vienen en el clon (están gitignorados). Cópialos desde
# la copia privada antes de este paso; ver deploy/fail2ban/jail.d/README.md.
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

### 2.8 Tareas programadas y logs

Las tres tareas de la aplicación son temporizadores de systemd, no líneas del
crontab: noticias (cada 30 min de 08:00 a 21:30, y a las 22:00), libros (00:00)
y Simkl (00:30).

```bash
sudo install -m 644 -o root -g root deploy/systemd/johanfer-{news,books,watching}.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now johanfer-news.timer johanfer-books.timer johanfer-watching.timer
systemctl list-timers 'johanfer-*'

sudo cp deploy/logrotate-bookshelf-cron /etc/logrotate.d/bookshelf-cron
sudo /usr/sbin/logrotate --debug /etc/logrotate.d/bookshelf-cron
```

Cada servicio ejecuta un comando de gestión (`update_news`, `update_books`,
`update_watching`) y escribe en `/home/johan/log_cron_bookshelf.txt`. Si la
tarea falla, el comando termina con código 1 y la unidad aparece en
`systemctl --failed`. Para lanzar una pasada a mano:
`sudo systemctl start johanfer-news.service`.

Hasta octubre de 2026 esto lo hacía django-crontab con cuatro líneas en el
crontab de johan. Las líneas ajenas del crontab (LED ACT, Cloudflare,
wifi_watchdog, PowerSave-USB) siguen ahí y hay que reponerlas a mano; ver §3.

### 2.9 Ajustes de la máquina

```bash
sudo cp deploy/sysctl-99-swappiness.conf /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system

sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp deploy/journald-size-limit.conf /etc/systemd/journald.conf.d/size-limit.conf
sudo systemctl restart systemd-journald
```

**Menos escrituras en la SD (noviembre 2026).** Medido: la tarjeta recibía
~1 GB al día. Tres ajustes, cada uno explicado en su fichero:

```bash
# Temporales de las copias en RAM (~240 MB/día menos). Antes de Qdrant (2.2)
# para que su unidad encuentre montado /var/lib/qdrant/snapshots.
grep -v '^#' deploy/fstab-tmpfs | grep -v '^$' | sudo tee -a /etc/fstab
sudo mkdir -p /var/lib/johanfer-backup /var/lib/qdrant/snapshots
sudo systemctl daemon-reload && sudo mount -a

# cron sin líneas informativas en el journal (~1.800/día menos)
sudo mkdir -p /etc/systemd/system/cron.service.d
sudo cp deploy/cron-quiet.conf /etc/systemd/system/cron.service.d/quiet.conf
sudo systemctl daemon-reload && sudo systemctl restart cron
```

La base va en `auto_vacuum=INCREMENTAL` y la pasada de noticias de las 22:00
devuelve cada día las páginas libres (`PRAGMA incremental_vacuum` en
`purge_old_news`). Una base restaurada de una copia anterior a ese cambio no
lo trae: se fija una vez, con la web parada o entre pasadas.

```bash
python - <<'PY'
import sqlite3
c = sqlite3.connect('database.db', isolation_level=None)
c.execute('PRAGMA auto_vacuum=INCREMENTAL'); c.execute('VACUUM')
print(c.execute('PRAGMA auto_vacuum').fetchone())   # (2,)
PY
```

Lo que trae la imagen de Raspberry Pi OS y aquí no hace nada (octubre de 2026).
Paquetes: ImageMagick y lo que arrastraba `neofetch` (el sitio procesa las
imágenes con Pillow), las cabeceras de Postgres y de GPIO, NFS. Unidades:
`man-db` regenera a diario el índice de manuales, `e2scrub` solo sirve con
LVM, la Pi 3 no tiene EEPROM que actualizar y no hay pantalla.

```bash
sudo apt-get purge --autoremove neofetch imagemagick imagemagick-6.q16   libpq-dev libpigpio-dev libpigpiod-if-dev nfs-common rpcbind pastebinit
sudo systemctl disable --now man-db.timer e2scrub_all.timer e2scrub_reap.service   rpi-eeprom-update.service rpi-display-backlight.service
```

Se quedan `avahi-daemon` (Windows encuentra la Pi como `raspberrypi` por mDNS)
y el paquete `rpi-eeprom` (si se quita, se lleva `raspi-utils` y con él
`vcgencmd`).

El swap es **zram** (`zramswap.service`, `/etc/default/zramswap`: `ALGO=lz4`,
`PERCENT=50`, `PRIORITY=100`), en RAM comprimida y no sobre la SD. Antes lo
gestionaba `dphys-swapfile`; ya no está instalado y su `/var/swap` se borró en
octubre de 2026.

El `config.txt` de fábrica es el de un equipo con pantalla. El de
[`deploy/boot/config.txt`](boot/config.txt) apaga audio, cámara, detección de
pantallas y el driver KMS, y deja la GPU en 16 MB. Requiere reiniciar:

```bash
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak
sudo cp deploy/boot/config.txt /boot/firmware/config.txt
ls /boot/firmware/start_cd.elf /boot/firmware/fixup_cd.dat   # gpu_mem=16 los necesita
sudo cp deploy/modprobe-headless.conf /etc/modprobe.d/headless.conf
sudo update-initramfs -u
```

En cada arranque journald avisa `system.journal corrupted or uncleanly shut
down, renaming and replacing`, y no es ni lo uno ni lo otro. La placa no tiene
reloj de hardware: `fake-hwclock` guarda la hora al apagar y journald sigue
escribiendo un segundo más, así que al arrancar el reloj vuelve a un instante
anterior a la última entrada y journald aparta el fichero por tener entradas
«del futuro». Los apartados (`*.journal~`) están cerrados (`State: OFFLINE`),
pasan `journalctl --verify` y se siguen leyendo; el límite de tamaño los cuenta
y los purga como a los demás.

El `modprobe-headless.conf` hace falta porque el árbol de dispositivos sigue
anunciando cámara, códec y audio aunque el firmware recortado ya no los ofrezca:
sin la lista negra, esos módulos se cargan igual y fallan en cada arranque.

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
systemctl list-timers 'johanfer-*' --no-legend | wc -l                     # 6 (3 tareas + 3 backups)
python manage.py shell -c "from my_news.models import News; print(News.objects.count())"
```

La primera petición tras reiniciar puede tardar ~20 s: es el arranque en frío de
gunicorn con `--preload` en una Pi 3. No es un fallo.

---

## Copias de seguridad

**Desde noviembre de 2026, cada copia es un solo archivo** comprimido con zstd
y cifrado con gpg (AES-256, con la contraseña de siempre, la de restic), que se
sube con rclone al remoto **sobrescribiendo un hueco fijo**. Antes iban a un
repositorio de restic: es un formato de muchos ficheros pequeños, y la poda
semanal borraba ~30 de golpe; el servicio de almacenamiento avisaba de un
«borrado masivo» cada domingo y lo borrado se acumulaba en su papelera. Con huecos fijos no se borra
nada nunca y el número de ficheros no crece. El porqué y los detalles, en la
cabecera de [`deploy/bin/johanfer-backup-lib`](bin/johanfer-backup-lib).

| qué | script | timer | huecos | en el remoto |
|---|---|---|---|---|
| `database.db` | `johanfer-db-backup` | cada 6 h (00,06,12,18:15) | 8 de las últimas 48 h, 14 diarios, 8 semanales, 12 mensuales | 42 × ~1,8 MB |
| Storage de Qdrant | `johanfer-qdrant-backup` | diario (02:45) | 3 (uno por día) | 3 × ~59 MB |
| Configuración, secretos y portadas | `johanfer-config-backup` | sábados 03:15 | 4 (uno por semana) | 4 × ~11 MB |
| Verificación | `johanfer-backup-maintenance` | domingos 03:30 | — | — |

En total unos 300 MB, en la carpeta `BACKUP_REMOTE` del `.env` (`base/`,
`qdrant/`, `config/`). La verificación de los domingos baja la copia
más reciente de cada tipo, la descifra y comprueba que sirve: la base pasa un
`integrity_check` de SQLite, y los tar de Qdrant y de configuración se leen
enteros. Es un simulacro de restauración de punta a punta.

Los scripts están en [`deploy/bin/`](bin/) (los cuatro cargan
`johanfer-backup-lib`) y sus unidades en [`deploy/systemd/`](systemd/). Las de
copia reintentan, cada 15 min, si falla la subida. Los temporales van a tmpfs
([`deploy/fstab-tmpfs`](fstab-tmpfs)), no a la SD.

La copia de configuración existe para **reinstalar en limpio**, no para clonar
la tarjeta (se descartó guardar una imagen: casi 1 GB, se queda vieja y el
sistema ya está descrito en esta guía). Lleva `.env`, `media/`, certificados,
las claves y scripts de `/home/johan`, `authorized_keys`, y de `/etc` lo de
nginx, fail2ban, ufw, systemd, logrotate, sysctl, modprobe, zram, sudoers, el
WiFi y `fstab`, más `config.txt` y `cmdline.txt`. Y unos volcados que no se
restauran tal cual pero sirven de lista de comprobación (en
`var/lib/johanfer-backup/config/` dentro del tar): crontab, paquetes instalados
a mano, unidades habilitadas, `ufw status` y `pip freeze`.

El destino y las rutas de credenciales no van en los scripts: los leen de
`/etc/johanfer-backup.env`, que no se versiona (plantilla en
[`deploy/backup.env.example`](backup.env.example)); `BACKUP_REMOTE` es la
carpeta de las copias.

```bash
sudo apt install -y rclone zstd gnupg
sudo install -m 600 -o root -g root /ruta/a/la/copia/johanfer-backup.env /etc/johanfer-backup.env
sudo install -m 700 -o root -g root deploy/bin/johanfer-backup-lib deploy/bin/johanfer-{qdrant,db,config}-backup deploy/bin/johanfer-backup-maintenance /usr/local/sbin/
sudo install -m 644 -o root -g root deploy/systemd/johanfer-{qdrant-backup,db-backup,config-backup,backup-maintenance}.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now johanfer-qdrant-backup.timer johanfer-db-backup.timer johanfer-config-backup.timer johanfer-backup-maintenance.timer
```

**El repositorio de restic de antes** (`RESTIC_REPOSITORY` en el `.env`,
hasta el 22/11/2026) ya no se escribe ni se poda. Se conserva como respaldo
mientras las copias nuevas acumulan historia; se puede borrar a mano a partir
de enero de 2027 (dará un último aviso de borrado masivo).

**Qué se puede regenerar y qué no.** `database.db` se copia con
`sqlite3.backup()` y no con `cp`, que con la base en WAL daría una copia
inconsistente (ese método además consolida el `-wal`, así que no hay que
llevarse los ficheros sueltos). El storage de Qdrant se copia con la API de
snapshots, por lo mismo. Y desde que la ventana de duplicados es de un año,
**los vectores antiguos no se regeneran desde ninguna parte**: su noticia se
purgó a los 15 días. `manage.py qdrant_backfill` solo alcanza a los recientes.

Bajar y descifrar una copia (como root, con el `.env` cargado:
`set -a; . /etc/johanfer-backup.env; set +a`). La más reciente de cada carpeta
es la de fecha más alta en `rclone lsl`:

```bash
rclone lsl "$BACKUP_REMOTE/base"
descifra() {   # descifra <carpeta/fichero> <salida>
  rclone cat "$BACKUP_REMOTE/$1" \
    | gpg --batch --pinentry-mode loopback --passphrase-file "$RESTIC_PASSWORD_FILE" -d \
    | zstd -d -c > "$2"
}
descifra base/base-6h-3.db.zst.gpg database.db
descifra qdrant/qdrant-1.snapshot.zst.gpg qdrant.snapshot
descifra config/config-2.tar.zst.gpg config.tar && tar -xf config.tar -C /root/restaurado
```

Restaurar Qdrant desde el snapshot:

```bash
sudo -u johan curl -X POST 'http://127.0.0.1:6333/collections/<coleccion>/snapshots/upload?priority=snapshot'   -H 'Content-Type: multipart/form-data' -F 'snapshot=@qdrant.snapshot'
```

## Restaurar tras perder la tarjeta

Lo que hace falta y dónde está:

| | dónde |
|---|---|
| Código y configuración versionada | este repo |
| Base, Qdrant, configuración y secretos | la carpeta `BACKUP_REMOTE` del `.env` |
| **Contraseña de las copias** (la de restic) y `rclone.conf` | `deploy/secretos/` de la copia privada del proyecto (no va a GitHub) |
| `/etc/johanfer-backup.env` | `deploy/johanfer-backup.env` en esa misma copia |

**Sin esa contraseña no se abre ninguna copia.** Si se cambia en la Pi, hay
que actualizar la copia de `deploy/secretos/`.

1. Grabar Raspberry Pi OS Lite (64 bits) con Raspberry Pi Imager, con usuario
   `johan`, el WiFi y SSH activado, y arrancar.
2. Poner las credenciales y comprobar que se llega a las copias:
   ```bash
   sudo apt update && sudo apt install -y rclone zstd gnupg git
   sudo install -d -m 700 /root/.config/restic /root/.config/rclone
   sudo install -m 600 restic-password /root/.config/restic/johanfer-password
   sudo install -m 600 rclone.conf /root/.config/rclone/rclone.conf
   sudo install -m 600 johanfer-backup.env /etc/johanfer-backup.env
   sudo -i; set -a; . /etc/johanfer-backup.env; set +a
   rclone lsl "$BACKUP_REMOTE"
   ```
3. Recuperar la configuración (la `config-N` más reciente) en un directorio
   aparte con la función `descifra` de la sección anterior, y mirarla antes de
   copiar nada: es la de la máquina vieja, y puede no casar con una versión
   nueva del sistema.
   ```bash
   mkdir -p /root/restaurado
   descifra config/config-2.tar.zst.gpg /root/config.tar && tar -xf /root/config.tar -C /root/restaurado
   ls /root/restaurado/var/lib/johanfer-backup/config/   # crontab, paquetes, unidades...
   ```
4. Seguir la sección 2 de esta guía. Donde pide `.env`, los `jail.d/*.local`,
   los certificados o el WiFi, tomarlos de `/root/restaurado`.
5. Antes de arrancar la aplicación, recuperar los datos:
   ```bash
   descifra base/base-6h-3.db.zst.gpg /root/database.db     # la más reciente
   sudo install -o johan -g johan -m 644 /root/database.db /home/johan/My_Bookshelf/database.db
   cp -a /root/restaurado/home/johan/My_Bookshelf/media /home/johan/My_Bookshelf/
   descifra qdrant/qdrant-1.snapshot.zst.gpg /root/qdrant.snapshot   # la más reciente
   # y subir el snapshot a Qdrant con el curl de la sección anterior
   ```
6. Comprobar con la sección 4.
