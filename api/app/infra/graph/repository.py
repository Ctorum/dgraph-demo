from dataclasses import dataclass, field
from typing import Any

from .adapter import DgraphClient


@dataclass
class GraphRepository:
    """Base repository over Dgraph.

    Predicates are namespaced per demo (``fraude.Cliente.nome``), so each
    repository sets ``namespace``. Every query run through ``query`` is kept
    in ``queries`` so the API can show the client exactly what was executed.
    """

    context: DgraphClient
    namespace: str = ""
    queries: list[str] = field(default_factory=list)

    async def query(self, dql: str, **variables: Any) -> dict[str, Any]:
        self.queries.append(dql)
        return await self.context.query(dql, **variables)

    async def get_vertex(self, vertex: str, id_: int) -> dict[str, Any] | None:
        """Scalar properties of ``<namespace>.<vertex>`` by its ``id``."""
        type_ = f"{self.namespace}.{vertex}"
        data = await self.context.query(
            f"query q($id: int) {{ v(func: eq({type_}.id, $id)) "
            f"@filter(type({type_})) {{ expand(_all_) }} }}",
            id=id_,
        )
        if not data["v"]:
            return None
        prefix = f"{type_}."
        return {
            key.removeprefix(prefix): value
            for key, value in data["v"][0].items()
            if key.startswith(prefix)
        }
