from .utils import refresh_books_data

def update_books_cron():
    try:
        refresh_books_data()
        print("Books data updated successfully")
    except Exception as e:
        print(f"Error updating books data: {str(e)}")