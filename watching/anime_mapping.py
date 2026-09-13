"""Traducciones verificables; nunca adivinar un cour por título o por orden."""

from dataclasses import dataclass

from django.conf import settings


class UnresolvedEpisode(ValueError):
    pass


@dataclass(frozen=True)
class AnimeEpisode:
    simkl_id: int
    number: int
    season: int
    episode: int


# IMDb de TYBW, temporada del catálogo Cinemeta -> cour Simkl y TVDB.
# El desplazamiento 40 se comprobó en /anime/episodes/2671730 (E8 = S17E48).
# No extrapolar a otras temporadas: requieren su propio catálogo verificado.
SERIES_ANIME_MAPPINGS = {
    ('tt14986406', 4): {'simkl_id': 2671730, 'tvdb_season': 17, 'offset': 40},
    ('mal:41467', 4): {'simkl_id': 2671730, 'tvdb_season': 17, 'offset': 40},
}


def resolve_series_anime(content_id, season, episode, fetch_catalog):
    """Traduce solo si la tabla y el catálogo actual coinciden exactamente.

    WATCHING_SERIES_ANIME_MAPPINGS permite ampliar las equivalencias verificadas.
    Ningún error o catálogo incompleto produce un marcado aproximado.
    """
    mappings = dict(SERIES_ANIME_MAPPINGS)
    mappings.update(getattr(settings, 'WATCHING_SERIES_ANIME_MAPPINGS', {}))
    mapping = mappings.get((content_id, season))
    if not mapping or not isinstance(episode, int) or episode < 1:
        raise UnresolvedEpisode('Sin equivalencia verificada para esta serie/temporada')
    sid = mapping['simkl_id']
    target = (mapping['tvdb_season'], mapping['offset'] + episode)
    matches = [e for e in fetch_catalog(sid, is_anime=True)
               if e.get('type') == 'episode'
               and ((e.get('tvdb') or {}).get('season'),
                    (e.get('tvdb') or {}).get('episode')) == target]
    if len(matches) != 1 or not matches[0].get('episode'):
        raise UnresolvedEpisode('El catálogo no confirma una equivalencia única')
    return AnimeEpisode(sid, matches[0]['episode'], *target)
