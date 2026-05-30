"""
Scraper — mundofutbolcol.online
Extrae EVENTOS_MANUALES de app-pc.js (datos reales del día).
Como respaldo intenta la API del Cloudflare Worker.
"""

import json
import math
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL    = "https://mundofutbolcol.online"
OUTPUT_DIR  = Path(__file__).parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "iacip_datos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL + "/",
    "Accept-Language": "es-CO,es;q=0.9",
}

COMP_MAP = {
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
}

# Mapa de parámetro stream → nombre legible del canal
STREAM_NAMES = {
    "espn":          "ESPN",
    "espn2":         "ESPN 2",
    "espn3":         "ESPN 3",
    "espn4":         "ESPN 4",
    "espn5":         "ESPN 5",
    "espn6":         "ESPN 6",
    "espn7":         "ESPN 7",
    "espnpremium":   "ESPN Premium",
    "espndeportes":  "ESPN Deportes",
    "foxsports":     "Fox Sports",
    "foxsports2":    "Fox Sports 2",
    "foxsports2_usa":"Fox Sports 2",
    "foxsports3":    "Fox Sports 3",
    "foxdeportes":   "Fox Deportes",
    "foxsportsmx":   "Fox Sports MX",
    "winsports":     "Win Sports",
    "winsportsplus": "Win Sports+",
    "tycsports":     "TyC Sports",
    "tntsports":     "TNT Sports",
    "tntsportschile":"TNT Sports Chile",
    "dsports":       "DirecTV Sports",
    "dsportsplus":   "DirecTV Sports+",
    "beinsportes":   "beIN Sports",
    "dazn1":         "DAZN 1",
    "dazn2":         "DAZN 2",
    "tudn":          "TUDN",
    "tudn_mx":       "TUDN MX",
    "premiere1":     "Premiere",
    "liga1max":      "Liga1 MAX",
    "sportv":        "Sportv",
    "mls1en":        "MLS",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def clasificar(comp: str) -> str:
    t = comp.lower()
    for clave, slug in COMP_MAP.items():
        if clave in t:
            return slug
    return "otro"


def canal_nombre(url: str) -> str:
    """Extrae nombre legible desde la URL del canal."""
    m = re.search(r"[?&]stream=([^&]+)", url)
    if m:
        key = m.group(1).lower().replace("+", "plus").replace("-", "")
        return STREAM_NAMES.get(key, m.group(1).upper())
    return url.split("/")[-1] or "Canal"


def fetch_js() -> str | None:
    url = f"{BASE_URL}/app-pc.js"
    try:
        time.sleep(1.5)
        r = requests.get(url, headers=HEADERS, timeout=(5, 12))
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text
    except requests.RequestException as e:
        log.warning("Error descargando app-pc.js — %s", e)
        return None


def _extract_array_block(js: str) -> str | None:
    """
    fix #9: extrae el bloque del array EVENTOS_MANUALES usando conteo de
    corchetes en lugar de regex greedy, evitando truncamiento si alguna
    URL contiene la secuencia '];'.
    """
    marker = "EVENTOS_MANUALES"
    idx = js.find(marker)
    if idx == -1:
        return None
    start = js.find("[", idx)
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(js[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return js[start : i + 1]
    return None


def parse_eventos_manuales(js: str) -> list[dict]:
    raw = _extract_array_block(js)
    if raw is None:
        log.warning("EVENTOS_MANUALES no encontrado en el JS")
        return []

    # Extrae cada objeto del array
    partidos: list[dict] = []
    item_pattern = re.compile(
        r"\{\s*time\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*comp\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*home\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*away\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*channels\s*:\s*\[([^\]]*)\]",
        re.DOTALL,
    )

    for m in item_pattern.finditer(raw):
        hora, comp, home, away, chans_raw = m.groups()

        # Extrae URLs de channels
        chan_urls = re.findall(r"['\"]([^'\"]+)['\"]", chans_raw)
        canales = [
            {"nombre": canal_nombre(u), "calidad": "HD", "url": u}
            for u in chan_urls if u.startswith("http")
        ]

        partidos.append({
            "titulo":      f"{comp}: {home} vs {away}",
            "competicion": comp,
            "equipos":     f"{home} - {away}",
            "hora":        hora,
            "canales":     canales,
            "categoria":   clasificar(comp),
            "fecha":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        })
        log.info("  + %s | %s vs %s (%d canales)", hora, home, away, len(canales))

    return partidos


def _js_to_base32(n: float) -> str:
    """Replica Number.prototype.toString(32) de JavaScript."""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    int_part = int(n)
    frac = n - int_part
    s = ""
    tmp = int_part
    while tmp > 0:
        s = digits[tmp % 32] + s
        tmp //= 32
    s = (s or "0") + "."
    for _ in range(52):
        frac *= 32
        d = min(int(frac), 31)  # fix #7: clamp evita IndexError por acumulación de error float
        frac -= d
        s += digits[d]
        if frac == 0:
            break
    return s


def decode_api_url(encoded: list[int]) -> str:
    b32 = _js_to_base32(math.sqrt(2))
    _k  = b32[3:11]
    return "".join(chr(c ^ ord(_k[i % len(_k)])) for i, c in enumerate(encoded))


def fetch_from_api() -> list[dict]:
    """Intenta obtener eventos desde el Cloudflare Worker."""
    encoded = [80,64,1,19,3,76,69,65,82,85,24,10,19,30,5,15,91,85,27,78,
               3,21,24,15,72,81,7,77,23,25,11,2,21,88,28,21,21,91,11,30,
               72,26,2,12,2,29,15,28,75,26,17,6,6,89]
    api_url = decode_api_url(encoded)
    log.info("API URL: %s", api_url)
    try:
        r = requests.get(
            api_url,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=(5, 10),  # (connect, read) — evita bloqueo en servidores lentos
        )
        if not r.ok:
            log.warning("API retornó %d", r.status_code)
            return []
        data = r.json()
        events = (data if isinstance(data, list)
                  else data.get("events") or data.get("matches")
                  or data.get("data") or data.get("result") or [])
        log.info("  → %d eventos desde API", len(events))
        partidos = []
        for item in events:
            home  = item.get("homeTeam") or item.get("local") or item.get("home") or ""
            away  = item.get("awayTeam") or item.get("visitor") or item.get("away") or ""
            comp  = item.get("league") or item.get("competition") or item.get("comp") or "Fútbol"
            hora  = item.get("time") or item.get("hora") or ""
            chans = item.get("channels") or item.get("signals") or item.get("canales") or []
            canales = []
            for ch in chans:
                if isinstance(ch, str):
                    canales.append({"nombre": canal_nombre(ch), "calidad": "HD", "url": ch})
                elif isinstance(ch, dict):
                    canales.append({
                        "nombre":  ch.get("name") or "Canal",
                        "calidad": ch.get("quality") or "HD",
                        "url":     ch.get("url") or ch.get("stream") or "",
                    })
            partidos.append({
                "titulo":      f"{comp}: {home} vs {away}",
                "competicion": comp,
                "equipos":     f"{home} - {away}",
                "hora":        hora,
                "canales":     canales,
                "categoria":   clasificar(comp),
                "fecha":       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            })
        return partidos
    except requests.RequestException as e:
        log.warning("Error de red en API: %s", e)
        return []
    except ValueError as e:
        log.warning("Respuesta no-JSON desde API (¿bloqueo Cloudflare?): %s", e)
        return []
    except Exception as e:
        log.warning("Error inesperado en API: %s", e)
        return []


def save(datos: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "fuente":           BASE_URL,
            "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
            "total":            len(datos),
        },
        "datos": datos,
    }
    # Escritura atómica: escribe en .tmp y luego reemplaza, evitando JSON truncado
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, OUTPUT_FILE)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    log.info("Guardado: %s (%d partidos)", OUTPUT_FILE, len(datos))


def main() -> None:
    log.info("=== Scraper mundofutbolcol.online ===")

    # 1. Intenta API primero (datos dinámicos)
    datos = fetch_from_api()

    # 2. Si la API falla, lee EVENTOS_MANUALES del JS
    if not datos:
        log.info("API no disponible — leyendo EVENTOS_MANUALES del JS")
        js = fetch_js()
        if js:
            datos = parse_eventos_manuales(js)

    if datos:
        save(datos)
        log.info("=== Finalizado: %d partidos ===", len(datos))
    else:
        log.error("No se obtuvieron datos de ninguna fuente")


if __name__ == "__main__":
    main()
