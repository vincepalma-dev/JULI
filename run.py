"""
JULI — Quick Start Script.
Launches the FastAPI backend and the Vue dev server, then opens the dashboard
with a fresh session token.

Usage: python run.py [--host 127.0.0.1] [--port 8000] [--no-browser] [--show-link] [--reload]
"""

import argparse
import ipaddress
import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import anthropic  # noqa: F401
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import keyring  # noqa: F401
        import openai  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        print(f"  Missing Python dependency: {e.name}")
        print("  Run: pip install -e .")
        sys.exit(1)

    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("  Node.js not found. Install it from https://nodejs.org")
        sys.exit(1)

    if not (FRONTEND_DIR / "node_modules").exists():
        print("  Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True, shell=True)


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description="Start JULI (backend + dashboard).")
    parser.add_argument("--host", default="127.0.0.1", help="backend bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="backend port (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the dashboard")
    parser.add_argument("--show-link", action="store_true",
                        help="print the dashboard link, which contains the session token")
    parser.add_argument("--reload", action="store_true",
                        help="restart the backend when its code changes (development only)")
    args = parser.parse_args()

    print()
    print("  J.U.L.I.")
    print("  Jolly Universe of Little Intelligences")
    print("  -------------------------------------")  # ASCII: a redirected Windows stdout is cp1252
    print()

    if not is_loopback(args.host):
        print(f"  WARNING: binding to {args.host} exposes JULI to your network.")
        print("  Anyone who gets the session token can run agents on this machine.")
        print()

    check_dependencies()

    token = secrets.token_urlsafe(32)
    env = {**os.environ, "JULI_TOKEN": token}
    dashboard = f"http://localhost:3000/#token={token}"
    processes = []

    try:
        print(f"  Starting backend on http://{args.host}:{args.port}")
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "--factory", "juli.api.app:create_app",
             "--host", args.host, "--port", str(args.port)] + (["--reload"] if args.reload else []),
            cwd=str(ROOT_DIR),
            env=env,
        ))
        time.sleep(2)

        print("  Starting dashboard on http://localhost:3000")
        processes.append(subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            env={**os.environ, "JULI_API_PORT": str(args.port)},
            shell=True,
        ))

        print()
        # The link holds the session token, so it's only printed on request.
        if args.show_link:
            print("  JULI is running. Dashboard link (keep it private, it holds your session token):")
            print(f"  {dashboard}")
        elif args.no_browser:
            print("  JULI is running. Restart with --show-link to print the dashboard link.")
        else:
            print("  JULI is running. The dashboard opens in your browser.")
        print()
        print("  Press Ctrl+C to stop all services")
        print()

        if not args.no_browser:
            threading.Timer(3.0, webbrowser.open, args=(dashboard,)).start()

        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("\n  Shutting down JULI...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait(timeout=5)
        print("  Goodbye!")


if __name__ == "__main__":
    main()
