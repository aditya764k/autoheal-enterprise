#!/usr/bin/env python3
"""
inject_http500.py — Simulate HTTP 500 Internal Server Error
============================================================
Hits the /crash endpoint on the Flask app, causing it to log a 500
traceback which the monitor will pick up via the "500" keyword pattern.

The /crash route was added to test_environment/app/app.py specifically
for this injector.

Usage:
    python inject_http500.py                            # default: localhost:5000
    python inject_http500.py --host 127.0.0.1 --port 5000
    python inject_http500.py --repeat 3
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
import urllib.error


def inject(host: str, port: int, repeat: int) -> None:
    url = f"http://{host}:{port}/crash"
    print(f"[inject_http500] 🎯 Target URL: {url}", file=sys.stderr)

    for i in range(repeat):
        try:
            urllib.request.urlopen(url, timeout=5)
            # Should not reach here — /crash always raises
            print(f"[inject_http500] ⚠️  [{i+1}/{repeat}] Expected 500 but got 200.", file=sys.stderr)
        except urllib.error.HTTPError as e:
            if e.code == 500:
                print(f"[inject_http500] ✅ [{i+1}/{repeat}] Got HTTP 500 — Flask traceback injected into container logs.", file=sys.stderr)
            else:
                print(f"[inject_http500] ⚠️  [{i+1}/{repeat}] Unexpected HTTP {e.code}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[inject_http500] ❌ [{i+1}/{repeat}] Request failed: {e}", file=sys.stderr)
        time.sleep(0.2)

    print(f"[inject_http500] 🏁 Done — triggered {repeat} 500 response(s).", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger HTTP 500 responses from the Flask test app.")
    parser.add_argument("--host", default="127.0.0.1", help="Flask host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Flask port (default: 5000)")
    parser.add_argument("--repeat", type=int, default=1, help="Number of requests")
    args = parser.parse_args()
    inject(args.host, args.port, args.repeat)


if __name__ == "__main__":
    main()
