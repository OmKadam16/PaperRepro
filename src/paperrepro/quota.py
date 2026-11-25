"""Strict daily limit on AI actions: 15 per user per day (UTC), enforced on the server.

A "user" is counted twice over: by a signed browser cookie AND by network address. An action
is refused if either has used up the day, so clearing cookies does not reset the count.
Each user action costs 1, however many model calls it makes inside (a gap search, a citation
run, a review). Usage is saved to disk, so restarting the server does not reset it either.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets as pysecrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DAILY_LIMIT = 15


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def resets_at() -> str:
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc).isoformat()


class Quota:
    def __init__(self, root: Path, limit: int = DAILY_LIMIT):
        self.path, self.limit = root / "usage.json", limit
        self.lock = threading.Lock()
        self.key = self._server_key(root)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                self.data = {}

    @staticmethod
    def _server_key(root: Path) -> bytes:
        """Signing key for user cookies; kept next to the data, owner-only, never sent anywhere."""
        f = root / ".cookie_key"
        if not f.exists():
            f.write_bytes(pysecrets.token_bytes(32))
            f.chmod(0o600)
        return f.read_bytes()

    # ---------------------------------------------------------------- user cookie
    def new_user(self) -> str:
        uid = pysecrets.token_hex(12)
        return f"{uid}.{self._sign(uid)}"

    def _sign(self, uid: str) -> str:
        return hmac.new(self.key, uid.encode(), hashlib.sha256).hexdigest()[:24]

    def verify(self, cookie: str) -> str | None:
        uid, _, sig = (cookie or "").partition(".")
        return uid if uid and hmac.compare_digest(sig, self._sign(uid)) else None

    # ---------------------------------------------------------------- counting
    def _day(self) -> dict:
        d = today()
        if self.data.get("day") != d:
            self.data = {"day": d, "used": {}}
        return self.data["used"]

    def used(self, uid: str | None, ip: str) -> int:
        with self.lock:
            used = self._day()
            return max(used.get(f"u:{uid}", 0) if uid else 0, used.get(f"ip:{ip}", 0))

    def take(self, uid: str | None, ip: str) -> bool:
        """Spend one action. False (and nothing spent) if the user is out for today."""
        with self.lock:
            used = self._day()
            keys = [f"ip:{ip}"] + ([f"u:{uid}"] if uid else [])
            if any(used.get(k, 0) >= self.limit for k in keys):
                return False
            for k in keys:
                used[k] = used.get(k, 0) + 1
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data))
            tmp.replace(self.path)
            return True

    def refund(self, uid: str | None, ip: str) -> None:
        """Give an action back when it never reached a model (e.g. both providers were down)."""
        with self.lock:
            used = self._day()
            for k in [f"ip:{ip}"] + ([f"u:{uid}"] if uid else []):
                if used.get(k, 0) > 0:
                    used[k] -= 1
            self.path.write_text(json.dumps(self.data))

    def status(self, uid: str | None, ip: str) -> dict:
        n = self.used(uid, ip)
        return {"used": n, "limit": self.limit, "left": max(0, self.limit - n), "resets_at": resets_at(),
                "now": time.time()}
