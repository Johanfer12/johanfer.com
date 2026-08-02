#!/bin/bash
# Despliegue de la aplicación Django.
#
# Copia de referencia versionada. El que se ejecuta de verdad vive en
# /home/johan/deploy.sh, FUERA del repo, a propósito: hace `git checkout .`
# sobre el propio repo y no puede estar dentro de lo que revierte.
#
# Si se cambia este fichero, hay que copiarlo a mano:
#   cp /home/johan/My_Bookshelf/deploy/deploy.sh /home/johan/deploy.sh
#   chmod +x /home/johan/deploy.sh
#
# OJO: no toca el crontab. Si se cambian CRONJOBS o CRONTAB_COMMAND_SUFFIX en
# settings.py hay que hacer además:
#   python manage.py crontab remove && python manage.py crontab add

set -Eeuo pipefail

# 1) Moverse al directorio del proyecto
cd /home/johan/My_Bookshelf || {
    echo "ERROR: No se pudo acceder a /home/johan/My_Bookshelf"
    exit 1
}

# 2) Revertir cambios locales (descartar modificaciones en el repositorio)
echo "Revirtiendo cambios locales (git checkout .)"
git checkout .

# 3) Obtener los últimos cambios del repositorio
echo "Haciendo pull de la rama main"
git pull origin main

# 4) Activar el entorno virtual
echo "Activando el entorno virtual..."
source env/bin/activate || {
    echo "ERROR: No se pudo activar el entorno virtual (esperaba /home/johan/My_Bookshelf/env)"
    exit 1
}

# 5) Instalar dependencias
if [[ -f requirements.txt ]]; then
    echo "Actualizando pip y herramientas base..."
    python -m pip install --upgrade pip setuptools wheel

    echo "Instalando dependencias desde requirements.txt..."
    python -m pip install -r requirements.txt --no-cache-dir
else
    echo "ADVERTENCIA: requirements.txt no existe; se omite la instalación de dependencias."
fi

# 6) Ejecutar migraciones
echo "Aplicando migraciones..."
python manage.py migrate

# 7) Recopilar archivos estáticos
echo "Recopilando archivos estáticos..."
python manage.py collectstatic --noinput --clear

# 8) Reiniciar el servicio systemd de Gunicorn
echo "Reiniciando servicio bookshelf..."
sudo systemctl restart my_bookshelf.service

echo "Despliegue completado con éxito."
