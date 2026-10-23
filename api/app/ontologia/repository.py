import json
from typing import Any

from app.api.exc.exceptions import FieldError, does_not_exist, validation_error
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.repository import GraphRepository, type_ddl
from app.infra.graph.schemas import (
    GraphBuilder,
    GraphSchema,
    UndoSchema,
    WriteSchema,
    node_id,
)

from .concepts import NAMESPACE, StatusConcept, VertexConcept
from .schemas import (
    AncestralSchema,
    BuscaSchema,
    ClasseInputSchema,
    ClasseUpdateSchema,
    InativoSchema,
    IndividuoInputSchema,
    IndividuoSchema,
    IndividuoUpdateSchema,
    RelacaoInputSchema,
    RelacaoSchema,
)

CLASSE = VertexConcept.CLASSE
INDIVIDUO = VertexConcept.INDIVIDUO
RELACAO = VertexConcept.RELACAO
INACTIVE = StatusConcept.INACTIVE
NOME = "nome: ontologia.Individuo.nome"


def ativo(vertex: str) -> str:
    """Filter that hides inactive vertices of ``ontologia.<vertex>``."""
    return f'@filter(NOT eq(ontologia.{vertex}.status, "{INACTIVE}"))'


def _atributos(raw: str | None) -> dict[str, Any] | None:
    """Dgraph stores the attribute map as a JSON string."""
    return json.loads(raw) if raw else None


# Status joins the original schema the first time this process writes.
_status_ready = False
STATUS_SCHEMA = "\n".join(
    [
        *(
            f"ontologia.{v}.status: string @index(exact) ."
            for v in VertexConcept
        ),
        type_ddl(
            "ontologia.Classe",
            [
                "ontologia.Classe.id",
                "ontologia.Classe.nome",
                "ontologia.SubclasseDe",
            ]
            + ["ontologia.Classe.status"],
        ),
        type_ddl(
            "ontologia.Individuo",
            ["ontologia.Individuo.id", "ontologia.Individuo.nome"]
            + ["ontologia.Individuo.atributos", "ontologia.InstanciaDe"]
            + ["ontologia.Individuo.status"],
        ),
        type_ddl(
            "ontologia.Relacao",
            ["ontologia.Relacao.tipo", "ontologia.origem", "ontologia.destino"]
            + ["ontologia.Relacao.status"],
        ),
    ]
)


