// Netlify Function — /api/datos
// Node.js 18+ (fetch nativo, sin dependencias)
// Obtiene partidos del día desde mundofutbolcol.online en tiempo real.

const BASE_URL = "https://mundofutbolcol.online";

const HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL + "/",
    "Accept-Language": "es-CO,es;q=0.9",
};

const COMP_MAP = {
    "libertadores": "libertadores",
    "sudamericana": "sudamericana",
    "champions":    "champions",
    "premier":      "premier",
    "laliga":       "laliga",
    "liga mx":      "liga_mx",
    "bundesliga":   "bundesliga",
    "serie a":      "serie_a",
    "ligue 1":      "ligue_1",
    "mundial":      "mundial",
    "amistoso":     "amistoso",
    "mls":          "mls",
};

const STREAM_NAMES = {
    "espn": "ESPN", "espn2": "ESPN 2", "espn3": "ESPN 3",
    "espn4": "ESPN 4", "espn5": "ESPN 5", "espn6": "ESPN 6",
    "espn7": "ESPN 7", "espnpremium": "ESPN Premium",
    "espndeportes": "ESPN Deportes",
    "foxsports": "Fox Sports", "foxsports2": "Fox Sports 2",
    "foxsports2_usa": "Fox Sports 2", "foxsports3": "Fox Sports 3",
    "foxdeportes": "Fox Deportes", "foxsportsmx": "Fox Sports MX",
    "winsports": "Win Sports", "winsportsplus": "Win Sports+",
    "tycsports": "TyC Sports", "tntsports": "TNT Sports",
    "tntsportschile": "TNT Sports Chile",
    "dsports": "DirecTV Sports", "dsportsplus": "DirecTV Sports+",
    "beinsportes": "beIN Sports", "dazn1": "DAZN 1", "dazn2": "DAZN 2",
    "tudn": "TUDN", "tudn_mx": "TUDN MX", "premiere1": "Premiere",
    "liga1max": "Liga1 MAX", "sportv": "Sportv", "mls1en": "MLS",
};

function clasificar(comp) {
    const t = comp.toLowerCase();
    for (const [clave, slug] of Object.entries(COMP_MAP)) {
        if (t.includes(clave)) return slug;
    }
    return "otro";
}

function canalNombre(url) {
    const m = url.match(/[?&]stream=([^&]+)/);
    if (m) {
        const key = m[1].toLowerCase().replace(/\+/g, "plus").replace(/-/g, "");
        return STREAM_NAMES[key] || m[1].toUpperCase();
    }
    return url.split("/").pop() || "Canal";
}

// Decodifica la apiUrl ofuscada con XOR + clave base32 de Math.SQRT2
function decodeApiUrl() {
    const encoded = [
        80,64,1,19,3,76,69,65,82,85,24,10,19,30,5,15,
        91,85,27,78,3,21,24,15,72,81,7,77,23,25,11,2,
        21,88,28,21,21,91,11,30,72,26,2,12,2,29,15,28,
        75,26,17,6,6,89,
    ];
    // Replica Math.SQRT2.toString(32).slice(3,11) de JavaScript
    const _k = Math.SQRT2.toString(32).slice(3, 11);
    return encoded.map((c, i) => String.fromCharCode(c ^ _k.charCodeAt(i % _k.length))).join("");
}

// Extrae el bloque del array EVENTOS_MANUALES usando conteo de corchetes
function extractArrayBlock(js) {
    const idx = js.indexOf("EVENTOS_MANUALES");
    if (idx === -1) return null;
    const start = js.indexOf("[", idx);
    if (start === -1) return null;
    let depth = 0;
    for (let i = start; i < js.length; i++) {
        if (js[i] === "[") depth++;
        else if (js[i] === "]") {
            depth--;
            if (depth === 0) return js.slice(start, i + 1);
        }
    }
    return null;
}

