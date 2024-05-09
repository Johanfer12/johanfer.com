from django_cron import CronJobBase, Schedule
from .models import scrap_books

class DailyScrapingJob(CronJobBase):
    RUN_AT_TIMES = ['19:00']  # ejecutar a las 7 p.m. cada día
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'home_page.daily_scraping_job'  # un identificador único para la tarea

    def do(self):
        scrap_books()