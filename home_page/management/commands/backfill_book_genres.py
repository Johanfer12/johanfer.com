from __future__ import annotations

import os
from typing import Dict

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from home_page.models import Book
from home_page.utils import extract_genres_from_book_link, extract_genres_from_review, extract_goodreads_id


DEFAULT_USER_ID = getattr(settings, "GOODREADS_USER_ID", "27786474-johan-gonzalez")
DEFAULT_BASE_URL = (
    "https://www.goodreads.com/review/list/"
    f"{DEFAULT_USER_ID}?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"
)


def _build_headers(cookie: str | None) -> Dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        )
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _get_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pagination_div = soup.find("div", id="reviewPagination")
    if not pagination_div:
        return 1
    links = pagination_div.find_all("a")
    if len(links) < 2:
        return 1
    try:
        return int(links[-2].get_text(strip=True))
    except Exception:
        return 1


class Command(BaseCommand):
    help = "Rellena el campo genres en libros existentes desde la lista de Goodreads."

    def add_arguments(self, parser):
        parser.add_argument("--cookie", type=str, default=None, help="Cookie de sesion de Goodreads (opcional).")
        parser.add_argument(
            "--user-id",
            type=str,
            default=DEFAULT_USER_ID,
            help="Identificador del usuario en Goodreads (ej: 27786474-johan-gonzalez).",
        )
        parser.add_argument(
            "--pages",
            type=int,
            default=0,
            help="Numero maximo de paginas a procesar (0 = todas).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximo de libros a actualizar en DB (0 = sin limite).",
        )
        parser.add_argument("--overwrite", action="store_true", help="Reescribe genres aunque ya exista valor.")
        parser.add_argument("--dry-run", action="store_true", help="No guarda cambios, solo muestra conteos.")

    def handle(self, *args, **options):
        user_id = options["user_id"]
        base_url = (
            "https://www.goodreads.com/review/list/"
            f"{user_id}?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"
        )
        cookie = options.get("cookie") or os.getenv("GOODREADS_COOKIE")
        headers = _build_headers(cookie)
        max_pages = max(0, int(options.get("pages") or 0))
        limit = max(0, int(options.get("limit") or 0))
        overwrite = bool(options.get("overwrite"))
        dry_run = bool(options.get("dry_run"))

        self.stdout.write("Obteniendo catalogo de Goodreads para backfill de generos...")
        first = requests.get(base_url, headers=headers, timeout=20)
        first.raise_for_status()
        total_pages = _get_total_pages(first.text)
        if max_pages:
            total_pages = min(total_pages, max_pages)

        by_gid: Dict[str, str] = {}
        processed_reviews = 0

        for page_number in range(1, total_pages + 1):
            page_url = f"{base_url}&page={page_number}"
            resp = requests.get(page_url, headers=headers, timeout=20)
            if resp.status_code != 200:
                self.stderr.write(f"Pagina {page_number}: HTTP {resp.status_code}, se omite.")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            reviews = soup.find_all("tr", class_="bookalike review")
            for review in reviews:
                processed_reviews += 1
                title_cell = review.find("td", class_="field title")
                link_tag = title_cell.find("a") if title_cell else None
                if not link_tag:
                    continue
                gid = extract_goodreads_id(link_tag.get("href", ""))
                if not gid:
                    continue
                genres = extract_genres_from_review(review)
                if not genres:
                    genres = extract_genres_from_book_link(link_tag.get("href", ""), headers)
                if genres:
                    by_gid[gid] = genres

            self.stdout.write(f"Pagina {page_number}/{total_pages}: reviews={len(reviews)}, mapeados={len(by_gid)}")

        qs = Book.objects.all().only("id", "book_link", "genres")
        if not overwrite:
            qs = qs.filter(Q(genres__isnull=True) | Q(genres=""))

        updated = 0
        missing_in_goodreads = 0
        no_genres_found = 0
        to_update = []

        for book in qs.iterator():
            gid = extract_goodreads_id(book.book_link or "")
            if not gid:
                missing_in_goodreads += 1
                continue
            if gid not in by_gid:
                missing_in_goodreads += 1
                continue
            genres = by_gid[gid]
            if not genres:
                no_genres_found += 1
                continue
            if not overwrite and (book.genres or "").strip():
                continue
            book.genres = genres
            to_update.append(book)
            updated += 1
            if limit and updated >= limit:
                break

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: actualizaria {len(to_update)} libros "
                    f"(reviews procesadas={processed_reviews}, mapeados={len(by_gid)}, "
                    f"sin-match={missing_in_goodreads}, sin-generos={no_genres_found})"
                )
            )
            return

        if to_update:
            with transaction.atomic():
                Book.objects.bulk_update(to_update, ["genres"], batch_size=200)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill completado: actualizados={len(to_update)}, "
                f"reviews_procesadas={processed_reviews}, mapeados={len(by_gid)}, "
                f"sin_match={missing_in_goodreads}, sin_generos={no_genres_found}"
            )
        )