function parseJs(js) {
    const raw = extractArrayBlock(js);
    if (!raw) return [];

    const pattern = /\{\s*time\s*:\s*['"]([^'"]+)['"]\s*,\s*comp\s*:\s*['"]([^'"]+)['"]\s*,\s*home\s*:\s*['"]([^'"]+)['"]\s*,\s*away\s*:\s*['"]([^'"]+)['"]\s*,\s*channels\s*:\s*\[([^\]]*)\]/g;

    const partidos = [];
    let m;
    while ((m = pattern.exec(raw)) !== null) {
        const [, hora, comp, home, away, chansRaw] = m;
        const chanUrls = [...chansRaw.matchAll(/['"]([^'"]+)['"]/g)]
            .map(x => x[1])
            .filter(u => u.startsWith("http"));
        const canales = chanUrls.map(u => ({ nombre: canalNombre(u), calidad: "HD", url: u }));
        partidos.push({
            titulo:      `${comp}: ${home} vs ${away}`,
            competicion: comp,
            equipos:     `${home} - ${away}`,
            hora,
            canales,
            categoria:   clasificar(comp),
            fecha:       new Date().toISOString().slice(0, 19),
        });
    }
    return partidos;
}

function normalizeApiEvents(events) {
    return events.map(item => {
        const home  = item.homeTeam || item.local  || item.home  || "";
        const away  = item.awayTeam || item.visitor || item.away  || "";
        const comp  = item.league   || item.competition || item.comp || "Fútbol";
        const hora  = item.time     || item.hora   || "";
        const chans = item.channels || item.signals || item.canales || [];
        const canales = chans.map(ch => {
            if (typeof ch === "string") return { nombre: canalNombre(ch), calidad: "HD", url: ch };
            return {
                nombre:  ch.name    || "Canal",
                calidad: ch.quality || "HD",
                url:     ch.url     || ch.stream || "",
            };
        });
        return {
            titulo:      `${comp}: ${home} vs ${away}`,
            competicion: comp,
            equipos:     `${home} - ${away}`,
            hora,
            canales,
            categoria:   clasificar(comp),
            fecha:       new Date().toISOString().slice(0, 19),
        };
    });
}

// Fetch con timeout compatible con todas las versiones de Node 18
function fetchConTimeout(url, options, ms) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    return fetch(url, { ...options, signal: controller.signal })
        .finally(() => clearTimeout(timer));
}

async function fetchDatos() {
    // 1. Intenta Cloudflare Worker
    try {
        const apiUrl = decodeApiUrl();
        console.log("[datos] Intentando API:", apiUrl);
        const res = await fetchConTimeout(
            apiUrl,
            { headers: { ...HEADERS, Accept: "application/json" } },
            3500
        );
        if (res.ok) {
            const data = await res.json();
            const events = Array.isArray(data) ? data
                : data.events || data.matches || data.data || data.result || [];
            if (events.length > 0) {
                console.log("[datos] API OK:", events.length, "eventos");
                return normalizeApiEvents(events);
            }
        }
        console.log("[datos] API status:", res.status, "— pasando a fallback");
    } catch (e) {
        console.log("[datos] API error:", e.message, "— pasando a fallback");
    }

    // 2. Parsea EVENTOS_MANUALES desde app-pc.js
    try {
        console.log("[datos] Descargando app-pc.js...");
        const res = await fetchConTimeout(
            `${BASE_URL}/app-pc.js`,
            { headers: HEADERS },
            5000
        );
        if (res.ok) {
            const js = await res.text();
            const partidos = parseJs(js);
            console.log("[datos] app-pc.js OK:", partidos.length, "partidos");
            return partidos;
        }
        console.log("[datos] app-pc.js status:", res.status);
    } catch (e) {
        console.log("[datos] app-pc.js error:", e.message);
    }

    console.log("[datos] Sin datos de ninguna fuente");
    return [];
}

// CommonJS export — máxima compatibilidad con Netlify Functions
exports.handler = async () => {
    try {
        const datos = await fetchDatos();
        return {
            statusCode: 200,
            headers: {
                "Content-Type":                "application/json",
                "Cache-Control":               "public, max-age=120",
                "Access-Control-Allow-Origin": "*",
            },
            body: JSON.stringify({
                meta: {
                    fuente:           BASE_URL,
                    fecha_extraccion: new Date().toISOString(),
                    total:            datos.length,
                },
                datos,
            }),
        };
    } catch (err) {
        return {
            statusCode: 500,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ error: err.message }),
        };
    }
};
