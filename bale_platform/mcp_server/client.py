"""Thin HTTP client for the adapter API. Responses are returned unchanged."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("bale.mcp")


class AdapterApiError(Exception):
    """The adapter API returned an error, or could not be reached.

    The message is safe to show to an MCP client: it includes the API error
    code and the status, and it never includes the bearer token.
    """

    def __init__(
        self,
        status_code: int,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retry_after = retry_after
        super().__init__(self._format())

    def _format(self) -> str:
        text = f"{self.code}: {self.message} (HTTP {self.status_code})"
        if self.retry_after:
            text += f"; retry_after={self.retry_after}"
        if self.details:
            text += f"; details={json.dumps(self.details, ensure_ascii=False, sort_keys=True)}"
        return text

    @classmethod
    def from_response(cls, response: httpx.Response) -> "AdapterApiError":
        code = "http_error"
        message = f"adapter API returned HTTP {response.status_code}"
        details: dict[str, Any] = {}
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                code = str(err.get("code") or code)
                message = str(err.get("message") or message)
                raw_details = err.get("details")
                if isinstance(raw_details, dict):
                    details = raw_details
        retry = response.headers.get("Retry-After")
        return cls(
            response.status_code,
            code=code,
            message=message,
            details=details,
            retry_after=retry,
        )


class AdapterApiClient:
    """Sync client. One instance is shared by the MCP tools in this process."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "bale-adapter-mcp",
            },
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._http.close()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json=body)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("adapter API %s %s unreachable (%s)", method, path, type(exc).__name__)
            raise AdapterApiError(
                0,
                code="unreachable",
                message=f"adapter API unreachable ({type(exc).__name__})",
            ) from exc
        if response.status_code >= 400 or response.is_redirect:
            err = AdapterApiError.from_response(response)
            logger.warning(
                "adapter API %s %s failed status=%s code=%s",
                method,
                path,
                response.status_code,
                err.code,
            )
            raise err
        try:
            payload = response.json()
        except ValueError as exc:
            raise AdapterApiError(
                response.status_code,
                code="invalid_response",
                message="adapter API returned a non-JSON body",
            ) from exc
        if not isinstance(payload, dict):
            raise AdapterApiError(
                response.status_code,
                code="invalid_response",
                message="adapter API returned JSON that is not an object",
            )
        return payload
