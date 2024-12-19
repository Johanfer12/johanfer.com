let page = 1;
let loading = false;
const bookContainer = document.getElementById('book-container');
const loadingDiv = document.getElementById('loading');

function loadMoreBooks() {
    if (loading) return;
    loading = true;
    loadingDiv.style.display = 'block';

    fetch(`/bookshelf?page=${page + 1}`, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        data.books.forEach(book => {
            const bookItem = document.createElement('div');
            bookItem.className = 'book-item';            
            const coverImage = book.cover_image.replace('.jpg', '.webp');
            
            bookItem.innerHTML = `
                <div class="book-info-container">
                    <div class="book-cover">
                        <img src="${coverImage}" alt="${book.title}">
                    </div>
                    <div class="book-info">
                        <a href="https://www.goodreads.com${book.book_link}" class="book-title" target="_blank">${book.title}</a>
                        <p><strong>Autor</strong><br>${book.author}</p>
                        <p><strong>Mi Calificación</strong><br>${'★'.repeat(book.my_rating)}</p>
                        <p><strong>Calificación General</strong><br>${book.public_rating}</p>
                        <p><strong>Lo leí el...</strong><br>${book.date_read}</p>
                    </div>
                </div>
            `;
            bookContainer.appendChild(bookItem);
        });

        page++;
        loading = false;
        loadingDiv.style.display = 'none';

        if (!data.has_next) {
            window.removeEventListener('scroll', handleScroll);
        }
    })
    .catch(error => {
        console.error('Error al cargar más libros:', error);
        loading = false;
        loadingDiv.style.display = 'none';
    });
}

function handleScroll() {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
        loadMoreBooks();
    }
}

window.addEventListener('scroll', handleScroll);