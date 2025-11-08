from __future__ import annotations

import json
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.utils.logging import mask_pii

BANNED_TOPICS = {"weapon", "explosive", "fraud"}
POLICY_REDIRECT = {
    "medical": "Please consult medical professionals; I can share general policy only.",
    "legal": "For legal topics, refer to your contract terms or counsel.",
}


class GuardrailMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable):
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw_body = (await request.body()).decode("utf-8")
        lowered = raw_body.lower()
        if any(token in lowered for token in BANNED_TOPICS):
            return JSONResponse(status_code=403, content={"detail": "Request blocked by policy"})
        for keyword, message in POLICY_REDIRECT.items():
            if keyword in lowered:
                return JSONResponse(status_code=400, content={"detail": message})
        request.state.masked_body = mask_pii(raw_body)
        response = await call_next(request)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            payload = json.loads(body.decode() or "{}")
            if isinstance(payload, dict) and payload.get("quote"):
                total_high = payload["quote"].get("total_high", 0)
                if total_high > self.settings.max_quote_cap:
                    payload["quote"]["total_high"] = self.settings.max_quote_cap
                    payload["quote"]["flag"] = "cap_enforced"
                body = json.dumps(payload).encode()
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers), media_type=response.media_type)
