"""Minimal async client for the Firewalla MSP API v2.

Reference: https://docs.firewalla.net/
Auth: "Authorization: Token <personal access token>"
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20


class FirewallaApiError(Exception):
    """Generic API failure."""


class FirewallaAuthError(FirewallaApiError):
    """Token rejected (401/403)."""


def normalize_domain(value: str) -> str:
    """Accept 'https://name.firewalla.net/' or 'name' and return 'name.firewalla.net'."""
    value = value.strip()
    for prefix in ("https://", "http://"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0]
    if "." not in value:
        value = f"{value}.firewalla.net"
    return value.lower()


def _as_list(payload: Any) -> list[dict[str, Any]]:
    """Endpoints return either a bare array or {count, results}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


class FirewallaMspClient:
    """Thin wrapper around the endpoints this integration uses."""

    def __init__(self, session: aiohttp.ClientSession, msp_domain: str, token: str) -> None:
        self._session = session
        self.host = normalize_domain(msp_domain)
        self._base = f"https://{self.host}/v2"
        self._headers = {"Authorization": f"Token {token.strip()}"}

    async def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._base}{path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, headers=self._headers, params=params
                ) as resp:
                    if resp.status in (401, 403):
                        raise FirewallaAuthError(f"Token rejected ({resp.status})")
                    if resp.status >= 400:
                        text = await resp.text()
                        raise FirewallaApiError(
                            f"{method} {path} failed: {resp.status} {text[:200]}"
                        )
                    if resp.content_type == "application/json":
                        return await resp.json()
                    text = await resp.text()
                    return text or None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FirewallaApiError(f"{method} {path} failed: {err}") from err

    async def get_boxes(self) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", "/boxes"))

    async def get_devices(self) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", "/devices"))

    async def get_rules(self) -> list[dict[str, Any]]:
        """Requires MSP 2.7.0 or later."""
        return _as_list(await self._request("GET", "/rules"))

    async def get_alarms(self, limit: int) -> list[dict[str, Any]]:
        """Newest alarms first (API default sort is ts:desc)."""
        return _as_list(
            await self._request(
                "GET", "/alarms", params={"sortBy": "ts:desc", "limit": str(limit)}
            )
        )

    async def pause_rule(self, rule_id: str) -> None:
        await self._request("POST", f"/rules/{rule_id}/pause")

    async def resume_rule(self, rule_id: str) -> None:
        await self._request("POST", f"/rules/{rule_id}/resume")
