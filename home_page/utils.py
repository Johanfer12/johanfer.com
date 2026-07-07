from bs4 import BeautifulSoup
import feedparser
import requests
import os
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime
from PIL import Image
import re
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from Bookshelf.html_sanitizer import sanitize_html
from .models import Book

logger = logging.getLogger(__name__)


def modify_cover_url(cover_url):
    return re.sub(r'(_SX\d+_SY\d+_|_SY\d+_SX\d+_|_SX\d+_|_SY\d+_)', '_SY700_', cover_url)

def convert_to_webp(source_path, destination_path):
    try:
        with Image.open(source_path) as img:
            img.thumbnail((300, 450), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(destination_path, 'WEBP')
    except Exception:
        logger.exception("Error al convertir la imagen")

def parse_rss_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed and timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
    except Exception:
        return None


def parse_rss_date(value):
    parsed = parse_rss_datetime(value)
    return parsed.date() if parsed else None


def parse_positive_int(value):
    try:
        parsed = int(str(value or "").strip())
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def normalize_goodreads_book_link(entry):
    summary = entry.get("summary") or ""
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        link = soup.find("a", href=re.compile(r"/book/show/"))
        if link and link.get("href"):
            href = link["href"].split("?", 1)[0]
            match = re.search(r"https?://www\.goodreads\.com(?P<path>/book/show/[^\"'#?]+)", href)
            if match:
                return match.group("path")
            if href.startswith("/book/show/"):
                return href

    book_id = (entry.get("book_id") or "").strip()
    if book_id:
        return f"/book/show/{book_id}"

    return (entry.get("link") or "").split("?", 1)[0]


def find_existing_book(goodreads_id, book_link):
    query = Q()
    if goodreads_id:
        query |= Q(goodreads_id=goodreads_id)
        query |= Q(book_link__contains=f"/show/{goodreads_id}")
    if book_link:
        query |= Q(book_link=book_link)
    if not query:
        return None
    return Book.objects.filter(query).first()


def build_rss_page_url(rss_url, page_number, per_page):
    parts = urlsplit(rss_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page_number)
    query["per_page"] = str(per_page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_shelf_url(rss_url, shelf):
    """Devuelve la URL del RSS apuntando a otra estantería de Goodreads."""
    parts = urlsplit(rss_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["shelf"] = shelf
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_feed_with_timeout(url, timeout=15):
    """Descarga un feed con timeout explícito; feedparser no lo soporta nativamente."""
    response = requests.get(
        url,
        timeout=timeout,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; johanfer-bookshelf/1.0)'},
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def fetch_goodreads_rss_entries(rss_url):
    per_page = max(1, min(int(getattr(settings, "GOODREADS_RSS_PER_PAGE", 200) or 200), 200))
    entries = []
    seen_ids = set()

    for page_number in range(1, 100):
        page_url = build_rss_page_url(rss_url, page_number, per_page)
        try:
            feed = fetch_feed_with_timeout(page_url)
        except requests.RequestException:
            logger.exception("Error descargando Goodreads RSS (página %s); se procesa lo recolectado.", page_number)
            break
        if getattr(feed, "bozo", False):
            logger.warning("Goodreads RSS no pudo parsearse correctamente: %s", getattr(feed, "bozo_exception", ""))

        page_entries = getattr(feed, "entries", []) or []
        if not page_entries:
            break

        new_entries = []
        for entry in page_entries:
            entry_key = (entry.get("book_id") or entry.get("id") or entry.get("link") or "").strip()
            if entry_key and entry_key in seen_ids:
                continue
            if entry_key:
                seen_ids.add(entry_key)
            new_entries.append(entry)

        if not new_entries:
            break

        entries.extend(new_entries)
        if len(page_entries) < per_page:
            break

    return entries


def download_cover_as_webp(cover_url, book_id, folder_path):
    if not cover_url or not book_id:
        return

    file_path = os.path.join(folder_path, f"{book_id}.webp")
    temp_path = os.path.join(folder_path, f"temp_{book_id}.jpg")
    try:
        response = requests.get(modify_cover_url(cover_url), timeout=30)
        response.raise_for_status()
        with open(temp_path, "wb") as f:
            f.write(response.content)
        convert_to_webp(temp_path, file_path)
    except Exception:
        logger.exception("Error al procesar portada RSS para libro %s", book_id)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def sync_currently_reading(rss_url, folder_path):
    """Sincroniza la estantería currently-reading: marca is_reading y crea
    los libros en curso que aún no existan (sin fecha ni calificación).

    Devuelve la lista de ids marcados, o None si el feed no pudo leerse
    (en ese caso no se tocan los flags existentes).
    """
    reading_url = build_shelf_url(rss_url, "currently-reading")
    try:
        feed = fetch_feed_with_timeout(reading_url)
    except requests.RequestException:
        logger.exception("Error descargando shelf currently-reading; se conservan los flags actuales.")
        return None

    reading_ids = []
    for entry in getattr(feed, "entries", []) or []:
        goodreads_id = (entry.get("book_id") or "").strip() or None
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        try:
            book_link = normalize_goodreads_book_link(entry)
            with transaction.atomic():
                book = find_existing_book(goodreads_id, book_link)
                is_new = book is None
                if is_new:
                    book = Book(my_rating=0, date_read=None)

                book.title = title
                book.author = (entry.get("author_name") or "").strip() or "Unknown Author"
                book.cover_link = (entry.get("book_large_image_url") or entry.get("book_medium_image_url") or entry.get("book_image_url") or "").strip()
                book.public_rating = (entry.get("average_rating") or "0.0").strip()
                book.book_link = book_link
                book.is_reading = True
                rss_description = entry.get("book_description")
                book.description = sanitize_html(rss_description) if rss_description else book.description
                book.goodreads_id = goodreads_id or book.goodreads_id
                book.isbn = (entry.get("isbn") or "").strip() or book.isbn
                book.num_pages = parse_positive_int(entry.get("num_pages")) or book.num_pages
                book.published_year = parse_positive_int(entry.get("book_published")) or book.published_year
                book.goodreads_date_added = parse_rss_datetime(entry.get("user_date_added")) or book.goodreads_date_added
                book.save()

            if book.cover_link:
                cover_path = os.path.join(folder_path, f"{book.id}.webp")
                if is_new or not os.path.exists(cover_path):
                    download_cover_as_webp(book.cover_link, book.id, folder_path)

            reading_ids.append(book.id)
            if is_new:
                logger.info("Libro en curso creado desde RSS: %s", title)
        except Exception:
            logger.exception("Error procesando libro en curso RSS: %s", title or goodreads_id)
            continue

    return reading_ids


def refresh_books_data():
    folder_path = os.path.join(settings.MEDIA_ROOT, "Covers")
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    rss_url = getattr(settings, "GOODREADS_RSS_URL", "https://www.goodreads.com/review/list_rss/27786474?shelf=read")

    # Estantería "leyendo ahora": marcar en curso y limpiar los que salieron
    reading_ids = sync_currently_reading(rss_url, folder_path)
    if reading_ids is not None:
        Book.objects.filter(is_reading=True).exclude(id__in=reading_ids).update(is_reading=False)

    entries = fetch_goodreads_rss_entries(rss_url)
    if not entries:
        logger.warning("Goodreads RSS no devolvió libros. Se conserva la información guardada.")
        return

    created = 0
    updated = 0

    for entry in reversed(entries):
        goodreads_id = (entry.get("book_id") or "").strip() or None
        title = (entry.get("title") or "").strip()
        try:
            book_link = normalize_goodreads_book_link(entry)
            author = (entry.get("author_name") or "").strip() or "Unknown Author"
            date_read = parse_rss_date(entry.get("user_read_at"))

            if not title or not date_read:
                logger.warning("Libro RSS omitido por falta de título o fecha: %s", title or goodreads_id)
                continue

            with transaction.atomic():
                book = find_existing_book(goodreads_id, book_link)
                is_new = book is None
                if is_new:
                    book = Book()

                book.title = title
                book.author = author
                book.cover_link = (entry.get("book_large_image_url") or entry.get("book_medium_image_url") or entry.get("book_image_url") or "").strip()
                book.my_rating = parse_positive_int(entry.get("user_rating")) or 0
                book.public_rating = (entry.get("average_rating") or "0.0").strip()
                book.date_read = date_read
                book.is_reading = False  # está en la estantería "read": terminado
                book.book_link = book_link
                rss_description = entry.get("book_description")
                book.description = sanitize_html(rss_description) if rss_description else book.description
                book.goodreads_id = goodreads_id or book.goodreads_id
                book.isbn = (entry.get("isbn") or "").strip() or book.isbn
                book.num_pages = parse_positive_int(entry.get("num_pages")) or book.num_pages
                book.published_year = parse_positive_int(entry.get("book_published")) or book.published_year
                book.goodreads_date_added = parse_rss_datetime(entry.get("user_date_added")) or book.goodreads_date_added
                book.save()

            # La descarga va fuera de la transacción para no mantener
            # bloqueada la BD (SQLite) durante peticiones de red.
            if book.cover_link:
                cover_path = os.path.join(folder_path, f"{book.id}.webp")
                if is_new or not os.path.exists(cover_path):
                    download_cover_as_webp(book.cover_link, book.id, folder_path)

            if is_new:
                created += 1
                logger.info("Libro creado desde RSS: %s", title)
            else:
                updated += 1
        except Exception:
            logger.exception("Error procesando libro RSS: %s", title or goodreads_id)
            continue

    logger.info("Goodreads RSS procesado: creados=%s, actualizados=%s, items=%s", created, updated, len(entries))
