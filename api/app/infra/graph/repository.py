import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.api.exc.exceptions import unauthorized_error
from app.settings import graph_settings

from .adapter import DgraphClient
from .schemas import UndoSchema, WriteSchema

HEADER = re.compile(r"^\s*query\s+\w+\s*\(([^)]*)\)\s*")
UID = re.compile(r"0x[0-9a-f]+")


def inline(dql: str, **variables: Any) -> str:
    """The query with its variables written in, ready to paste in Ratel."""
    header = HEADER.match(dql)
    if not header:
        return dql
    types = dict(re.findall(r"\$(\w+)\s*:\s*(\w+)", header.group(1)))
    body = dql[header.end() :]
    for name, value in variables.items():
        literal = str(value)
        if types.get(name) == "string" and not UID.fullmatch(literal):
            literal = json.dumps(literal, ensure_ascii=False)
        body = re.sub(rf"\${name}\b", literal, body)
    return body


def type_ddl(name: str, fields: list[str]) -> str:
    """``type`` declaration; Dgraph wants one field per line."""
    body = "".join(f"\n  {f}" for f in fields)
    return f"type {name} {{{body}\n}}"


@dataclass
class GraphRepository:
    """Base repository over Dgraph.

    Predicates are namespaced per demo (``fraude.Cliente.nome``), so each
    repository sets ``namespace``. Every query run through ``query`` is kept
    in ``queries`` so the API can show the client exactly what was executed, with the
    variables inlined so it runs as-is in Ratel.
    """

    context: DgraphClient
    namespace: str = ""
    queries: list[str] = field(default_factory=list)
    # Writes in execution order: JSON mutations and schema DDL. With
    # ``dry_run`` they are only recorded, so the client previews them.
    mutations: list[str] = field(default_factory=list)
    dry_run: bool = False

    def _writable(self) -> bool:
        if self.dry_run:
            return False
        if not graph_settings.WRITE_ENABLED:
            raise unauthorized_error(
                "Escrita desabilitada (WRITE_ENABLED=false)"
            )
        return True

    async def mutate(self, *mutations: dict[str, Any]) -> dict[str, str]:
        """Records and applies mutations in one transaction."""
        self.mutations += [
            json.dumps(m, ensure_ascii=False, indent=2) for m in mutations
        ]
        return await self.context.mutate(*mutations) if self._writable() else {}

    async def alter(self, operation: str | dict[str, Any]) -> None:
        self.mutations.append(
            operation
            if isinstance(operation, str)
            else json.dumps(operation, ensure_ascii=False, indent=2)
        )
        if self._writable():
            await self.context.alter(operation)

    def written(
        self,
        node: str | None = None,
        key: int | None = None,
        impacto: dict[str, int] | None = None,
        desfazer: UndoSchema | None = None,
    ) -> WriteSchema:
        return WriteSchema(
            applied=not self.dry_run,
            mutations=self.mutations,
            queries=self.queries,
            node=node,
            key=key,
            impacto=impacto or {},
            desfazer=desfazer,
        )

    async def query(self, dql: str, **variables: Any) -> dict[str, Any]:
        self.queries.append(inline(dql, **variables))
        return await self.context.query(dql, **variables)

    async def get_vertex(self, vertex: str, id_: int) -> dict[str, Any] | None:
        """Scalar properties of ``<namespace>.<vertex>`` by its ``id``."""
        type_ = f"{self.namespace}.{vertex}"
        data = await self.context.query(
            f"query q($id: int) {{ v(func: eq({type_}.id, $id)) "
            f"@filter(type({type_})) {{ uid expand(_all_) }} }}",
            id=id_,
        )
        if not data["v"]:
            return None
        prefix = f"{type_}."
        vertex_ = data["v"][0]
        return {"uid": vertex_["uid"]} | {
            key.removeprefix(prefix): value
            for key, value in vertex_.items()
            if key.startswith(prefix)
        }
