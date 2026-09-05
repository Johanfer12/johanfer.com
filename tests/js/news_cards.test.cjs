const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function runtime(extra = {}) {
    let nextId = 0;
    const frames = new Map();
    const timers = new Map();
    const events = new Map();
    const document = {readyState: 'loading', addEventListener: (name, fn) => events.set(name, fn)};
    const context = vm.createContext({
        document, console, URL, Set, Map,
        requestAnimationFrame: fn => { frames.set(++nextId, fn); return nextId; },
        cancelAnimationFrame: id => frames.delete(id),
        setTimeout: fn => { timers.set(++nextId, fn); return nextId; },
        clearTimeout: id => timers.delete(id),
        ...extra,
    });
    context.window = context;
    context.innerWidth = 1200;
    context.innerHeight = 800;
    context.matchMedia = () => ({matches: false});
    context.addEventListener = () => {};
    return {
        context, events, frames, timers,
        frame() { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn()); },
        timeout() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); },
        load(file) { vm.runInContext(fs.readFileSync(path.join(__dirname, '../../static/js', file), 'utf8'), context); },
    };
}

function card(id, trace = []) {
    const listeners = new Map();
    return {
        id, isConnected: true, dataset: {newsId: id},
        style: new Proxy({transform: '', transition: '', willChange: ''}, {
            set(target, key, value) { trace.push('write'); target[key] = value; return true; },
        }),
        getBoundingClientRect() { trace.push('read'); return {left: 0, top: 0, bottom: 200, width: 300, height: 200}; },
        addEventListener: (name, fn) => listeners.set(name, fn),
        removeEventListener: name => listeners.delete(name),
        end(propertyName = 'transform') { listeners.get('transitionend')?.({target: this, propertyName}); },
    };
}

test('reposition batches geometry before styles and settles once for the entire grid', () => {
    const run = runtime(); run.load('news_cards_common.js');
    const trace = [];
    const cards = Array.from({length: 25}, (_, i) => card(String(i), trace));
    let settled = 0;
    run.context.NewsCards.animateReposition(new Map(cards.map(c => [c, {left: 320, top: 0}])), {onSettled: () => settled++});
    run.frame();
    assert.deepEqual(trace.slice(0, 25), Array(25).fill('read'));
    assert.equal(trace.slice(25).includes('read'), false);
    assert.equal(run.frames.size, 1);
    run.frame();
    assert.equal(run.timers.size, 1);
    cards[0].end('opacity');
    assert.equal(settled, 0);
    cards.slice(0, -1).forEach(c => c.end());
    assert.equal(settled, 0);
    cards.at(-1).end();
    run.timeout();
    assert.equal(settled, 1);
    assert.ok(cards.every(c => c.style.willChange === '' && c.style.transition === ''));
});

test('rapid consecutive removals cancel stale callbacks and preserve the new animation', () => {
    const run = runtime(); run.load('news_cards_common.js');
    const c = card('1'); let oldSettled = 0; let newSettled = 0;
    run.context.NewsCards.animateReposition(new Map([[c, {left: 300, top: 0}]]), {onSettled: () => oldSettled++});
    run.frame(); run.frame();
    run.context.NewsCards.animateReposition(new Map([[c, {left: 150, top: 0}]]), {onSettled: () => newSettled++});
    run.frame();
    assert.equal(c.style.transform, 'translate3d(150px,0px,0)');
    run.timeout();
    assert.equal(c.style.transform, 'translate3d(150px,0px,0)');
    run.frame(); run.timeout();
    assert.equal(oldSettled, 0);
    assert.equal(newSettled, 1);
    assert.equal(c.style.transform, '');
});

