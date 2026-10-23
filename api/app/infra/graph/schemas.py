from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

type Role = Literal["focus", "result", "path"]


class NodeSchema(BaseModel):
    id: str = Field(
        description="Chave única no grafo", examples=["Cliente:281"]
    )
    type: str = Field(description="Classe do vértice", examples=["Cliente"])
    key: int = Field(description="Propriedade `id` do vértice", examples=[281])
    label: str = Field(examples=["Cliente 281"])
    role: Role = Field(
        "path",
        description="focus: de onde a consulta partiu; result: o que ela "
        "encontrou; path: vértices intermediários do caminho",
    )
    props: dict[str, Any] = Field(default_factory=dict)


class EdgeSchema(BaseModel):
    id: str
    source: str
    target: str
    label: str = Field(description="Classe ou tipo da aresta")
    props: dict[str, Any] = Field(default_factory=dict)


class GraphSchema[T](BaseModel):
    """Resultado de uma consulta: o subgrafo percorrido e a lista tabular."""

    queries: list[str] = Field(description="Consultas DQL executadas")
    nodes: list[NodeSchema]
    edges: list[EdgeSchema]
    items: list[T]


_RANK = {"path": 0, "result": 1, "focus": 2}


def node_id(type_: str, key: int) -> str:
    return f"{type_}:{key}"


@dataclass
class GraphBuilder:
    """Acumula nós e arestas sem duplicar."""

    nodes: dict[str, NodeSchema] = field(default_factory=dict)
    edges: dict[str, EdgeSchema] = field(default_factory=dict)

    def node(
        self,
        type_: str,
        key: int,
        label: str,
        role: Role = "path",
        **props: Any,
    ) -> str:
        """Adds a vertex; a stronger role (focus > result > path) wins."""
        id_ = node_id(type_, key)
        current = self.nodes.get(id_)
        if current is None or _RANK[role] > _RANK[current.role]:
            self.nodes[id_] = NodeSchema(
                id=id_, type=type_, key=key, label=label, role=role, props=props
            )
        return id_

    def edge(self, source: str, target: str, label: str, **props: Any) -> None:
        id_ = f"{source}-{label}-{target}"
        self.edges.setdefault(
            id_,
            EdgeSchema(
                id=id_, source=source, target=target, label=label, props=props
            ),
        )

    def build[T](self, queries: list[str], items: list[T]) -> GraphSchema[T]:
        return GraphSchema[T](
            queries=queries,
            nodes=list(self.nodes.values()),
            edges=list(self.edges.values()),
            items=items,
        )


class UndoSchema(BaseModel):
    """The request that reverts a write, so the client can offer Desfazer."""

    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    path: str
    body: dict[str, Any] | None = None


class WriteSchema(BaseModel):
    """Result (or preview, with ``dry_run``) of a write."""

    applied: bool
    mutations: list[str] = Field(
        description="Mutations JSON e DDL de schema, na ordem de execução"
    )
    queries: list[str] = Field(
        description="Leituras feitas para montar a escrita"
    )
    node: str | None = Field(None, description="Nó do grafo escrito")
    key: int | None = None
    impacto: dict[str, int] = Field(
        default_factory=dict,
        description="O que sai das consultas junto (inativação)",
    )
    desfazer: UndoSchema | None = None
