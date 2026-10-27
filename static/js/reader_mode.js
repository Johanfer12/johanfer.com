(() => {
    'use strict';

    /* =====================================================================
     *  MODO LECTURA CON TTS (Text-to-Speech) Y GESTOS TÁCTILES
     * ================================================================== */

    // Verificar soporte de Web Speech API
    if (!('speechSynthesis' in window)) {
        console.warn('[reader] Web Speech API no soportada en este navegador');
        document.getElementById('readerBtn')?.remove();
        return;
    }

    /* ---------------------------------------------------------------------
     *  Selectores y estado
     * ------------------------------------------------------------------ */
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => Array.from(document.querySelectorAll(sel));

    const DOM = {
        btn: $('#readerBtn'),
        overlay: $('#reader-overlay'),
        title: $('.reader-title'),
        text: $('.reader-text'),
        grid: $('.news-grid'),
        remaining: $('.reader-remaining'),
        headerCounter: $('.header-counter'),
        continuousBtn: $('.reader-continuous-btn'),
    };

    const CONTINUOUS_KEY = 'reader:continuous';
    // Pausa entre una noticia y la siguiente en lectura continua
    const CONTINUOUS_GAP_MS = 900;

    const STATE = {
        active: false,
        currentIndex: 0,
        newsCards: [],
        readingBack: false,
        utterance: null,
        touchStartX: 0,
        touchStartY: 0,
        touchEndX: 0,
        touchEndY: 0,
        minSwipeDistance: 50,
        processingGesture: false,
        continuous: false,
        advanceTimer: null,
    };

    /* ---------------------------------------------------------------------
     *  Funciones de utilidad
     * ------------------------------------------------------------------ */

    /** Obtener todas las tarjetas de noticias visibles */
    const getNewsCards = () => {
        return $$('.news-card-container').filter(card => {
            return !card.classList.contains('deleted') &&
                   card.style.display !== 'none';
        });
    };

    /** Extraer datos de una tarjeta */
    const getCardData = (card) => {
        const front = card.querySelector('.card-front');
        const back = card.querySelector('.card-back');
        const title = front?.querySelector('.news-title')?.textContent || '';
        const shortAnswer = front?.querySelector('.short-answer')?.textContent || '';
        const description = back?.querySelector('.news-description')?.textContent || '';
        const deleteBtn = back?.querySelector('.delete-btn');

        return {
            title,
            shortAnswer,
            description,
            deleteBtn,
            element: card,
        };
    };

    /** Limpiar texto para TTS (remover HTML, exceso de espacios) */
    const cleanText = (text) => {
        return text
            .replace(/<[^>]+>/g, '') // Remover HTML
            .replace(/\s+/g, ' ')     // Normalizar espacios
            .trim();
    };

    /** Obtener el total global desde el header */
    const getHeaderTotal = () => {
        if (!DOM.headerCounter) return null;
        const digits = DOM.headerCounter.textContent?.replace(/[^\d]/g, '');
        if (!digits) return null;
        const total = parseInt(digits, 10);
        return Number.isNaN(total) ? null : total;
    };

    /** Actualizar contador de noticias restantes */
    const updateRemaining = () => {
        if (!DOM.remaining) return;
        const headerTotal = getHeaderTotal();
        if (headerTotal !== null) {
            DOM.remaining.textContent = `Restantes: ${headerTotal}`;
            return;
        }
        const total = STATE.newsCards.length;
        const remaining = Math.max(total - (STATE.currentIndex + 1), 0);
        DOM.remaining.textContent = `Restantes: ${remaining}`;
    };

    /* ---------------------------------------------------------------------
     *  TTS (Text-to-Speech)
     * ------------------------------------------------------------------ */

    /** Detener lectura actual */
    const stopSpeaking = () => {
        clearTimeout(STATE.advanceTimer);
        STATE.advanceTimer = null;
        if (speechSynthesis.speaking || speechSynthesis.pending) {
            speechSynthesis.cancel();
        }
        STATE.utterance = null;
    };

    /** Obtener la mejor voz en español disponible */
    const getSpanishVoice = () => {
        const voices = speechSynthesis.getVoices();

        // Buscar voz en español (cualquier variante)
        const spanishVoice = voices.find(voice => voice.lang.startsWith('es'));

        if (spanishVoice) {
            console.log(`[reader] Usando voz: ${spanishVoice.name} (${spanishVoice.lang})`);
            return spanishVoice;
        }

        console.log('[reader] No se encontró voz en español, usando voz por defecto');
        return null;
    };

    /** Leer texto usando TTS */
    const speak = (text, onEnd = null) => {
        if (!text || text.trim().length === 0) {
            console.warn('[reader] No hay texto para leer');
            return;
        }

        // Cancelar cualquier lectura pendiente
        stopSpeaking();

        const utterance = new SpeechSynthesisUtterance(cleanText(text));

        // Usar la voz en español del sistema si está disponible
        const voice = getSpanishVoice();
        if (voice) {
            utterance.voice = voice;
            utterance.lang = voice.lang;
        } else {
            // Fallback: especificar idioma español
            utterance.lang = 'es-US';
        }

        utterance.rate = 0.95;  // Velocidad ligeramente más lenta (más natural)
        utterance.pitch = 1.0;  // Tono de voz
        utterance.volume = 1.0; // Volumen máximo

        utterance.onend = () => {
            console.log('[reader] Lectura finalizada');
            if (onEnd && STATE.utterance === utterance) onEnd();
        };

        utterance.onerror = (e) => {
            // "interrupted"/"canceled" los provoca stopSpeaking: quien cortó la
            // lectura ya decidió qué viene después, así que no se encadena nada.
            if (e.error === 'interrupted' || e.error === 'canceled') return;
            console.error('[reader] Error en TTS:', e);
            if (onEnd && STATE.utterance === utterance) onEnd();
        };

        STATE.utterance = utterance;

        // Asegurar que speechSynthesis esté listo
        if (speechSynthesis.paused) {
            speechSynthesis.resume();
        }

        speechSynthesis.speak(utterance);
    };

    /* ---------------------------------------------------------------------
     *  Lectura continua
     * ------------------------------------------------------------------ */

    /** Al acabar de leer: en modo continuo, pasar a la siguiente noticia */
    const onSpeechEnd = () => {
        if (!STATE.active || !STATE.continuous) return;
        clearTimeout(STATE.advanceTimer);
        STATE.advanceTimer = setTimeout(() => {
            STATE.advanceTimer = null;
            if (!STATE.active || !STATE.continuous) return;
            // Se detiene en la última en vez de volver a empezar por la primera
            if (STATE.currentIndex + 1 >= getNewsCards().length) {
                DOM.text.textContent = 'No quedan más noticias';
                speak('No quedan más noticias');
                return;
            }
            nextNews();
        }, CONTINUOUS_GAP_MS);
    };

    const setContinuous = (on) => {
        STATE.continuous = on;
        DOM.continuousBtn?.setAttribute('aria-pressed', String(on));
        try { localStorage.setItem(CONTINUOUS_KEY, on ? '1' : '0'); } catch (e) { /* sin almacenamiento */ }
        // Si se activa con la lectura ya terminada, arrancar ahora
        if (on && STATE.active && !speechSynthesis.speaking && !speechSynthesis.pending) {
            onSpeechEnd();
        } else if (!on) {
            clearTimeout(STATE.advanceTimer);
            STATE.advanceTimer = null;
        }
    };

    try { STATE.continuous = localStorage.getItem(CONTINUOUS_KEY) === '1'; } catch (e) { /* sin almacenamiento */ }
    DOM.continuousBtn?.setAttribute('aria-pressed', String(STATE.continuous));

    /* ---------------------------------------------------------------------
     *  Navegación de noticias
     * ------------------------------------------------------------------ */

    /** Cargar y leer una noticia */
    const loadNews = (index) => {
        STATE.newsCards = getNewsCards();

        if (STATE.newsCards.length === 0) {
            exitReaderMode();
            return;
        }

        // Ajustar índice si está fuera de rango
        if (index < 0) index = STATE.newsCards.length - 1;
        if (index >= STATE.newsCards.length) index = 0;

        STATE.currentIndex = index;
        STATE.readingBack = false;

        const card = STATE.newsCards[index];
        const data = getCardData(card);

        // Actualizar UI
        DOM.title.textContent = data.title;
        DOM.text.textContent = data.shortAnswer || 'Sin resumen disponible';
        updateRemaining();

        // Leer título y resumen corto
        const textToRead = `${data.title}. ${data.shortAnswer || ''}`;
        speak(textToRead, onSpeechEnd);

        console.log(`[reader] Noticia ${index + 1} de ${STATE.newsCards.length}`);
    };

    /** Ir a la siguiente noticia */
    const nextNews = () => {
        loadNews(STATE.currentIndex + 1);
    };

    /** Leer el reverso de la tarjeta (descripción completa) */
    const readBack = () => {
        if (STATE.readingBack) return;

        STATE.readingBack = true;
        const card = STATE.newsCards[STATE.currentIndex];
        const data = getCardData(card);

        if (data.description && data.description.trim().length > 0) {
            DOM.text.textContent = data.description;
            speak(data.description, onSpeechEnd);
        } else {
            DOM.text.textContent = 'Sin descripción adicional';
            speak('Sin descripción adicional', onSpeechEnd);
        }
    };

    /** Eliminar noticia actual */
    const deleteCurrentNews = () => {
        const card = STATE.newsCards[STATE.currentIndex];
        const data = getCardData(card);

        if (!data.deleteBtn) {
            console.warn('[reader] No se puede eliminar (no eres staff)');
            return;
        }

        stopSpeaking();

        // Simular click en botón eliminar
        data.deleteBtn.click();

        // Esperar a que la animación de eliminación termine (500ms + margen)
        setTimeout(() => {
            STATE.newsCards = getNewsCards();
            if (STATE.newsCards.length === 0) {
                exitReaderMode();
            } else {
                // Mantener el mismo índice (la siguiente noticia tomará la posición actual)
                loadNews(STATE.currentIndex);
            }
        }, 650);
    };

    /* ---------------------------------------------------------------------
     *  Gestión de gestos táctiles
     * ------------------------------------------------------------------ */

    const handleTouchStart = (e) => {
        STATE.touchStartX = e.changedTouches[0].screenX;
        STATE.touchStartY = e.changedTouches[0].screenY;
    };

    const handleTouchEnd = (e) => {
        STATE.touchEndX = e.changedTouches[0].screenX;
        STATE.touchEndY = e.changedTouches[0].screenY;
        handleGesture();
    };

    const handleGesture = () => {
        // Prevenir gestos múltiples simultáneos
        if (STATE.processingGesture) {
            console.log('[reader] Gesto ignorado: ya procesando otro gesto');
            return;
        }

        const deltaX = STATE.touchEndX - STATE.touchStartX;
        const deltaY = STATE.touchEndY - STATE.touchStartY;
        const absDeltaX = Math.abs(deltaX);
        const absDeltaY = Math.abs(deltaY);

        // Determinar si es un swipe válido
        if (absDeltaX < STATE.minSwipeDistance && absDeltaY < STATE.minSwipeDistance) {
            return; // No es un swipe significativo
        }

        // Marcar que estamos procesando un gesto
        STATE.processingGesture = true;

        // Determinar dirección principal
        if (absDeltaX > absDeltaY) {
            // Swipe horizontal
            if (deltaX > 0) {
                // Swipe derecha → Leer reverso
                console.log('[reader] Gesto: Derecha - Leer reverso');
                readBack();
                // Liberar inmediatamente para permitir otro gesto
                STATE.processingGesture = false;
            } else {
                // Swipe izquierda → Eliminar y pasar a la siguiente
                console.log('[reader] Gesto: Izquierda - Eliminar y pasar a siguiente');
                deleteCurrentNews();
                // Liberar después de que la eliminación termine
                setTimeout(() => {
                    STATE.processingGesture = false;
                }, 700);
            }
        } else {
            // Swipe vertical
            if (deltaY > 0) {
                // Swipe abajo → Salir
                console.log('[reader] Gesto: Abajo - Salir');
                exitReaderMode();
                // Liberar inmediatamente
                STATE.processingGesture = false;
            } else {
                // Swipe arriba → Siguiente noticia (sin eliminar)
                console.log('[reader] Gesto: Arriba - Siguiente sin eliminar');
                nextNews();
                // Liberar inmediatamente
                STATE.processingGesture = false;
            }
        }
    };

    /* ---------------------------------------------------------------------
     *  Activar/Desactivar modo lectura
     * ------------------------------------------------------------------ */

    const enterReaderMode = () => {
        STATE.active = true;
        STATE.newsCards = getNewsCards();

        if (STATE.newsCards.length === 0) {
            alert('No hay noticias disponibles');
            return;
        }

        // Cambiar theme-color a negro puro
        let metaTheme = document.querySelector('meta[name="theme-color"]');
        if (metaTheme) {
            metaTheme.setAttribute('content', '#000000');
        }

        // Bloquear scroll del body
        document.body.classList.add('reader-active');
        document.body.style.backgroundColor = '#000';
        document.documentElement.style.overflow = 'hidden';
        document.documentElement.style.backgroundColor = '#000';

        // Activar UI
        DOM.btn.classList.add('active');
        DOM.overlay.classList.add('active');

        // Ocultar hints después de 5 segundos
        setTimeout(() => {
            DOM.overlay.classList.add('hide-hints');
        }, 5000);

        // Añadir listeners de gestos
        DOM.overlay.addEventListener('touchstart', handleTouchStart, false);
        DOM.overlay.addEventListener('touchend', handleTouchEnd, false);

        // Cargar primera noticia
        loadNews(0);

        console.log('[reader] Modo lectura activado');
    };

    const exitReaderMode = () => {
        STATE.active = false;

        // Detener lectura
        stopSpeaking();

        // Restaurar theme-color original
        let metaTheme = document.querySelector('meta[name="theme-color"]');
        if (metaTheme) {
            metaTheme.setAttribute('content', '#000000'); // Mantener negro
        }

        // Restaurar scroll del body
        document.body.classList.remove('reader-active');
        document.body.style.backgroundColor = '';
        document.documentElement.style.overflow = '';
        document.documentElement.style.backgroundColor = '';

        // Desactivar UI
        DOM.btn.classList.remove('active');
        DOM.overlay.classList.remove('active');
        DOM.overlay.classList.remove('hide-hints');

        // Remover listeners
        DOM.overlay.removeEventListener('touchstart', handleTouchStart);
        DOM.overlay.removeEventListener('touchend', handleTouchEnd);

        // Limpiar contenido
        DOM.title.textContent = '';
        DOM.text.textContent = '';
        if (DOM.remaining) {
            DOM.remaining.textContent = '';
        }

        console.log('[reader] Modo lectura desactivado');
    };

    const toggleReaderMode = () => {
        if (STATE.active) {
            exitReaderMode();
        } else {
            enterReaderMode();
        }
    };

    /* ---------------------------------------------------------------------
     *  Event listeners
     * ------------------------------------------------------------------ */

    DOM.btn.addEventListener('click', toggleReaderMode);

    DOM.continuousBtn?.addEventListener('click', () => setContinuous(!STATE.continuous));
    // El toque en el botón no debe contar como gesto del lector
    DOM.continuousBtn?.addEventListener('touchstart', (e) => e.stopPropagation());
    DOM.continuousBtn?.addEventListener('touchend', (e) => e.stopPropagation());

    // Manejar teclas (para testing en desktop)
    document.addEventListener('keydown', (e) => {
        if (!STATE.active) return;

        switch(e.key) {
            case 'ArrowUp':
                e.preventDefault();
                nextNews();
                break;
            case 'ArrowDown':
                e.preventDefault();
                exitReaderMode();
                break;
            case 'ArrowRight':
                e.preventDefault();
                readBack();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                deleteCurrentNews();
                break;
            case 'Escape':
                e.preventDefault();
                exitReaderMode();
                break;
            case 'c':
            case 'C':
                e.preventDefault();
                setContinuous(!STATE.continuous);
                break;
        }
    });

    // Pausar si la página pierde visibilidad
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && STATE.active) {
            stopSpeaking();
        }
    });

    if (DOM.headerCounter && DOM.remaining) {
        const headerObserver = new MutationObserver(() => {
            if (STATE.active) {
                updateRemaining();
            }
        });
        headerObserver.observe(DOM.headerCounter, {
            childList: true,
            characterData: true,
            subtree: true,
        });
    }

    // Cargar voces (necesario en Chrome)
    if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = () => {
            const voices = speechSynthesis.getVoices();
            console.log(`[reader] ${voices.length} voces disponibles`);
        };
    }

    // Cargar voces inmediatamente
    speechSynthesis.getVoices();

    console.log('[reader] Modo lectura inicializado');
})();
