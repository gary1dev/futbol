/* RojaDirecta Dashboard — app.js */

// En Netlify: /api/datos → redirigido a /.netlify/functions/datos (netlify.toml)
// En local con Flask: http://localhost:5000/api/datos (Flask lo sirve directamente)
const API_URL   = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:5000/api/datos'
    : '/api/datos';
const DATA_FILE = '/data/iacip_datos.json';

// ── Colores por competición ───────────────────────────────
const COMP_COLORS = {
    libertadores: '#f59e0b',
    sudamericana: '#3b82f6',
    champions:    '#8b5cf6',
    premier:      '#10b981',
    laliga:       '#ef4444',
    liga_mx:      '#06b6d4',
    bundesliga:   '#f97316',
    serie_a:      '#0ea5e9',
    mundial:      '#22c55e',
    amistoso:     '#94a3b8',
    otro:         '#6b7280',
};

// ── Tema ──────────────────────────────────────────────────
const root      = document.documentElement;
const toggleBtn = document.getElementById('theme-toggle');
const saved     = localStorage.getItem('theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
root.setAttribute('data-theme', saved);
toggleBtn.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
});

// ── DOM ───────────────────────────────────────────────────
const grid          = document.getElementById('content-grid');
const emptyState    = document.getElementById('empty-state');
const searchInput   = document.getElementById('search-input');
const catFilter     = document.getElementById('category-filter');
const refreshBtn    = document.getElementById('btn-refresh');
const refreshIcon   = document.getElementById('refresh-icon');
const statusEl      = document.getElementById('scraper-status');
const statusText    = statusEl ? statusEl.querySelector('.status-text') : null;  // fix #1 null-safe
const statPartidos  = document.getElementById('total-partidos');
const statCanales   = document.getElementById('total-canales');
const statComps     = document.getElementById('total-comps');
const statFecha     = document.getElementById('ultima-actualizacion');
const lastFetchEl   = document.getElementById('last-fetch-time');

let allData = [];

// ── Utilidades ────────────────────────────────────────────
function setStatus(state, text) {
    if (!statusEl) return;
    // fix: clase nunca queda "status-indicator " con espacio suelto
    statusEl.className = state ? `status-indicator ${state}` : 'status-indicator';
    if (statusText) statusText.textContent = text;
}

function formatTime(iso) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
}

