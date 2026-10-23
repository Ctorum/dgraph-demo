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
        body = await self._post(
            "/query",
            json={
                "query": dql,
                "variables": {f"${k}": str(v) for k, v in variables.items()},
            },
        )
        return body["data"]

    async def _post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.http.post(path, **kwargs)
        except httpx.TransportError as error:
            raise service_unavailable(error) from error
        body = response.json()
        if body.get("errors"):
            raise unexpected_error(body["errors"][0]["message"])
        return body

    async def mutate(self, *mutations: dict[str, Any]) -> dict[str, str]:
        """Applies JSON mutations in order, in one transaction.

        Dgraph applies a request's ``delete`` after its ``set``, so replacing
        a value takes two requests; they share the transaction and commit
        together. Returns the uids assigned to blank nodes.
        """
        uids: dict[str, str] = {}
        keys: list[str] = []
        preds: list[str] = []
        start_ts: int | None = None
        for mutation in mutations:
            body = await self._post(
                "/mutate",
                params={"startTs": start_ts} if start_ts else None,
                json=mutation,
            )
            txn = body["extensions"]["txn"]
            start_ts = txn["start_ts"]
            keys += txn.get("keys", [])
            preds += txn.get("preds", [])
            uids |= body["data"].get("uids", {})
        if start_ts:
            await self._post(
                "/commit",
                params={"startTs": start_ts},
                json={"keys": keys, "preds": preds},
            )
        return uids

    async def alter(self, operation: str | dict[str, Any]) -> None:
        """Schema DDL (a string) or a drop operation (a dict)."""
        if isinstance(operation, str):
            await self._post("/alter", content=operation.encode())
        else:
            await self._post("/alter", json=operation)

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
