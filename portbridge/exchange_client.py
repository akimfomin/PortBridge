"""Connect to an explicitly configured loopback exchange."""

from http.client import HTTPConnection, HTTPException
import json
from urllib.parse import urlencode

from .discussion import MAX_WAIT_SECONDS
from .exchange_fields import TOKEN


class ExchangeClientError(OSError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Local exchange returned HTTP {status}")


class ExchangeClient:
    def __init__(self, port, token):
        if not 1 <= port <= 65535:
            raise ValueError("Use a loopback exchange port between 1 and 65535")
        if not TOKEN.fullmatch(token or ""):
            raise ValueError("Set PORTBRIDGE_EXCHANGE_TOKEN to a read-enabled exchange key")
        self.port = port
        self.token = token

    def preflight(self, **options):
        return self.request("preflight", query={key: value for key, value in options.items() if value})

    def request(self, route, *, query=None, body=None):
        if not route.isascii() or not route.replace("-", "").isalpha():
            raise ValueError("invalid exchange route")
        url = f"/api/v1/exchange/{route}"
        if query:
            url += f"?{urlencode(query)}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        timeout = MAX_WAIT_SECONDS + 6 if route == "updates" else 6
        connection = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            connection.request("GET" if data is None else "POST", url, body=data, headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                raise ExchangeClientError(response.status)
            limit = 1024 * 1024
            body = response.read(limit + 1)
            if len(body) > limit:
                raise OSError("Local exchange response exceeded the size limit")
            return json.loads(body)
        except HTTPException as exc:
            raise OSError("Local exchange returned an incomplete HTTP response") from exc
        finally:
            connection.close()
