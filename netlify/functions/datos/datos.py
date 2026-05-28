"""
Netlify Function — /api/datos
Obtiene los partidos del día desde mundofutbolcol.online en tiempo real.
Intenta primero la API del Cloudflare Worker; si falla, parsea EVENTOS_MANUALES del JS.
"""

import json
import re
import math
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://mundofutbolcol.online"

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

STREAM_NAMES = {
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
}


def clasificar(comp: str) -> str:
    t = comp.lower()
    for clave, slug in COMP_MAP.items():
        if clave in t:
            return slug
    return "otro"


def canal_nombre(url: str) -> str:
    m = re.search(r"[?&]stream=([^&]+)", url)
    if m:
        key = m.group(1).lower().replace("+", "plus").replace("-", "")
        return STREAM_NAMES.get(key, m.group(1).upper())
    return url.split("/")[-1] or "Canal"


def _js_to_base32(n: float) -> str:
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
        d = min(int(frac), 31)
        frac -= d
        s += digits[d]
        if frac == 0:
            break
    return s


def decode_api_url() -> str:
    encoded = [
        80, 64, 1, 19, 3, 76, 69, 65, 82, 85, 24, 10, 19, 30, 5, 15,
        91, 85, 27, 78, 3, 21, 24, 15, 72, 81, 7, 77, 23, 25, 11, 2,
        21, 88, 28, 21, 21, 91, 11, 30, 72, 26, 2, 12, 2, 29, 15, 28,
        75, 26, 17, 6, 6, 89,
    ]
    b32 = _js_to_base32(math.sqrt(2))
    _k = b32[3:11]
    return "".join(chr(c ^ ord(_k[i % len(_k)])) for i, c in enumerate(encoded))


def _extract_array_block(js: str) -> str | None:
    idx = js.find("EVENTOS_MANUALES")
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
                return js[start: i + 1]
    return None


def parse_js(js: str) -> list[dict]:
    raw = _extract_array_block(js)
    if not raw:
        return []
    pattern = re.compile(
        r"\{\s*time\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*comp\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*home\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*away\s*:\s*['\"]([^'\"]+)['\"]"
        r",\s*channels\s*:\s*\[([^\]]*)\]",
        re.DOTALL,
    )
    partidos = []
    for m in pattern.finditer(raw):
        hora, comp, home, away, chans_raw = m.groups()
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
    return partidos


def fetch_datos() -> list[dict]:
    # 1. Intenta Cloudflare Worker
    try:
        api_url = decode_api_url()
        r = requests.get(
            api_url,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            events = (
                data if isinstance(data, list)
                else data.get("events") or data.get("matches")
                or data.get("data") or data.get("result") or []
            )
            if events:
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
    except Exception:
        pass

    # 2. Fallback: parsea app-pc.js
    try:
        r = requests.get(f"{BASE_URL}/app-pc.js?v=348", headers=HEADERS, timeout=12)
        if r.ok:
            r.encoding = "utf-8"
            return parse_js(r.text)
    except Exception:
        pass

    return []


def handler(event, context):
    try:
        datos = fetch_datos()
        payload = {
            "meta": {
                "fuente":           BASE_URL,
                "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
                "total":            len(datos),
            },
            "datos": datos,
        }
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type":                "application/json",
                "Cache-Control":               "public, max-age=120",  # caché 2 min en CDN
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(payload, ensure_ascii=False),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
