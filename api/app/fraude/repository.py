from typing import Any

from app.infra.graph.adapter import DgraphClient
from app.infra.graph.repository import GraphRepository
from app.infra.graph.schemas import GraphBuilder, GraphSchema, Role

from .concepts import IDENTIFICADORES, NAMESPACE, VertexConcept
from .schemas import (
    AnelSchema,
    CicloSchema,
    ConexaoSchema,
    TransferenciaSchema,
)

CLIENTE_FIELDS = (
    "id: fraude.Cliente.id nome: fraude.Cliente.nome "
    "risco: fraude.Cliente.risco bloqueado: fraude.Cliente.bloqueado"
)


def _cliente(
    graph: GraphBuilder, row: dict[str, Any], role: Role = "path"
) -> str:
    return graph.node(
        VertexConcept.CLIENTE,
        row["id"],
        row["nome"],
        role,
        risco=row.get("risco"),
        bloqueado=row.get("bloqueado"),
    )


def _conta(graph: GraphBuilder, id_: int, role: Role = "path") -> str:
    return graph.node(VertexConcept.CONTA, id_, f"Conta {id_}", role)


class FraudeRepository(GraphRepository):
    def __init__(self, context: DgraphClient):
        super().__init__(context=context, namespace=NAMESPACE)

    async def fetch_conexoes(
        self, cliente: dict[str, Any]
    ) -> GraphSchema[ConexaoSchema]:
        blocks = " ".join(
            f"{via}: fraude.{aresta} {{ id: fraude.{via}.id "
            f"valor: fraude.{via}.{campo} "
            f"outros: ~fraude.{aresta} @filter(NOT eq(fraude.Cliente.id, $id)) "
            f"{{ {CLIENTE_FIELDS} }} }}"
            for via, (aresta, campo) in IDENTIFICADORES.items()
        )
        data = await self.query(
            "query conexoes($id: int) { "
            f"c(func: eq(fraude.Cliente.id, $id)) {{ {blocks} }} }}",
            id=cliente["id"],
        )
        graph = GraphBuilder()
        focus = _cliente(graph, cliente, "focus")
        items: list[ConexaoSchema] = []
        for via, (aresta, _) in IDENTIFICADORES.items():
            for ident in data["c"][0].get(via, []) if data["c"] else []:
                if not ident.get("outros"):
                    continue
                node = graph.node(via, ident["id"], ident["valor"])
                graph.edge(focus, node, aresta)
                for outro in ident["outros"]:
                    graph.edge(_cliente(graph, outro, "result"), node, aresta)
                    items.append(
                        ConexaoSchema(
                            id=outro["id"],
                            nome=outro["nome"],
                            via=via,
                            valor=ident["valor"],
                        )
                    )
        return graph.build(self.queries, items)

    async def fetch_aneis(self, min_clientes: int) -> GraphSchema[AnelSchema]:
        blocks = " ".join(
            f"var(func: type(fraude.{via})) {{ n{via} as count(~fraude.{aresta}) }} "
            f"{via}(func: uid(n{via})) @filter(ge(val(n{via}), $n)) {{ "
            f"id: fraude.{via}.id valor: fraude.{via}.{campo} "
            f"clientes: ~fraude.{aresta} {{ id: fraude.Cliente.id "
            "nome: fraude.Cliente.nome } }"
            for via, (aresta, campo) in IDENTIFICADORES.items()
        )
        data = await self.query(
            f"query aneis($n: int) {{ {blocks} }}", n=min_clientes
        )
        graph = GraphBuilder()
        items: list[AnelSchema] = []
        for via, (aresta, _) in IDENTIFICADORES.items():
            for ident in data.get(via, []):
                node = graph.node(via, ident["id"], ident["valor"], "result")
                for cliente in ident["clientes"]:
                    graph.edge(_cliente(graph, cliente), node, aresta)
                items.append(
                    AnelSchema(
                        via=via,
                        valor=ident["valor"],
                        clientes=[c["id"] for c in ident["clientes"]],
                    )
                )
        return graph.build(self.queries, items)

    async def fetch_ciclos(self, conta_id: int) -> GraphSchema[CicloSchema]:
        # Transfere is a node (it carries valor), so each hop is
        # conta <-origem- transferencia -destino-> conta.
        # ponytail: fixed 3-hop cycles, add a depth param if needed
        hop = (
            "~fraude.origem @filter(type(fraude.Transfere)) "
            "{{ valor: fraude.Transfere.valor {alias}: fraude.destino "
            "{{ id: fraude.Conta.id {inner} }} }}"
        )
        last = hop.format(alias="volta", inner="")
        middle = hop.format(alias="c", inner=f"t3: {last}")
        first = hop.format(alias="b", inner=f"t2: {middle}")
        data = await self.query(
            "query ciclos($id: int) { "
            f"a(func: eq(fraude.Conta.id, $id)) {{ t1: {first} }} }}",
            id=conta_id,
        )
        graph = GraphBuilder()
        focus = _conta(graph, conta_id, "focus")
        items: list[CicloSchema] = []
        for t1 in data["a"][0].get("t1", []) if data["a"] else []:
            for b in t1["b"]:
                for t2 in b.get("t2", []):
                    for c in t2["c"]:
                        for t3 in c.get("t3", []):
                            if t3["volta"][0]["id"] != conta_id:
                                continue
                            if len({conta_id, b["id"], c["id"]}) < 3:
                                continue
                            nb = _conta(graph, b["id"], "result")
                            nc = _conta(graph, c["id"], "result")
                            graph.edge(
                                focus, nb, "Transfere", valor=t1["valor"]
                            )
                            graph.edge(nb, nc, "Transfere", valor=t2["valor"])
                            graph.edge(
                                nc, focus, "Transfere", valor=t3["valor"]
                            )
                            items.append(
                                CicloSchema(contas=[conta_id, b["id"], c["id"]])
                            )
        return graph.build(self.queries, items)

    async def fetch_transferencias_suspeitas(
        self, limit: int
    ) -> GraphSchema[TransferenciaSchema]:
        data = await self.query(
            "query suspeitas($limit: int) { "
            "t(func: type(fraude.Transfere), orderdesc: fraude.Transfere.valor, "
            "first: $limit) @filter(eq(fraude.Transfere.suspeita, true)) { "
            "valor: fraude.Transfere.valor dias_atras: fraude.Transfere.dias_atras "
            "origem: fraude.origem { id: fraude.Conta.id } "
            "destino: fraude.destino { id: fraude.Conta.id } } }",
            limit=limit,
        )
        graph = GraphBuilder()
        items: list[TransferenciaSchema] = []
        for t in data["t"]:
            origem, destino = t["origem"][0]["id"], t["destino"][0]["id"]
            graph.edge(
                _conta(graph, origem, "result"),
                _conta(graph, destino, "result"),
                "Transfere",
                valor=t["valor"],
                dias_atras=t["dias_atras"],
                suspeita=True,
            )
            items.append(
                TransferenciaSchema(
                    origem=origem,
                    destino=destino,
                    valor=t["valor"],
                    dias_atras=t["dias_atras"],
                )
            )
        return graph.build(self.queries, items)
