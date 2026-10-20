from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Request

from app.api.exc.exceptions import service_unavailable, unexpected_error
from app.settings import graph_settings


@dataclass
class DgraphClient:
    """DQL over Dgraph's HTTP endpoint."""

    http: httpx.AsyncClient

    async def query(self, dql: str, **variables: Any) -> dict[str, Any]:
        """Runs a read-only DQL query; variables are bound, never inlined."""
        try:
            response = await self.http.post(
                "/query",
                json={
                    "query": dql,
                    "variables": {
                        f"${k}": str(v) for k, v in variables.items()
                    },
                },
            )
        except httpx.TransportError as error:
            raise service_unavailable(error) from error
        body = response.json()
        if body.get("errors"):
            raise unexpected_error(body["errors"][0]["message"])
        return body["data"]

    async def health(self) -> list[dict[str, Any]]:
        try:
            response = await self.http.get("/health")
        except httpx.TransportError as error:
            raise service_unavailable(error) from error
        return response.json()


@asynccontextmanager
async def create_graph_adapter(app: FastAPI) -> AsyncGenerator[None]:
    async with httpx.AsyncClient(
        base_url=graph_settings.DGRAPH_URL,
        timeout=graph_settings.DGRAPH_TIMEOUT,
    ) as http:
        app.state.graph = DgraphClient(http)
        yield


def get_graph(request: Request) -> DgraphClient:
    return request.app.state.graph


GraphContext = Annotated[DgraphClient, Depends(get_graph)]
