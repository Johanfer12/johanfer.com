import feedparser
from django.test import SimpleTestCase

from .services import FeedService

# Recorte del RSS de The Guardian: la misma foto en tres tamaños, el pequeño
# primero. Las URL van firmadas (`s=`), así que no se puede reescribir el ancho.
GUARDIAN_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>The Guardian</title>
<item>
  <title>Noticia</title>
  <link>https://www.theguardian.com/x</link>
  <media:content width="140" url="https://i.guim.co.uk/a.jpg?width=140&amp;s=uno"/>
  <media:content width="460" url="https://i.guim.co.uk/a.jpg?width=460&amp;s=dos"/>
  <media:content width="700" url="https://i.guim.co.uk/a.jpg?width=700&amp;s=tres"/>
</item>
</channel></rss>"""


class LargestMediaContentTests(SimpleTestCase):
    def test_guardian_feed_takes_the_widest_image(self):
        entry = feedparser.parse(GUARDIAN_RSS).entries[0]
        self.assertEqual(
            FeedService.largest_media_content_url(entry.media_content),
            "https://i.guim.co.uk/a.jpg?width=700&s=tres",
        )

    def test_without_widths_keeps_the_first(self):
        media = [{"url": "https://e.com/1.jpg"}, {"url": "https://e.com/2.jpg"}]
        self.assertEqual(
            FeedService.largest_media_content_url(media), "https://e.com/1.jpg"
        )

    def test_skips_video_and_entries_without_url(self):
        media = [
            {"url": "https://e.com/v.mp4", "medium": "video", "width": "1920"},
            {"url": "", "width": "2000"},
            {"url": "https://e.com/i.jpg", "width": "abc"},
        ]
        self.assertEqual(
            FeedService.largest_media_content_url(media), "https://e.com/i.jpg"
        )

    def test_empty(self):
        self.assertIsNone(FeedService.largest_media_content_url([]))
        self.assertIsNone(FeedService.largest_media_content_url(None))
