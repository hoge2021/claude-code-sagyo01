"""Tribal v2 ast_extract test fixture: Python."""
import os
import json as _json
from pathlib import Path


class UserService:
    def get_user(self, uid: str) -> dict:
        return {"id": uid, "loaded_from": str(self._db_path())}

    def _db_path(self) -> Path:
        return Path(os.environ.get("DB", "/tmp/db.json"))


def main() -> None:
    svc = UserService()
    data = svc.get_user("alice")
    print(_json.dumps(data))
