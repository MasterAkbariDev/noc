from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

API_PREFIXES = ("api/", "healthz", "readyz", "metrics")
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
ASSETS_DIRECTORY = "assets"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


class SinglePageApp(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.startswith(API_PREFIXES) or "." in path:
                raise
            response = await super().get_response("index.html", scope)
        return harden(response)


def harden(response: Response) -> Response:
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if isinstance(response, FileResponse):
        file_path = Path(response.path)
        if file_path.name == "index.html":
            response.headers["Cache-Control"] = "no-cache"
        elif file_path.parent.name == ASSETS_DIRECTORY:
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
    return response
