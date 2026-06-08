from django.db import models

class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    cover_link = models.TextField()  
    my_rating = models.IntegerField()
    public_rating = models.CharField(max_length=20)
    date_read = models.DateField()
    book_link = models.TextField(unique=True)
    description = models.TextField(null=True, blank=True)
    genres = models.TextField(null=True, blank=True)
    goodreads_id = models.CharField(max_length=32, null=True, blank=True, unique=True)
    isbn = models.CharField(max_length=32, null=True, blank=True)
    num_pages = models.PositiveIntegerField(null=True, blank=True)
    published_year = models.PositiveIntegerField(null=True, blank=True)
    goodreads_date_added = models.DateTimeField(null=True, blank=True)

    @property
    def goodreads_url(self):
        if not self.book_link:
            return ""
        if self.book_link.startswith("http://") or self.book_link.startswith("https://"):
            return self.book_link
        return f"https://www.goodreads.com{self.book_link}"

    class Meta:
        ordering = ['-date_read']
        verbose_name = 'Libro'
        verbose_name_plural = 'Libros'

    def __str__(self):
        return f"{self.title} - {self.author}"

class DeletedBook(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    cover_link = models.TextField()
    my_rating = models.IntegerField()
    public_rating = models.CharField(max_length=20)
    date_read = models.DateField()
    book_link = models.TextField()
    description = models.TextField(null=True, blank=True)
    genres = models.TextField(null=True, blank=True)
    goodreads_id = models.CharField(max_length=32, null=True, blank=True)
    isbn = models.CharField(max_length=32, null=True, blank=True)
    num_pages = models.PositiveIntegerField(null=True, blank=True)
    published_year = models.PositiveIntegerField(null=True, blank=True)
    goodreads_date_added = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Libro Eliminado'
        verbose_name_plural = 'Libros Eliminados'

    def __str__(self):
        return f"{self.title} - {self.author}"


class VisitLog(models.Model):
    ip_address = models.CharField(max_length=45, db_index=True)
    visitor_id = models.CharField(max_length=64, db_index=True, blank=True, default='')
    country_code = models.CharField(max_length=2, blank=True, default='')
    country = models.CharField(max_length=120, blank=True, default='')
    path = models.CharField(max_length=255, db_index=True)
    user_agent = models.TextField(blank=True, default='')
    referrer = models.TextField(blank=True, default='')
    visited_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-visited_at']
        verbose_name = 'Visita'
        verbose_name_plural = 'Visitas'

    def __str__(self):
        return f"{self.ip_address} - {self.path}"
