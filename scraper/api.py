"""
api.py — Servidor Flask local
Sirve los datos extraídos al frontend en http://localhost:5000/api/datos
"""

import json
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, abort
from flask_cors import CORS

DATA_FILE    = Path(__file__).parent.parent / "data" / "iacip_datos.json"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = Flask(__name__, static_folder=None)  # evita ruta /frontend/* automática

# fix #4: CORS restringido solo al origen local
CORS(app, origins=["http://localhost:5000", "http://127.0.0.1:5000"])


@app.get("/api/datos")
def datos():
    if not DATA_FILE.exists():
        return jsonify({"error": "Ejecuta el scraper primero."}), 404
    # fix #6: captura race condition si el archivo está siendo escrito
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return jsonify({"error": "Datos temporalmente no disponibles."}), 503
    return jsonify(payload)


@app.get("/api/status")
def status():
    # fix #5: no exponer ruta absoluta del sistema de archivos
    return jsonify({
        "scraper": "ok",
        "datos_disponibles": DATA_FILE.exists(),
    })


# fix #2: bloquea path traversal antes de servir archivos estáticos
@app.get("/")
@app.get("/<path:filename>")
def frontend(filename="index.html"):
    safe = os.path.normpath(filename)
    if safe.startswith("..") or os.path.isabs(safe):
        abort(404)
    return send_from_directory(FRONTEND_DIR, safe)


if __name__ == "__main__":
    print("Servidor iniciado en http://localhost:5000")
    # fix #5: debug=False para no exponer tracebacks al cliente
    app.run(debug=False, port=5000)