// fix #3: escapa también comilla simple para contextos HTML
function esc(str = '') {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// fix #10: parte por ' - ' (espacio-guión-espacio) para no cortar nombres compuestos
function splitEquipos(equipos = '') {
    const sep = equipos.indexOf(' - ');
    if (sep > -1) return [equipos.slice(0, sep), equipos.slice(sep + 3)];
    const mid = equipos.indexOf('-');
    if (mid > -1) return [equipos.slice(0, mid).trim(), equipos.slice(mid + 1).trim()];
    return [equipos, '?'];
}

// fix #1: solo permite URLs http/https antes de asignarlas al iframe
function safeUrl(url = '') {
    return /^https?:\/\//i.test(url) ? url : '';
}

// ── Renderizado de tarjeta de partido ─────────────────────
function renderCard(p) {
    const color   = COMP_COLORS[p.categoria] || COMP_COLORS.otro;
    const comp    = esc(p.competicion);
    const canales = (p.canales || []).map(c => {
        const url = safeUrl(c.url);
        if (!url) return '';
        return `
        <button class="canal-btn"
            style="--canal-color:${color}"
            data-url="${esc(url)}"
            data-equipos="${esc(p.equipos)}"
            data-canal="${esc(c.nombre)}"
            data-comp="${esc(p.competicion)}">
            <span class="canal-nombre">${esc(c.nombre)}</span>
            <span class="canal-calidad">${esc(c.calidad)}</span>
        </button>`;
    }).join('');

    const [equipo1, equipo2] = splitEquipos(p.equipos);

    return `
    <div class="data-card" style="--comp-color:${color}">
        <div class="card-top">
            <span class="card-tag">${comp}</span>
            <span class="card-hora">🕐 ${esc(p.hora || '—')}</span>
        </div>
        <div class="match-row">
            <span class="equipo">${esc(equipo1 || '?')}</span>
            <span class="vs">VS</span>
            <span class="equipo equipo-right">${esc(equipo2 || '?')}</span>
        </div>
        <div class="canales-row">${canales || '<span class="sin-canales">Sin canales</span>'}</div>
    </div>`;
}

// ── Player modal ──────────────────────────────────────────
const overlay       = document.getElementById('player-overlay');
const iframe        = document.getElementById('player-iframe');
const playerComp    = document.getElementById('player-comp');
const playerMatch   = document.getElementById('player-match');
const btnClose      = document.getElementById('player-close');
const btnReload     = document.getElementById('player-reload');
const btnFullscreen = document.getElementById('player-fullscreen');
const btnReport     = document.getElementById('player-report');

let currentUrl = '';
let _noLoadTimer = null;
const noLoadMsg = document.getElementById('player-no-load');

function showNoLoad(show) {
    if (!noLoadMsg) return;
    noLoadMsg.style.display = show ? 'flex' : 'none';
    btnReload.classList.toggle('player-btn-pulse', show);
}

function openPlayer(url, equipos, canal, comp) {
    const safe = safeUrl(url);
    if (!safe) return;
    currentUrl = safe;
    playerComp.textContent  = comp || 'EN VIVO';
    playerMatch.textContent = `${equipos}  —  ${canal}`;
    showNoLoad(false);
    iframe.src = safe;
    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Si en 12 s el iframe sigue sin cargar, avisa al usuario
    clearTimeout(_noLoadTimer);
    _noLoadTimer = setTimeout(() => showNoLoad(true), 12000);
    iframe.onload = () => { clearTimeout(_noLoadTimer); showNoLoad(false); };
}

function closePlayer() {
    clearTimeout(_noLoadTimer);
    showNoLoad(false);
    overlay.style.display = 'none';
    iframe.src = '';
    iframe.onload = null;
    currentUrl = '';
    document.body.style.overflow = '';
}

btnClose.addEventListener('click', closePlayer);
overlay.addEventListener('click', e => { if (e.target === overlay) closePlayer(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePlayer(); });

btnReload.addEventListener('click', () => {
    if (currentUrl) { iframe.src = ''; setTimeout(() => { iframe.src = currentUrl; }, 80); }
});

btnFullscreen.addEventListener('click', () => {
    if (iframe.requestFullscreen)            iframe.requestFullscreen();
    else if (iframe.webkitRequestFullscreen) iframe.webkitRequestFullscreen();
    else if (iframe.mozRequestFullScreen)    iframe.mozRequestFullScreen();
});

btnReport.addEventListener('click', () => {
    const msg = `Problema con: ${playerMatch.textContent}\nURL: ${currentUrl}`;
    alert(`Reporte registrado.\n\n${msg}\n\nGracias por avisar.`);
});

// ── Filtrado ──────────────────────────────────────────────
function applyFilters() {
    const q   = searchInput.value.toLowerCase().trim();
    const cat = catFilter.value;
    const filtered = allData.filter(p => {
        const haystack = `${p.titulo} ${p.equipos} ${p.competicion}`.toLowerCase();
        return (!cat || p.categoria === cat) && (!q || haystack.includes(q));
    });
    if (!filtered.length) {
        grid.innerHTML = '';
        emptyState.style.display = 'flex';
    } else {
        emptyState.style.display = 'none';
        grid.innerHTML = filtered.map(renderCard).join('');
    }
}

searchInput.addEventListener('input', applyFilters);
catFilter.addEventListener('change', applyFilters);

grid.addEventListener('click', e => {
    const btn = e.target.closest('.canal-btn');
    if (!btn) return;
    openPlayer(btn.dataset.url, btn.dataset.equipos, btn.dataset.canal, btn.dataset.comp);
});

// ── Stats ─────────────────────────────────────────────────
function updateStats(datos, meta = {}) {
    const totalCanales = datos.reduce((s, p) => s + (p.canales || []).length, 0);
    const comps        = new Set(datos.map(p => p.categoria)).size;
    statPartidos.textContent = datos.length;
    statCanales.textContent  = totalCanales;
    statComps.textContent    = comps;
    statFecha.textContent    = formatTime(meta.fecha_extraccion) || '—';
    lastFetchEl.textContent  = `Scrapeado: ${new Date(meta.fecha_extraccion || Date.now()).toLocaleString('es-MX')}`;
}

// ── Carga de datos ────────────────────────────────────────
let _loading = false;  // fix #8: guard contra llamadas concurrentes

async function loadData() {
    if (_loading) return;
    _loading = true;
    refreshIcon.classList.add('spinning');
    setStatus('', 'Cargando...');
    grid.innerHTML = '<div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div>';
    emptyState.style.display = 'none';

    let payload = null;

    try {
        const res = await fetch(API_URL, { signal: AbortSignal.timeout(4000) });
        if (res.ok) { payload = await res.json(); setStatus('active', 'API activa'); }
    } catch { /* sin API — usa archivo */ }

    if (!payload) {
        try {
            const res = await fetch(DATA_FILE, { signal: AbortSignal.timeout(4000) });
            if (res.ok) { payload = await res.json(); setStatus('active', 'Archivo local'); }
        } catch { /* nada */ }
    }

    if (payload) {
        allData = payload.datos || payload;
        updateStats(allData, payload.meta || {});
        applyFilters();
    } else {
        setStatus('error', 'Sin datos');
        grid.innerHTML = '';
        emptyState.style.display = 'flex';
    }

    refreshIcon.classList.remove('spinning');
    _loading = false;
}

refreshBtn.addEventListener('click', loadData);
loadData();
