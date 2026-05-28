"""
Decodifica la apiUrl ofuscada en app-pc.js
Lógica JS:
  _k = Math.SQRT2.toString(32).slice(3,11)
  $_(a) = a.map((c,i) => String.fromCharCode(c ^ _k.charCodeAt(i % _k.length))).join('')
"""
import sys
import math
import requests

sys.stdout.reconfigure(encoding="utf-8")

def js_number_to_base(n, radix):
    """Convierte un float al string base-radix como lo hace JavaScript."""
    DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    sign = ""
    if n < 0:
        sign = "-"
        n = -n
    int_part = int(n)
    frac_part = n - int_part
    # Parte entera
    if int_part == 0:
        int_str = "0"
    else:
        digits = []
        tmp = int_part
        while tmp > 0:
            digits.append(DIGITS[tmp % radix])
            tmp //= radix
        int_str = "".join(reversed(digits))
    # Parte fraccionaria (max 52 iteraciones como JS)
    frac_str = ""
    seen = {}
    for _ in range(52):
        frac_part *= radix
        digit = int(frac_part)
        frac_part -= digit
        frac_str += DIGITS[digit]
        if frac_part == 0:
            break
    result = int_str
    if frac_str:
        result += "." + frac_str
    return sign + result

# Calcula _k
sqrt2_b32 = js_number_to_base(math.sqrt(2), 32)
print(f"sqrt2 base32: {sqrt2_b32}")
_k = sqrt2_b32[3:11]
print(f"_k (slice 3-11): {_k!r}  len={len(_k)}")

# Array ofuscado de la apiUrl
encoded = [80,64,1,19,3,76,69,65,82,85,24,10,19,30,5,15,91,85,27,78,
           3,21,24,15,72,81,7,77,23,25,11,2,21,88,28,21,21,91,11,30,
           72,26,2,12,2,29,15,28,75,26,17,6,6,89]

api_url = "".join(chr(c ^ ord(_k[i % len(_k)])) for i, c in enumerate(encoded))
print(f"\napiUrl decodificada: {api_url}")

# Prueba la URL
print("\n=== Probando la API ===")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mundofutbolcol.online/",
    "Accept": "application/json",
}
try:
    r = requests.get(api_url, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type','')}")
    print(f"Tamaño: {len(r.text)} chars")
    print()
    print(r.text[:3000])
except Exception as e:
    print(f"Error: {e}")
