import subprocess
import sys


def test_api_loads_without_the_agent_engine():
    """The orchestrator (and pyautogen) are imported lazily inside the task route."""
    code = (
        "import sys; import juli.api.app; "
        "assert 'agents.orchestrator' not in sys.modules; assert 'autogen' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
