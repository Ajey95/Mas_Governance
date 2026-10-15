"""Server-side Supabase Auth bridge for the private, per-user dashboard."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class AuthError(Exception):
    pass


class SupabaseAuth:
    def __init__(self, project_url: str, publishable_key: str) -> None:
        if not project_url.startswith("https://") or not publishable_key:
            raise ValueError("Supabase Auth requires an HTTPS project URL and publishable key")
        self.base = project_url.rstrip("/") + "/auth/v1"
        self.key = publishable_key

    def _request(self, path: str, *, method: str = "GET", payload: dict | None = None,
                 access_token: str | None = None) -> dict:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                data = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise AuthError("Supabase Auth request failed") from exc
        result = json.loads(data) if data else {}
        if not isinstance(result, dict):
            raise AuthError("Supabase Auth returned an invalid response")
        return result

    def password_login(self, email: str, password: str) -> dict:
        result = self._request("/token?grant_type=password", method="POST",
                               payload={"email": email, "password": password})
        if not result.get("access_token") or not result.get("refresh_token"):
            raise AuthError("Supabase Auth did not return a session")
        return result

    def register(self, email: str, password: str) -> None:
        self._request("/signup", method="POST", payload={"email": email, "password": password})

    def request_recovery(self, email: str, redirect_url: str) -> None:
        if not redirect_url.startswith("https://"):
            raise ValueError("Password recovery requires an HTTPS redirect")
        self._request("/recover?" + urlencode({"redirect_to": redirect_url}),
                      method="POST", payload={"email": email})

    def update_password(self, access_token: str, password: str) -> None:
        self._request("/user", method="PUT", payload={"password": password},
                      access_token=access_token)

    def refresh(self, refresh_token: str) -> dict:
        result = self._request("/token?grant_type=refresh_token", method="POST",
                               payload={"refresh_token": refresh_token})
        if not result.get("access_token") or not result.get("refresh_token"):
            raise AuthError("Supabase Auth did not refresh the session")
        return result

    def user(self, access_token: str) -> dict:
        result = self._request("/user", access_token=access_token)
        if (not isinstance(result.get("id"), str) or not result["id"]
                or result.get("is_anonymous") is True or not result.get("email")):
            raise AuthError("Supabase Auth returned no user ID")
        return result

    def logout(self, access_token: str) -> None:
        self._request("/logout", method="POST", access_token=access_token)
