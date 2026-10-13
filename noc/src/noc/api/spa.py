from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

API_PREFIXES = ("api/", "healthz", "readyz", "metrics")


class SinglePageApp(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.startswith(API_PREFIXES) or "." in path:
                raise
            return await super().get_response("index.html", scope)
