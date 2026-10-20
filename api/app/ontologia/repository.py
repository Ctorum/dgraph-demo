import json
from typing import Any

from app.infra.graph.adapter import DgraphClient
from app.infra.graph.repository import GraphRepository
from app.infra.graph.schemas import GraphBuilder, GraphSchema

from .concepts import NAMESPACE, VertexConcept
from .schemas import AncestralSchema, IndividuoSchema, RelacaoSchema

CLASSE = VertexConcept.CLASSE
INDIVIDUO = VertexConcept.INDIVIDUO
NOME = "nome: ontologia.Individuo.nome"


def _atributos(raw: str | None) -> dict[str, Any] | None:
    """Dgraph stores the attribute map as a JSON string."""
    return json.loads(raw) if raw else None


class OntologiaRepository(GraphRepository):
    def __init__(self, context: DgraphClient):
        super().__init__(context=context, namespace=NAMESPACE)

    async def fetch_ancestrais(
        self, classe: dict[str, Any]
    ) -> GraphSchema[AncestralSchema]:
        data = await self.query(
            "query ancestrais($id: int) { "
            "c(func: eq(ontologia.Classe.id, $id)) @recurse(depth: 32) { "
            "id: ontologia.Classe.id nome: ontologia.Classe.nome "
            "pais: ontologia.SubclasseDe } }",
            id=classe["id"],
        )
        graph = GraphBuilder()
        items: list[AncestralSchema] = []

        def walk(node: dict[str, Any], nivel: int) -> str:
            id_ = graph.node(
                CLASSE,
                node["id"],
                node["nome"],
                "focus" if nivel == 0 else "result",
            )
            if nivel:
                items.append(
                    AncestralSchema(
                        id=node["id"], nome=node["nome"], nivel=nivel
                    )
                )
            for pai in node.get("pais", []):
                graph.edge(id_, walk(pai, nivel + 1), "SubclasseDe")
            return id_

        for root in data["c"]:
            walk(root, 0)
        return graph.build(self.queries, items)

    async def fetch_individuos(
        self, classe: dict[str, Any]
    ) -> GraphSchema[IndividuoSchema]:
        """Instâncias da classe e de todas as subclasses (inferência)."""
        data = await self.query(
            "query individuos($id: int) { "
            "c(func: eq(ontologia.Classe.id, $id)) @recurse(depth: 32) { "
            "classe_id: ontologia.Classe.id classe: ontologia.Classe.nome "
            f"id: ontologia.Individuo.id {NOME} "
            "atributos: ontologia.Individuo.atributos "
            "subclasses: ~ontologia.SubclasseDe "
            "instancias: ~ontologia.InstanciaDe } }",
            id=classe["id"],
        )
        graph = GraphBuilder()
        individuos: dict[int, IndividuoSchema] = {}

        def walk(node: dict[str, Any], focus: bool) -> str:
            id_ = graph.node(
                CLASSE,
                node["classe_id"],
                node["classe"],
                "focus" if focus else "path",
            )
            for sub in node.get("subclasses", []):
                graph.edge(walk(sub, False), id_, "SubclasseDe")
            for ind in node.get("instancias", []):
                atributos = _atributos(ind.get("atributos"))
                graph.edge(
                    graph.node(
                        INDIVIDUO,
                        ind["id"],
                        ind["nome"],
                        "result",
                        atributos=atributos,
                    ),
                    id_,
                    "InstanciaDe",
                )
                item = individuos.setdefault(
                    ind["id"],
                    IndividuoSchema(
                        id=ind["id"],
                        nome=ind["nome"],
                        atributos=atributos,
                        classes=[],
                    ),
                )
                item.classes.append(node["classe"])
            return id_

        for root in data["c"]:
            walk(root, True)
        return graph.build(self.queries, list(individuos.values()))

    async def fetch_relacoes(
        self, individuo: dict[str, Any]
    ) -> GraphSchema[RelacaoSchema]:
        # Relacao is a node (it carries tipo): origem <- relacao -> destino.
        individuo_id = individuo["id"]
        data = await self.query(
            "query relacoes($id: int) { "
            "i(func: eq(ontologia.Individuo.id, $id)) { "
            "saida: ~ontologia.origem { tipo: ontologia.Relacao.tipo "
            f"outro: ontologia.destino {{ id: ontologia.Individuo.id {NOME} }} }} "
            "entrada: ~ontologia.destino { tipo: ontologia.Relacao.tipo "
            f"outro: ontologia.origem {{ id: ontologia.Individuo.id {NOME} }} }} }} }}",
            id=individuo_id,
        )
        graph = GraphBuilder()
        focus = graph.node(
            INDIVIDUO,
            individuo_id,
            individuo["nome"],
            "focus",
            atributos=_atributos(individuo.get("atributos")),
        )
        items: list[RelacaoSchema] = []
        node = data["i"][0] if data["i"] else {}
        for sentido in ("saida", "entrada"):
            for relacao in node.get(sentido, []):
                for outro in relacao["outro"]:
                    other = graph.node(
                        INDIVIDUO, outro["id"], outro["nome"], "result"
                    )
                    origem, destino = (
                        (
                            (individuo_id, individuo["nome"]),
                            (outro["id"], outro["nome"]),
                        )
                        if sentido == "saida"
                        else (
                            (outro["id"], outro["nome"]),
                            (individuo_id, individuo["nome"]),
                        )
                    )
                    graph.edge(
                        focus if sentido == "saida" else other,
                        other if sentido == "saida" else focus,
                        relacao["tipo"],
                    )
                    items.append(
                        RelacaoSchema(
                            tipo=relacao["tipo"],
                            origem_id=origem[0],
                            origem=origem[1],
                            destino_id=destino[0],
                            destino=destino[1],
                        )
                    )
        return graph.build(self.queries, items)
