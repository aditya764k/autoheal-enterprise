from flask import Flask, jsonify
import logging
import os
import sys

app = Flask(__name__)

# ── Production routes ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "AutoHeal Test App"})

@app.route("/health")
def health():
    return jsonify({"health": "alive"})

@app.route("/db-check")
def db_check():
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
        conn.close()
        return jsonify({"db": "connected"})
    except Exception as e:
        return jsonify({"db": "error", "detail": str(e)}), 500

# ── Test / injection routes (OBSERVE layer simulation) ────────────────────

@app.route("/crash")
def crash():
    """Deliberately raises an unhandled exception.
    Flask catches it and logs a 500 Internal Server Error traceback —
    used by inject_http500.py to produce HTTP 500 log lines."""
    raise RuntimeError("Simulated crash: inject_http500 triggered this route")

@app.route("/error-log")
def error_log():
    """Writes ERROR and FATAL lines to stderr without crashing the app —
    used by inject_error.py to exercise keyword detection."""
    app.logger.error("ERROR: Simulated application error from /error-log")
    sys.stderr.write("FATAL: Simulated fatal condition from /error-log\n")
    sys.stderr.flush()
    return jsonify({"injected": True, "keywords": ["ERROR", "FATAL"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)