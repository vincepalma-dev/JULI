"""Start JULI for the end-to-end tests: the built dashboard and the API on
127.0.0.1:<port>, with the token from $JULI_TOKEN and data in $JULI_DATA_DIR.

Unlike `juli serve`, it never touches a developer's own setup: not the
repository's legacy settings.json, not the .env file, and not the OS
keychain. Keys live in memory for this process only, so a test that saves
or deletes keys (such as "delete all data") can't reach the real ones.
"""

import os
import sys

import keyring
import uvicorn
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from juli import cli, config, keystore
from juli.api.app import create_app


class MemoryKeyring(KeyringBackend):
    """A keychain that forgets everything when the test server stops."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.store.pop((service, username), None) is None:
            raise PasswordDeleteError("not found")


keyring.set_keyring(MemoryKeyring())  # before anything reads or writes a key

port = int(sys.argv[1])
data = config.data_dir()
config.LEGACY_SETTINGS_FILE = data / "no-legacy-settings.json"
keystore.ENV_FILE = data / "no-env"
for var in [v for v in os.environ if v.upper().endswith("_API_KEY")]:
    del os.environ[var]  # keys from the shell stay out too
os.environ["JULI_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{port},http://localhost:{port}"
app = create_app(os.environ["JULI_TOKEN"], static_dir=cli.FRONTEND_DIR / "dist", port=port)
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
