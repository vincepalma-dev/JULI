"""Start JULI for the end-to-end tests: the built dashboard and the API on
127.0.0.1:<port>, with the token from $JULI_TOKEN and data in $JULI_DATA_DIR.

Unlike `juli serve`, it never reads the repository's legacy settings.json,
so a developer's own crew and keys stay out of the tests.
"""

import os
import sys

import uvicorn

from juli import cli, config
from juli.api.app import create_app

port = int(sys.argv[1])
data = config.data_dir()
config.LEGACY_SETTINGS_FILE = data / "no-legacy-settings.json"
os.environ["JULI_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{port},http://localhost:{port}"
app = create_app(os.environ["JULI_TOKEN"], static_dir=cli.FRONTEND_DIR / "dist", port=port)
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
