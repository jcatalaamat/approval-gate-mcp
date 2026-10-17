"""Propose/confirm gate for irreversible operations.

First call: nothing runs. The caller gets a preview and a one-time token.
Second call: the token must come back, and the action that runs is the one that
was *proposed*, not whatever params arrive with the token. A token is bound to
the tenant and operation that minted it, is single use, and expires.
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from .errors import GateError

TTL_SECONDS = 600


def digest(tenant: str, operation: str, params: dict) -> str:
    blob = json.dumps({"t": tenant, "o": operation, "p": params}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass(frozen=True)
class Pending:
    tenant: str
    operation: str
    params: dict
    created: float


class ApprovalGate:
    def __init__(self, ttl: int = TTL_SECONDS, clock: Callable[[], float] = time.time):
        self._ttl = ttl
        self._clock = clock
        self._pending: dict[str, Pending] = {}

    def propose(self, tenant: str, operation: str, params: dict) -> dict:
        self._sweep()
        token = secrets.token_urlsafe(16)
        self._pending[token] = Pending(tenant, operation, dict(params), self._clock())
        return {
            "pending": True,
            "operation": operation,
            "params": params,
            "confirm_token": token,
            "expires_in_seconds": self._ttl,
            "note": (
                "NOT executed. To run exactly this action, call execute again with the same operation and "
                "only {\"confirm_token\": \"<token>\"} after the user has approved these exact params."
            ),
        }

    def confirm(self, tenant: str, operation: str, token: str) -> dict:
        """Return the originally proposed params and consume the token."""
        pending = self._pending.get(token)
        if pending is None:
            raise GateError("invalid or expired confirm_token; call again without it for a fresh preview")
        if self._clock() - pending.created > self._ttl:
            del self._pending[token]
            raise GateError("confirm_token expired; call again without it for a fresh preview")
        if pending.tenant != tenant or pending.operation != operation:
            # not consumed: a wrong-context attempt must not burn the real caller's token
            raise GateError("confirm_token does not belong to this tenant and operation")
        del self._pending[token]
        return dict(pending.params)

    def _sweep(self) -> None:
        now = self._clock()
        for token in [t for t, p in self._pending.items() if now - p.created > self._ttl]:
            del self._pending[token]
