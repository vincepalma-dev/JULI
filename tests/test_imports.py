import subprocess
import sys


def test_api_loads_without_the_engine():
    """The engine is imported lazily inside the task routes."""
    code = "import sys; import juli.api.app; assert 'juli.engine' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_an_environment_on_an_old_python_is_told_what_to_do():
    """pip refuses a new install below the floor; an environment from before it was raised still starts."""
    code = "import sys; sys.version_info = (3, 10, 11, 'final', 0); import juli"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "JULI needs Python 3.11 or later, and this environment runs Python 3.10." in result.stderr
    assert "Traceback" not in result.stderr


def test_no_autogen_anywhere():
    code = "import juli.api.app, juli.engine, juli.cli, sys; assert 'autogen' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)
