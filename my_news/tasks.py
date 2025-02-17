from .services import FeedService

def update_news_cron():
    try:
        FeedService.fetch_and_save_news()
        print("News data updated successfully")
    except Exception as e:
        print(f"Error updating news data: {str(e)}") 