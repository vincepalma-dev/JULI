import subprocess
import sys


def test_api_loads_without_the_engine():
    """The engine is imported lazily inside the task routes."""
    code = "import sys; import juli.api.app; assert 'juli.engine' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_no_autogen_anywhere():
    code = "import juli.api.app, juli.engine, juli.cli, sys; assert 'autogen' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)
