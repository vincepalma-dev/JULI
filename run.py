"""
JULI — Quick Start Script.
Launches both the FastAPI backend and Vue frontend dev server.
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR
FRONTEND_DIR = ROOT_DIR / "frontend"


def check_dependencies():
    """Check if required dependencies are installed."""
    # Check Python packages
    try:
        import fastapi
        import uvicorn
        import autogen
    except ImportError as e:
        print(f"❌ Missing Python dependency: {e.name}")
        print(f"   Run: pip install -r requirements.txt")
        sys.exit(1)

    # Check Node
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Node.js not found. Install from https://nodejs.org")
        sys.exit(1)

    # Check if frontend dependencies are installed
    if not (FRONTEND_DIR / "node_modules").exists():
        print("📦 Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True, shell=True)


def main():
    """Start both backend and frontend."""
    print()
    print("  🤖 J.U.L.I.")
    print("  Jolly Universe of Little Intelligences")
    print("  ─────────────────────────────────────")
    print()

    check_dependencies()

    processes = []

    try:
        # Start FastAPI backend
        print("  🔧 Starting backend on http://localhost:8000")
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app",
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            cwd=str(BACKEND_DIR),
        )
        processes.append(backend)
        time.sleep(2)

        # Start Vue frontend
        print("  🎨 Starting frontend on http://localhost:3000")
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
            shell=True,
        )
        processes.append(frontend)

        print()
        print("  ✅ JULI is running!")
        print("  ─────────────────────────────────────")
        print("  Dashboard : http://localhost:3000")
        print("  API       : http://localhost:8000")
        print("  API Docs  : http://localhost:8000/docs")
        print()
        print("  Press Ctrl+C to stop all services")
        print()

        # Wait for processes
        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("\n  🛑 Shutting down JULI...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait(timeout=5)
        print("  👋 Goodbye!")


if __name__ == "__main__":
    main()
