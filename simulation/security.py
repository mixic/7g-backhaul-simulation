# 7g-backhaul-simulation
# Copyright (C) 2026 MILAN NIKOLIC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


class AuthenticationError(ValueError):
    """Raised when a simulated session credential cannot be trusted."""


@dataclass(frozen=True)
class SessionCredential:
    principal: str
    session_id: str
    expires_at: int
    nonce: str
    signature: str


class SessionAuthenticator:
    """Issue and verify short-lived HMAC session credentials for simulation use."""

    def __init__(self, secret_key: bytes) -> None:
        if len(secret_key) < 32:
            raise ValueError("HMAC secret must contain at least 32 bytes.")
        self._secret_key = bytes(secret_key)

    @staticmethod
    def _message(principal: str, session_id: str, expires_at: int, nonce: str) -> bytes:
        fields = (principal, session_id, str(expires_at), nonce)
        if any(not field or "\n" in field for field in fields):
            raise ValueError("Credential fields must be non-empty and cannot contain newlines.")
        return "\n".join(fields).encode("utf-8")

    def issue(
        self,
        principal: str,
        session_id: str,
        now: int,
        lifetime_seconds: int = 300,
    ) -> SessionCredential:
        if now < 0 or lifetime_seconds <= 0:
            raise ValueError("Current time must be non-negative and lifetime must be positive.")
        expires_at = now + lifetime_seconds
        nonce = secrets.token_hex(16)
        signature = hmac.new(
            self._secret_key,
            self._message(principal, session_id, expires_at, nonce),
            hashlib.sha256,
        ).hexdigest()
        return SessionCredential(principal, session_id, expires_at, nonce, signature)

    def verify(self, credential: SessionCredential, session_id: str, now: int) -> str:
        if credential.session_id != session_id:
            raise AuthenticationError("Credential is not valid for this session.")
        if now < 0 or now >= credential.expires_at:
            raise AuthenticationError("Credential has expired or the verification time is invalid.")
        expected = hmac.new(
            self._secret_key,
            self._message(
                credential.principal,
                credential.session_id,
                credential.expires_at,
                credential.nonce,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, credential.signature):
            raise AuthenticationError("Credential signature is invalid.")
        return credential.principal