test('no movement, detached cards and reduced motion still settle without lingering styles', () => {
    const run = runtime(); run.load('news_cards_common.js');
    const c = card('1'); let settled = 0;
    const options = {onSettled: () => settled++};
    run.context.NewsCards.animateReposition(new Map([[c, {left: 0, top: 0}]]), options);
    run.frame();
    c.isConnected = false;
    run.context.NewsCards.animateReposition(new Map([[c, {left: 100, top: 0}]]), options);
    run.frame();
    run.context.matchMedia = () => ({matches: true});
    run.context.NewsCards.animateReposition(new Map([[c, {left: 100, top: 0}]]), options);
    assert.equal(settled, 3);
    assert.equal(run.frames.size + run.timers.size, 0);
});

function publicFeed({storageBlocked = false, initial = false} = {}) {
    const run = runtime();
    const nodes = new Map();
    const gridEvents = new Map();
    const current = [];
    const makeCard = id => Object.assign(card(id), {
        classList: {add() {}, remove() {}, contains() { return false; }, toggle() {}},
        querySelectorAll: () => [],
        removeAttribute() {},
        cloneNode: () => makeCard('clone'),
        remove() { const i = current.indexOf(this); if (i >= 0) current.splice(i, 1); },
    });
    const grid = {addEventListener: (name, fn) => gridEvents.set(name, fn), appendChild: c => current.push(c)};
    const retry = {addEventListener: (name, fn) => { retry.click = fn; }};
    const error = {hidden: true};
    nodes.set('#public-news-grid', grid);
    nodes.set('#public-news-counter', {dataset: {totalNews: '5'}});
    nodes.set('#public-news-page-data', {textContent: JSON.stringify({page_size: 1, current_page: 1, total_pages: 3})});
    nodes.set('#public-news-retry-btn', retry);
    nodes.set('#public-news-load-error', error);
    Object.assign(run.context.document, {querySelector: selector => nodes.get(selector), body: {appendChild() {}}});
    let scans = 0;
    run.context.NewsCards = {
        cards: () => current, isMobile: () => false,
        addMobileDeleteButton() {}, bindImageFallbacks() {}, fitCardText() {},
        capturePositions: () => new Map(), animateReposition() {},
        activeCards: () => { scans++; return []; }, resetFlipState() {},
    };
    run.context.localStorage = {
        getItem: () => '[]',
        setItem() { if (storageBlocked) throw new Error('QuotaExceededError'); },
    };
    run.context.location = {href: 'https://example.test/noticias/'};
    const requests = [];
    run.context.fetch = async url => {
        requests.push(url);
        return {ok: requests.length > 1, status: 503, text: async () => 'fixture'};
    };
    run.context.console = {warn() {}};
    run.context.DOMParser = class { parseFromString() { return {querySelectorAll: () => [makeCard('2')]}; } };
    if (initial) current.push(makeCard('1'));
    run.load('news_public.js');
    return {run, retry, error, requests, current, gridEvents, scans: () => scans};
}

test('failed refill offers retry and requests the SAME page instead of skipping news', async () => {
    const {retry, error, requests, current} = publicFeed();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(error.hidden, false);
    assert.equal(retry.disabled, false);
    await retry.click();
    assert.equal(requests.length, 2);
    assert.equal(requests[0], requests[1]);
    assert.equal(new URL(requests[1]).searchParams.get('page'), '2');
    assert.equal(error.hidden, true);
    assert.equal(current.length, 1);
});

test('blocked storage does not interrupt hiding a card', () => {
    const {current, gridEvents} = publicFeed({storageBlocked: true, initial: true});
    const button = {dataset: {id: '1'}, closest: () => current[0]};
    assert.doesNotThrow(() => gridEvents.get('click')({
        target: {closest: () => button}, preventDefault() {}, stopPropagation() {},
    }));
    assert.equal(current.length, 0);
});

test('100 mousemove events do only one hover pass per frame', () => {
    const {run, scans} = publicFeed({initial: true});
    const move = run.events.get('mousemove');
    for (let i = 0; i < 100; i++) move({target: {closest: () => null}});
    assert.equal(scans(), 0);
    assert.equal(run.frames.size, 1);
    run.frame();
    assert.equal(scans(), 1);
});
