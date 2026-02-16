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
                    <div class="book-cover" onclick="openModal('${book.id}')">
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

            // Crear el modal para este libro
            const modal = document.createElement('div');
            modal.id = `modal-${book.id}`;
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content">
                    <span class="close" onclick="closeModal('${book.id}')">&times;</span>
                    <h2>${book.title}</h2>
                    <p><strong>Autor:</strong> ${book.author}</p>
                    <p><strong>Mi Calificación</strong> ${'★'.repeat(book.my_rating)}</p>
                    <p><strong>Calificación General:</strong> ${book.public_rating}</p>
                    <p><strong>Géneros:</strong> ${book.genres || 'Sin género'}</p>
                    <p><strong>Lo leí el...</strong> ${book.date_read}</p>
                    <div class="book-description">
                        <strong>Descripción</strong><br><br>
                        ${book.description || 'No hay descripción disponible'}
                    </div>
                </div>`;

            bookContainer.appendChild(bookItem);
            bookContainer.appendChild(modal);
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
