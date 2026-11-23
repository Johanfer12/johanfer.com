// /visitas/: filtros, modales por país, carga de filas por tandas y borrados.
// Vivía en línea en visits.html (unos 20 KB que viajaban en cada carga de la
// página sin poder cachearse); aquí se cachea como el resto de estáticos.
(function () {
    const groups = Array.from(document.querySelectorAll('.visit-country-group'));
    const deleteForm = document.getElementById('visits-delete-form');
    const modal = document.getElementById('delete-confirmation-modal');
    const countryModals = Array.from(document.querySelectorAll('.country-visits-modal'));
    const modalMessage = document.getElementById('delete-modal-message');
    const confirmDelete = document.getElementById('confirm-delete');
    const cancelDelete = document.getElementById('cancel-delete');
    const rowsUrl = deleteForm.dataset.rowsUrl;
    let pendingDelete = null;
    let previouslyFocused = null;
    let activeCountryModal = null;
    let countryModalOpener = null;

    function plural(count, one, many) {
        return count === 1 ? one : many;
    }

    function filterParams() {
        const params = new URLSearchParams();
        ['from', 'to', 'ip', 'country', 'path', 'ua'].forEach(function (name) {
            const field = deleteForm.querySelector('input[name="' + name + '"]');
            if (field && field.value) params.set(name, field.value);
        });
        return params;
    }

    function rowsBody(group) {
        return group.querySelector('.country-visit-rows');
    }

    function checkboxes(group) {
        return Array.from(group.querySelectorAll('.visit-select'));
    }

    function updateCountryState(group) {
        const master = group.querySelector('.select-country-visits');
        const items = checkboxes(group);
        const selected = items.filter(function (item) { return item.checked; }).length;
        master.checked = items.length > 0 && selected === items.length;
        master.indeterminate = selected > 0 && selected < items.length;
    }

    function renderCounts(group) {
        const total = Number(group.dataset.visitCount);
        const mine = Number(group.dataset.selfCount);
        const countText = total + ' ' + plural(total, 'visita', 'visitas');
        group.querySelector('.country-count-text').textContent = countText;

        const selfSummary = group.querySelector('.self-summary');
        selfSummary.textContent = '(' + mine + ' ' + plural(mine, 'tuya', 'tuyas') + ')';
        selfSummary.hidden = mine === 0;
        group.querySelector('.country-delete-self').hidden = mine === 0;
        group.querySelector('.country-modal-counts').textContent = countText
            + (mine ? ' · ' + mine + ' ' + plural(mine, 'tuya', 'tuyas') : '');
    }

    function buildRow(row) {
        const tr = document.createElement('tr');
        tr.dataset.visitId = row.id;

        const date = document.createElement('td');
        date.textContent = row.visited_at;

        const check = document.createElement('td');
        check.className = 'visit-check';
        const box = document.createElement('input');
        box.className = 'visit-select';
        box.type = 'checkbox';
        box.value = row.id;
        box.setAttribute('aria-label', 'Seleccionar visita');
        if (row.is_self) box.dataset.self = '1';
        check.appendChild(box);

        // Una línea por dato; las que no traen nada no se pintan.
        function line(className, text) {
            const span = document.createElement('span');
            span.className = className;
            span.textContent = text;
            return span;
        }

        // Origen: IP (con YO), operador, y ciudad · idioma.
        const origin = document.createElement('td');
        origin.className = 'visit-origin';
        const ipLine = document.createElement('span');
        ipLine.className = 'visit-ip';
        // Punto de corte tras cada «:» para que una IPv6 parta por grupos.
        row.ip_address.split(':').forEach((part, index, parts) => {
            ipLine.append(part + (index < parts.length - 1 ? ':' : ''));
            if (index < parts.length - 1) ipLine.appendChild(document.createElement('wbr'));
        });
        if (row.is_self) {
            const badge = document.createElement('span');
            badge.className = 'self-badge';
            badge.textContent = 'YO';
            ipLine.append(' ', badge);
        }
        if (row.bot.length) {
            // Mismo sitio que «YO»: es una marca sobre quién visita.
            const bot = document.getElementById('bot-icon-template').content.firstElementChild.cloneNode(true);
            bot.title = 'Robot probable: ' + row.bot.join('; ');
            bot.setAttribute('aria-label', bot.title);
            ipLine.append(' ', bot);
        }
        origin.appendChild(ipLine);
        if (row.isp) origin.appendChild(line('visit-isp', row.isp));
        if (row.place) origin.appendChild(line('visit-place', row.place));

        const path = document.createElement('td');
        path.className = 'visit-path';
        path.textContent = row.path;

        // Dispositivo: modelo y sistema (si los hay) y debajo el UA
        // completo en pequeño: el dato crudo, para cuando haga falta.
        const agent = document.createElement('td');
        agent.className = 'visit-agent';
        if (row.device) agent.appendChild(line('visit-device', row.device));
        agent.appendChild(line('visit-ua', row.user_agent));

        const actions = document.createElement('td');
        actions.className = 'visit-actions';
        const remove = document.createElement('button');
        remove.className = 'inline-delete';
        remove.type = 'button';
        remove.dataset.confirmDelete = 'one';
        remove.title = 'Eliminar visita';
        remove.setAttribute('aria-label', 'Eliminar visita');
        remove.textContent = '×';
        actions.appendChild(remove);

        tr.append(date, check, origin, path, agent, actions);
        return tr;
    }

    function loadRows(group) {
        if (group.dataset.loading === '1') return;
        group.dataset.loading = '1';

        const status = group.querySelector('.rows-status');
        const loadMore = group.querySelector('.load-more-rows');
        loadMore.hidden = true;
        status.hidden = false;
        status.textContent = 'Cargando visitas…';

        const params = filterParams();
        params.set('group', group.dataset.groupKey);
        params.set('offset', group.dataset.offset || '0');

        fetch(rowsUrl + '?' + params.toString(), {
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        })
            .then(function (response) {
                if (!response.ok) throw new Error('respuesta ' + response.status);
                return response.json();
            })
            .then(function (data) {
                const fragment = document.createDocumentFragment();
                data.rows.forEach(function (row) { fragment.appendChild(buildRow(row)); });
                rowsBody(group).appendChild(fragment);
                group.dataset.offset = String(data.offset);
                loadMore.hidden = !data.has_more;
                const empty = rowsBody(group).children.length === 0;
                status.hidden = !empty;
                if (empty) status.textContent = 'No hay visitas.';
                updateCountryState(group);
            })
            .catch(function () {
                status.hidden = false;
                status.textContent = 'No se pudieron cargar las visitas.';
            })
            .finally(function () { group.dataset.loading = ''; });
    }

    function sendDelete(fields) {
        const body = new FormData();
        body.set('csrfmiddlewaretoken', deleteForm.querySelector('[name="csrfmiddlewaretoken"]').value);
        filterParams().forEach(function (value, name) { body.set(name, value); });
        Object.keys(fields).forEach(function (name) { body.set(name, fields[name]); });

        return fetch(window.location.pathname, {
            method: 'POST',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
            body: body,
        }).then(function (response) {
            if (!response.ok) throw new Error('respuesta ' + response.status);
            return response.json();
        });
    }

    // Borrar sin recargar: el modal del pais sigue abierto y solo
    // desaparecen las filas que se fueron.
    function applyDelete(pending, data) {
        const group = pending.group;
        const headerTotal = document.querySelector('.header .header-counter');
        if (headerTotal) headerTotal.textContent = data.total_visits;
        group.dataset.visitCount = String(data.group_count);
        group.dataset.selfCount = String(data.group_self_count);

        if (!data.group_count) {
            closeCountryModal();
            group.remove();
            if (!document.querySelector('.visit-country-group')) window.location.reload();
            return;
        }

        if (pending.reset) {
            // El servidor ha borrado por país, también filas que aún no
            // se habían pedido: recontar a mano dejaría el desplazamiento
            // torcido y la siguiente tanda se saltaría visitas.
            rowsBody(group).replaceChildren();
            group.dataset.offset = '0';
        } else {
            pending.rows.forEach(function (row) { if (row) row.remove(); });
            group.dataset.offset = String(
                Math.max(Number(group.dataset.offset || 0) - pending.rows.length, 0)
            );
        }

        renderCounts(group);
        updateCountryState(group);
        if (rowsBody(group).children.length === 0) loadRows(group);
    }

    function loadedRows(group, deleteType) {
        const items = checkboxes(group);
        const picked = deleteType === 'selected'
            ? items.filter(function (item) { return item.checked; })
            : deleteType === 'self'
                ? items.filter(function (item) { return item.dataset.self === '1'; })
                : items;
        return picked.map(function (item) { return item.closest('tr'); });
    }

    function syncModalOpenState() {
        const hasOpenCountryModal = countryModals.some(function (countryModal) {
            return !countryModal.hidden;
        });
        document.body.classList.toggle('modal-open', !modal.hidden || hasOpenCountryModal);
    }

    function closeDeleteModal() {
        modal.hidden = true;
        syncModalOpenState();
        pendingDelete = null;
        if (previouslyFocused && document.body.contains(previouslyFocused)) {
            previouslyFocused.focus();
        }
    }

    function openDeleteModal(button) {
        const deleteType = button.dataset.confirmDelete;
        const group = button.closest('.visit-country-group');
        const countryName = group ? group.dataset.country : '';

        if (deleteType === 'one') {
            const row = button.closest('tr');
            pendingDelete = {group: group, rows: [row], fields: {
                delete_one: row.dataset.visitId,
                group: group.dataset.groupKey,
            }};
            modalMessage.textContent = '¿Eliminar esta visita? Esta acción no se puede deshacer.';
        } else if (deleteType === 'selected') {
            const selected = checkboxes(group).filter(function (item) { return item.checked; });
            pendingDelete = selected.length ? {
                group: group,
                rows: loadedRows(group, 'selected'),
                fields: {
                    action: 'delete_selected',
                    selected_visits: selected.map(function (item) { return item.value; }).join(','),
                    group: group.dataset.groupKey,
                },
            } : null;
            modalMessage.textContent = selected.length
                ? '¿Eliminar ' + selected.length + ' visita' + (selected.length === 1 ? ' seleccionada?' : 's seleccionadas?')
                : 'No hay visitas seleccionadas.';
        } else if (deleteType === 'self') {
            // El servidor borra las mias de todo el pais, aunque solo
            // se haya cargado una parte de la tabla.
            const mine = Number(group.dataset.selfCount);
            pendingDelete = mine ? {
                group: group,
                rows: [],
                reset: true,
                fields: {
                    action: 'delete_group',
                    self_only: '1',
                    group: group.dataset.groupKey,
                },
            } : null;
            modalMessage.textContent = mine
                ? '¿Eliminar ' + (mine === 1 ? 'tu única visita de ' : 'tus ' + mine + ' visitas de ')
                    + countryName + '? Esta acción no se puede deshacer.'
                : 'No hay visitas tuyas en ' + countryName + '.';
        } else if (deleteType === 'country') {
            const total = Number(group.dataset.visitCount);
            pendingDelete = {
                group: group,
                rows: loadedRows(group, 'country'),
                fields: {action: 'delete_group', group: group.dataset.groupKey},
            };
            modalMessage.textContent = '¿Eliminar ' + (total === 1 ? 'la visita de ' : 'las ' + total + ' visitas de ')
                + countryName + '? Esta acción no se puede deshacer.';
        } else if (deleteType === 'bots') {
            const bots = Number(button.dataset.botCount);
            pendingDelete = {reload: true, fields: {action: 'delete_bots'}};
            modalMessage.textContent = '¿Eliminar ' + (bots === 1 ? 'la visita marcada' : 'las ' + bots + ' visitas marcadas')
                + ' como robot probable? Solo las del filtro actual. Esta acción no se puede deshacer.';
        } else {
            pendingDelete = {reload: true, fields: {action: 'delete_all_filtered'}};
            modalMessage.textContent = '¿Eliminar todas las visitas del filtro actual? Si no hay filtros activos, se eliminarán todas. Esta acción no se puede deshacer.';
        }

        confirmDelete.hidden = pendingDelete === null;
        previouslyFocused = document.activeElement;
        modal.hidden = false;
        syncModalOpenState();
        (confirmDelete.hidden ? cancelDelete : confirmDelete).focus();
    }

    function closeCountryModal() {
        if (!activeCountryModal) return;
        activeCountryModal.hidden = true;
        activeCountryModal = null;
        syncModalOpenState();
        if (countryModalOpener && document.body.contains(countryModalOpener)) {
            countryModalOpener.focus();
        }
        countryModalOpener = null;
    }

    groups.forEach(function (group) {
        const master = group.querySelector('.select-country-visits');
        master.addEventListener('change', function () {
            checkboxes(group).forEach(function (item) { item.checked = master.checked; });
            updateCountryState(group);
        });
        group.querySelector('.load-more-rows').addEventListener('click', function () {
            loadRows(group);
        });
        // Delegacion: las filas llegan despues de cargar la pagina, y
        // con miles de casillas un listener por casilla se nota.
        group.addEventListener('change', function (event) {
            if (event.target.classList.contains('visit-select')) updateCountryState(group);
        });
    });

    document.querySelectorAll('[data-country-modal-target]').forEach(function (button) {
        button.addEventListener('click', function () {
            const countryModal = document.getElementById(button.dataset.countryModalTarget);
            if (!countryModal) return;
            const group = button.closest('.visit-country-group');
            activeCountryModal = countryModal;
            countryModalOpener = button;
            countryModal.hidden = false;
            syncModalOpenState();
            countryModal.querySelector('.country-modal-close').focus();
            if (!rowsBody(group).children.length) loadRows(group);
        });
    });

    countryModals.forEach(function (countryModal) {
        countryModal.querySelectorAll('[data-close-country-modal]').forEach(function (button) {
            button.addEventListener('click', closeCountryModal);
        });
    });

    document.addEventListener('click', function (event) {
        const button = event.target.closest('[data-confirm-delete]');
        if (!button) return;
        event.preventDefault();
        openDeleteModal(button);
    });

    confirmDelete.addEventListener('click', function () {
        const pending = pendingDelete;
        if (!pending) return;
        modal.hidden = true;
        syncModalOpenState();
        pendingDelete = null;
        confirmDelete.disabled = true;

        sendDelete(pending.fields)
            .then(function (data) {
                if (pending.reload) {
                    window.location.reload();
                    return;
                }
                applyDelete(pending, data);
            })
            .catch(function () { window.location.reload(); })
            .finally(function () { confirmDelete.disabled = false; });
    });

    cancelDelete.addEventListener('click', closeDeleteModal);
    modal.querySelector('[data-close-delete-modal]').addEventListener('click', closeDeleteModal);
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        if (!modal.hidden) {
            closeDeleteModal();
        } else {
            closeCountryModal();
        }
    });

    groups.forEach(updateCountryState);
})();
