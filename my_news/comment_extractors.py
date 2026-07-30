"""Extractores modulares de comentarios para noticias externas.

Cada extractor declara qué dominios soporta y devuelve la misma estructura
normalizada. Para añadir otro medio basta con implementar ``CommentExtractor``
y registrarlo en ``COMMENT_EXTRACTORS``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from datetime import datetime, timezone as datetime_timezone
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


REQUEST_TIMEOUT = 12
MAX_COMMENTS = 100
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
}


class CommentExtractionError(RuntimeError):
    """Error controlado al consultar o interpretar una fuente externa."""


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "html.parser").get_text("\n", strip=True)


def _safe_media_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    if url.startswith("//"):
        url = f"https:{url}"
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None

    host = parsed.hostname.lower().rstrip(".")
    allowed_domains = (
        "disquscdn.com",
        "tenor.com",
        "giphy.com",
        "weblogssl.com",
    )
    if not any(_host_matches(host, domain) for domain in allowed_domains):
        return None
    return url


def _html_media_urls(value: Any) -> list[str]:
    if not value or "<" not in str(value):
        return []
    urls = []
    for image in BeautifulSoup(str(value), "html.parser").find_all("img", src=True):
        safe_url = _safe_media_url(image.get("src"))
        if safe_url and safe_url not in urls:
            urls.append(safe_url)
    return urls


def _without_media_urls(text: str, urls: list[str]) -> str:
    for url in urls:
        text = text.replace(url, "")
        if url.startswith("https:"):
            text = text.replace(url.removeprefix("https:"), "")
    return text.strip()


def _unix_date(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=datetime_timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _extract_assigned_json(html: str, marker: str) -> dict[str, Any]:
    """Lee un objeto JSON situado después de un marcador JavaScript."""
    marker_index = html.find(marker)
    if marker_index < 0:
        raise CommentExtractionError("No se encontró la información de comentarios.")

    json_start = html.find("{", marker_index + len(marker))
    if json_start < 0:
        raise CommentExtractionError("La información de comentarios no contiene JSON.")

    try:
        value, _ = json.JSONDecoder().raw_decode(html[json_start:])
    except json.JSONDecodeError as exc:
        raise CommentExtractionError("La información de comentarios no es válida.") from exc

    if not isinstance(value, dict):
        raise CommentExtractionError("La información de comentarios tiene un formato inesperado.")
    return value


def _request_html(url: str, *, params: dict[str, Any] | None = None) -> str:
    try:
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        raise CommentExtractionError("No se pudo consultar la página de comentarios.") from exc


def _with_query_parameter(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


class CommentExtractor(ABC):
    """Contrato común de los adaptadores de comentarios."""

    source_name = "Comentarios"
    domains: tuple[str, ...] = ()

    def supports(self, url: str) -> bool:
        host = _hostname(url)
        return bool(host) and any(_host_matches(host, domain) for domain in self.domains)

    @abstractmethod
    def extract(self, url: str) -> dict[str, Any]:
        """Devuelve ``source``, ``total`` y una lista normalizada ``comments``."""


class WebediaCommentExtractor(CommentExtractor):
    """Comentarios incrustados por Webedia en sus distintos medios."""

    source_name = "Webedia"
    domains = ("xataka.com", "3djuegos.com", "vidaextra.com")

    def extract(self, url: str) -> dict[str, Any]:
        data = _extract_assigned_json(
            _request_html(url),
            "AML.Comments.config.data =",
        )
        raw_comments = data.get("comments") or []
        comments = []
        for item in raw_comments[:MAX_COMMENTS]:
            if not isinstance(item, dict):
                continue
            raw_content = item.get("content") or item.get("content_filtered")
            media_urls = _html_media_urls(raw_content)
            comments.append({
                "id": str(item.get("id") or ""),
                "user": (
                    item.get("user_name")
                    or item.get("author")
                    or item.get("comment_author")
                    or "Anónimo"
                ),
                "comment": _without_media_urls(_plain_text(raw_content), media_urls),
                "date": _unix_date(item.get("date")),
                "parent_id": str(item["parent"]) if item.get("parent") is not None else None,
                "depth": int(item.get("tree_level") or 0),
                "votes": int(item.get("vote_count") or 0),
                "upvotes": None,
                "downvotes": None,
                "media": [{"url": media_url, "thumbnail_url": media_url} for media_url in media_urls],
            })

        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        total = meta.get("totalCount", meta.get("total", len(comments)))
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(comments)

        return {
            "source": self.source_name,
            "total": total,
            "comments": comments,
        }


class ElChapuzasDisqusCommentExtractor(CommentExtractor):
    """Comentarios Disqus usados por El Chapuzas Informático."""

    source_name = "Disqus"
    domains = ("elchapuzasinformatico.com",)

    def _embed_from_feed(self, url: str) -> dict[str, Any]:
        """Reconstruye la configuración Disqus desde el RSS de WordPress."""
        parsed_url = urlparse(url)
        feed_url = urlunparse(parsed_url._replace(path="/feed/", params="", query="", fragment=""))
        feed_xml = _request_html(feed_url)

        try:
            root = ElementTree.fromstring(feed_xml)
        except ElementTree.ParseError as exc:
            raise CommentExtractionError("El RSS de la fuente no es válido.") from exc

        expected_url = url.rstrip("/")
        for item in root.findall(".//item"):
            item_url = (item.findtext("link") or "").strip()
            if item_url.rstrip("/") != expected_url:
                continue

            guid = (item.findtext("guid") or "").strip()
            post_id = (parse_qs(urlparse(guid).query).get("p") or [""])[0].strip()
            if not post_id or not guid:
                break

            return {
                "disqusShortname": "elchapuzasinformatico",
                "disqusIdentifier": f"{post_id} {guid}",
                "disqusUrl": item_url,
                "disqusTitle": (item.findtext("title") or "").strip(),
            }

        raise CommentExtractionError("La noticia no aparece en el RSS de la fuente.")

    def _get_embed_config(self, url: str) -> dict[str, Any]:
        # El parámetro evita el bloqueo que la portada aplica a algunas
        # peticiones automatizadas, sin alterar el contenido del artículo.
        try:
            article_html = _request_html(_with_query_parameter(url, "output", "1"))
            return _extract_assigned_json(article_html, "var embedVars =")
        except CommentExtractionError:
            # Cloudflare puede desafiar la huella TLS de la Raspberry aunque
            # el RSS del mismo sitio siga disponible.
            return self._embed_from_feed(url)

    def extract(self, url: str) -> dict[str, Any]:
        embed = self._get_embed_config(url)

        shortname = str(embed.get("disqusShortname") or "").strip()
        identifier = str(embed.get("disqusIdentifier") or "").strip()
        canonical_url = str(embed.get("disqusUrl") or url).strip()
        title = str(embed.get("disqusTitle") or "").strip()
        if not shortname or not identifier:
            raise CommentExtractionError("La noticia no expone su conversación de Disqus.")

        embed_html = _request_html(
            "https://disqus.com/embed/comments/",
            params={
                "base": "default",
                "f": shortname,
                "t_i": identifier,
                "t_u": canonical_url,
                "t_d": title,
            },
        )
        soup = BeautifulSoup(embed_html, "html.parser")
        thread_data_node = soup.find("script", id="disqus-threadData")
        if thread_data_node is None:
            raise CommentExtractionError("Disqus no devolvió la conversación de la noticia.")

        try:
            thread_data = json.loads(thread_data_node.get_text())
        except (TypeError, json.JSONDecodeError) as exc:
            raise CommentExtractionError("Disqus devolvió datos no válidos.") from exc

        response_data = thread_data.get("response") or {}
        raw_comments = response_data.get("posts") or []
        comments = []
        for item in raw_comments[:MAX_COMMENTS]:
            if not isinstance(item, dict) or item.get("isDeleted"):
                continue
            author = item.get("author") if isinstance(item.get("author"), dict) else {}
            media = []
            media_text_urls = []
            for media_item in item.get("media") or []:
                if not isinstance(media_item, dict):
                    continue
                media_url = next((
                    safe_url
                    for candidate in (
                        media_item.get("resolvedUrl"),
                        media_item.get("url"),
                        media_item.get("location"),
                    )
                    if (safe_url := _safe_media_url(candidate))
                ), None)
                thumbnail_url = next((
                    safe_url
                    for candidate in (
                        media_item.get("thumbnailUrl"),
                        media_item.get("thumbnailURL"),
                        media_url,
                    )
                    if (safe_url := _safe_media_url(candidate))
                ), media_url)
                if media_url and not any(existing["url"] == media_url for existing in media):
                    media.append({"url": media_url, "thumbnail_url": thumbnail_url or media_url})
                for candidate in (
                    media_item.get("resolvedUrl"),
                    media_item.get("url"),
                    media_item.get("location"),
                ):
                    if candidate:
                        media_text_urls.append(str(candidate))

            raw_message = item.get("raw_message") or item.get("message")
            comments.append({
                "id": str(item.get("id") or ""),
                "user": author.get("name") or author.get("username") or "Anónimo",
                "comment": _without_media_urls(_plain_text(raw_message), media_text_urls),
                "date": item.get("createdAt") or None,
                "parent_id": str(item["parent"]) if item.get("parent") is not None else None,
                "depth": int(item.get("depth") or 0),
                "votes": int(item.get("points") or 0),
                "upvotes": int(item.get("likes") or 0),
                "downvotes": int(item.get("dislikes") or 0),
                "media": media,
            })

        cursor = thread_data.get("cursor") if isinstance(thread_data.get("cursor"), dict) else {}
        thread = response_data.get("thread") if isinstance(response_data.get("thread"), dict) else {}
        total = cursor.get("total", thread.get("posts", len(comments)))
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(comments)

        return {
            "source": self.source_name,
            "total": total,
            "comments": comments,
        }


# El orden permite registrar primero extractores más específicos si dos
# adaptadores llegaran a compartir dominio.
COMMENT_EXTRACTORS: tuple[CommentExtractor, ...] = (
    ElChapuzasDisqusCommentExtractor(),
    WebediaCommentExtractor(),
)


def get_comment_extractor(url: str) -> CommentExtractor | None:
    return next((extractor for extractor in COMMENT_EXTRACTORS if extractor.supports(url)), None)


def supports_comment_extraction(url: str) -> bool:
    return get_comment_extractor(url) is not None


def extract_comments(url: str) -> dict[str, Any]:
    extractor = get_comment_extractor(url)
    if extractor is None:
        raise CommentExtractionError("Esta fuente todavía no tiene extractor de comentarios.")
    return extractor.extract(url)