class OntologiaRepository(GraphRepository):
    def __init__(self, context: DgraphClient, dry_run: bool = False):
        super().__init__(context=context, namespace=NAMESPACE, dry_run=dry_run)

    async def fetch_ancestrais(
        self, classe: dict[str, Any]
    ) -> GraphSchema[AncestralSchema]:
        data = await self.query(
            "query ancestrais($id: int) { "
            "c(func: eq(ontologia.Classe.id, $id)) @recurse(depth: 32) { "
            "id: ontologia.Classe.id nome: ontologia.Classe.nome "
            f"pais: ontologia.SubclasseDe {ativo(CLASSE)} }} }}",
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
                **({"status": classe.get("status")} if nivel == 0 else {}),
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
            f"subclasses: ~ontologia.SubclasseDe {ativo(CLASSE)} "
            f"instancias: ~ontologia.InstanciaDe {ativo(INDIVIDUO)} }} }}",
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
                **({"status": classe.get("status")} if focus else {}),
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
        outro = f"{{ id: ontologia.Individuo.id {NOME} }}"
        data = await self.query(
            "query relacoes($id: int) { "
            "i(func: eq(ontologia.Individuo.id, $id)) { "
            f"saida: ~ontologia.origem {ativo(RELACAO)} {{ uid "
            "tipo: ontologia.Relacao.tipo "
            f"outro: ontologia.destino {ativo(INDIVIDUO)} {outro} }} "
            f"entrada: ~ontologia.destino {ativo(RELACAO)} {{ uid "
            "tipo: ontologia.Relacao.tipo "
            f"outro: ontologia.origem {ativo(INDIVIDUO)} {outro} }} }} }}",
            id=individuo_id,
        )
        graph = GraphBuilder()
        focus = graph.node(
            INDIVIDUO,
            individuo_id,
            individuo["nome"],
            "focus",
            atributos=_atributos(individuo.get("atributos")),
            status=individuo.get("status"),
        )
        items: list[RelacaoSchema] = []
        node = data["i"][0] if data["i"] else {}
        eu = (individuo_id, individuo["nome"])
        for sentido in ("saida", "entrada"):
            for relacao in node.get(sentido, []):
                for o in relacao.get("outro", []):
                    other = graph.node(INDIVIDUO, o["id"], o["nome"], "result")
                    ele = (o["id"], o["nome"])
                    origem, destino = (
                        (eu, ele) if sentido == "saida" else (ele, eu)
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
                            relacao_id=int(relacao["uid"], 16),
                        )
                    )
        return graph.build(self.queries, items)

    async def fetch_inativos(self) -> GraphSchema[InativoSchema]:
        data = await self.query(
            "{ c(func: eq(ontologia.Classe.status, "
            f'"{INACTIVE}")) {{ id: ontologia.Classe.id nome: ontologia.Classe.nome }} '
            f'i(func: eq(ontologia.Individuo.status, "{INACTIVE}")) '
            f"{{ id: ontologia.Individuo.id {NOME} }} "
            f'r(func: eq(ontologia.Relacao.status, "{INACTIVE}")) {{ uid '
            "tipo: ontologia.Relacao.tipo "
            f"origem: ontologia.origem {{ id: ontologia.Individuo.id {NOME} }} "
            f"destino: ontologia.destino {{ id: ontologia.Individuo.id {NOME} }} }} }}"
        )
        graph = GraphBuilder()
        items: list[InativoSchema] = []
        for tipo, rows in ((CLASSE, data["c"]), (INDIVIDUO, data["i"])):
            for row in rows:
                graph.node(
                    tipo, row["id"], row["nome"], "result", status=INACTIVE
                )
                items.append(
                    InativoSchema(tipo=tipo, id=row["id"], nome=row["nome"])
                )
        for row in data["r"]:
            if not (row.get("origem") and row.get("destino")):
                continue
            origem, destino = row["origem"][0], row["destino"][0]
            graph.edge(
                graph.node(INDIVIDUO, origem["id"], origem["nome"]),
                graph.node(INDIVIDUO, destino["id"], destino["nome"]),
                row["tipo"],
            )
            items.append(
                InativoSchema(
                    tipo=RELACAO,
                    id=int(row["uid"], 16),
                    nome=f"{origem['nome']} {row['tipo']} {destino['nome']}",
                    relacao_id=int(row["uid"], 16),
                )
            )
        return graph.build(self.queries, items)

    async def fetch_busca(
        self, q: str, tipo: VertexConcept
    ) -> list[BuscaSchema]:
        # ponytail: the ontology is small (17 classes, 86 individuals), so
        # matching happens here; a trigram index takes over if it grows.
        data = await self.query(
            f"{{ v(func: type(ontologia.{tipo})) {ativo(tipo)} {{ "
            f"id: ontologia.{tipo}.id nome: ontologia.{tipo}.nome }} }}"
        )
        termo = q.casefold()
        found = [v for v in data["v"] if termo in v["nome"].casefold()]
        found.sort(
            key=lambda v: (
                not v["nome"].casefold().startswith(termo),
                v["nome"],
            )
        )
        return [
            BuscaSchema(id=v["id"], nome=v["nome"], tipo=tipo)
            for v in found[:20]
        ]

    async def fetch_tipos_relacao(self) -> list[str]:
        data = await self.query(
            "{ t(func: type(ontologia.Relacao)) "
            "@groupby(ontologia.Relacao.tipo) { count(uid) } }"
        )
        groups = data["t"][0]["@groupby"] if data["t"] else []
        groups.sort(key=lambda g: -g["count"])
        return [g["ontologia.Relacao.tipo"] for g in groups]

    # Writes ---------------------------------------------------------------

    async def _ensure_status(self) -> None:
        global _status_ready
        if not _status_ready and not self.dry_run:
            await self.context.alter(STATUS_SCHEMA)
            _status_ready = True

    async def _next_id(self, vertex: VertexConcept) -> int:
        data = await self.query(
            f"{{ var(func: type(ontologia.{vertex})) {{ m as ontologia.{vertex}.id }} "
            "r() { max: max(val(m)) } }"
        )
        return int(data["r"][0].get("max") or 0) + 1

    async def _uid(self, vertex: VertexConcept, id_: int, field: str) -> str:
        found = await self.get_vertex(vertex, id_)
        if found is None:
            raise validation_error(
                f"{vertex} {id_} não existe",
                fields=[
                    FieldError(name=field, detail=f"{vertex} {id_} não existe")
                ],
            )
        return found["uid"]

    async def create_classe(self, payload: ClasseInputSchema) -> WriteSchema:
        await self._ensure_status()
        id_ = await self._next_id(CLASSE)
        node: dict[str, Any] = {
            "uid": "_:classe",
            "dgraph.type": "ontologia.Classe",
            "ontologia.Classe.id": id_,
            "ontologia.Classe.nome": payload.nome,
            "ontologia.Classe.status": "active",
        }
        if payload.pai_id is not None:
            node["ontologia.SubclasseDe"] = [
                {"uid": await self._uid(CLASSE, payload.pai_id, "pai_id")}
            ]
        await self.mutate({"set": [node]})
        return self.written(node_id(CLASSE, id_), id_)

    async def update_classe(
        self, classe: dict[str, Any], payload: ClasseUpdateSchema
    ) -> WriteSchema:
        await self._ensure_status()
        uid = classe["uid"]
        changes: dict[str, Any] = {"uid": uid}
        mutations: list[dict[str, Any]] = []
        if payload.nome is not None:
            changes["ontologia.Classe.nome"] = payload.nome
        if "pai_id" in payload.model_fields_set:
            mutations.append(
                {"delete": [{"uid": uid, "ontologia.SubclasseDe": None}]}
            )
            if payload.pai_id is not None:
                await self._reject_cycle(classe, payload.pai_id)
                changes["ontologia.SubclasseDe"] = [
                    {"uid": await self._uid(CLASSE, payload.pai_id, "pai_id")}
                ]
        if len(changes) > 1:
            mutations.append({"set": [changes]})
        if mutations:
            await self.mutate(*mutations)
        return self.written(node_id(CLASSE, classe["id"]), classe["id"])

    async def _reject_cycle(self, classe: dict[str, Any], pai_id: int) -> None:
        """A class cannot descend from itself or from one of its subclasses."""
        data = await self.query(
            "query descendentes($id: int) { "
            "c(func: eq(ontologia.Classe.id, $id)) @recurse(depth: 32) { "
            "id: ontologia.Classe.id sub: ~ontologia.SubclasseDe } }",
            id=classe["id"],
        )
        ids: set[int] = set()

        def walk(node: dict[str, Any]) -> None:
            ids.add(node["id"])
            for sub in node.get("sub", []):
                walk(sub)

        for root in data["c"]:
            walk(root)
        if pai_id in ids:
            raise validation_error(
                "A superclasse criaria um ciclo",
                fields=[
                    FieldError(
                        name="pai_id",
                        detail=f"{classe['nome']} não pode herdar de si mesma "
                        "nem de uma subclasse sua",
                    )
                ],
            )

    async def create_individuo(
        self, payload: IndividuoInputSchema
    ) -> WriteSchema:
        await self._ensure_status()
        id_ = await self._next_id(INDIVIDUO)
        node = {
            "uid": "_:individuo",
            "dgraph.type": "ontologia.Individuo",
            "ontologia.Individuo.id": id_,
            "ontologia.Individuo.nome": payload.nome,
            "ontologia.Individuo.atributos": json.dumps(
                payload.atributos, ensure_ascii=False
            ),
            "ontologia.Individuo.status": "active",
            "ontologia.InstanciaDe": [
                {"uid": await self._uid(CLASSE, payload.classe_id, "classe_id")}
            ],
        }
        await self.mutate({"set": [node]})
        return self.written(node_id(INDIVIDUO, id_), id_)

    async def update_individuo(
        self, individuo: dict[str, Any], payload: IndividuoUpdateSchema
    ) -> WriteSchema:
        await self._ensure_status()
        uid = individuo["uid"]
        changes: dict[str, Any] = {"uid": uid}
        mutations: list[dict[str, Any]] = []
        if payload.nome is not None:
            changes["ontologia.Individuo.nome"] = payload.nome
        if payload.atributos is not None:
            changes["ontologia.Individuo.atributos"] = json.dumps(
                payload.atributos, ensure_ascii=False
            )
        if payload.classe_id is not None:
            mutations.append(
                {"delete": [{"uid": uid, "ontologia.InstanciaDe": None}]}
            )
            changes["ontologia.InstanciaDe"] = [
                {"uid": await self._uid(CLASSE, payload.classe_id, "classe_id")}
            ]
        if len(changes) > 1:
            mutations.append({"set": [changes]})
        if mutations:
            await self.mutate(*mutations)
        return self.written(
            node_id(INDIVIDUO, individuo["id"]), individuo["id"]
        )

    async def create_relacao(self, payload: RelacaoInputSchema) -> WriteSchema:
        await self._ensure_status()
        origem = await self._uid(INDIVIDUO, payload.origem_id, "origem_id")
        destino = await self._uid(INDIVIDUO, payload.destino_id, "destino_id")
        uids = await self.mutate(
            {
                "set": [
                    {
                        "uid": "_:relacao",
                        "dgraph.type": "ontologia.Relacao",
                        "ontologia.Relacao.tipo": payload.tipo,
                        "ontologia.Relacao.status": "active",
                        "ontologia.origem": [{"uid": origem}],
                        "ontologia.destino": [{"uid": destino}],
                    }
                ]
            }
        )
        key = int(uids["relacao"], 16) if "relacao" in uids else None
        # The relation draws as an edge: the origin is the node to show.
        return self.written(node_id(INDIVIDUO, payload.origem_id), key)

    async def get_relacao(self, id_: int) -> dict[str, Any] | None:
        data = await self.context.query(
            "query r($id: string) { r(func: uid($id)) @filter(type(ontologia.Relacao)) "
            "{ uid status: ontologia.Relacao.status "
            "origem: ontologia.origem { id: ontologia.Individuo.id } } }",
            id=hex(id_),
        )
        return data["r"][0] if data["r"] else None

    async def impacto(self, vertex: VertexConcept, uid: str) -> dict[str, int]:
        """What leaves the queries together with this vertex."""
        counts = {
            CLASSE: "subclasses: count(~ontologia.SubclasseDe) "
            "individuos: count(~ontologia.InstanciaDe)",
            INDIVIDUO: "origem: count(~ontologia.origem) "
            "destino: count(~ontologia.destino)",
            RELACAO: "",
        }[vertex]
        if not counts:
            return {}
        data = await self.query(f"{{ v(func: uid({uid})) {{ {counts} }} }}")
        row = data["v"][0] if data["v"] else {}
        if vertex == INDIVIDUO:
            return {"relacoes": row.get("origem", 0) + row.get("destino", 0)}
        return {k: v for k, v in row.items() if v}

    async def set_status(
        self,
        vertex: VertexConcept,
        found: dict[str, Any],
        status: StatusConcept,
        node: str | None,
        path: str,
    ) -> WriteSchema:
        await self._ensure_status()
        if not found:
            raise does_not_exist(vertex)
        previous = found.get("status") or StatusConcept.ACTIVE
        impacto = (
            await self.impacto(vertex, found["uid"])
            if status == StatusConcept.INACTIVE
            else {}
        )
        await self.mutate(
            {
                "set": [
                    {"uid": found["uid"], f"ontologia.{vertex}.status": status}
                ]
            }
        )
        return self.written(
            node,
            impacto=impacto,
            desfazer=UndoSchema(
                method="PUT", path=path, body={"status": previous}
            ),
        )
