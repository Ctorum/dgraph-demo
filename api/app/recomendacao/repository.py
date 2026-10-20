from collections import Counter, defaultdict
from typing import Any

from app.infra.graph.adapter import DgraphClient
from app.infra.graph.repository import GraphRepository
from app.infra.graph.schemas import GraphBuilder, GraphSchema

from .concepts import NAMESPACE, VertexConcept
from .schemas import RecomendacaoSchema

# Caminhos de apoio desenhados por item recomendado
PATHS_PER_ITEM = 3

# Comprou is a node (it carries dias_atras): usuario <-origem- compra
# -destino-> produto. Avaliou shares origem/destino, hence the type filter.
COMPRAS = "~recomendacao.origem @filter(type(recomendacao.Comprou))"
COMPRADORES = "~recomendacao.destino @filter(type(recomendacao.Comprou))"
PRODUTO = "id: recomendacao.Produto.id nome: recomendacao.Produto.nome"
USUARIO = "id: recomendacao.Usuario.id nome: recomendacao.Usuario.nome"


def _top(
    rows: list[dict[str, Any]], limit: int
) -> tuple[dict[int, int], dict[int, str]]:
    score = Counter(row["id"] for row in rows)
    nomes = {row["id"]: row["nome"] for row in rows}
    return dict(score.most_common(limit)), nomes


class RecomendacaoRepository(GraphRepository):
    def __init__(self, context: DgraphClient):
        super().__init__(context=context, namespace=NAMESPACE)

    async def fetch_produtos(
        self, usuario: dict[str, Any], limit: int
    ) -> GraphSchema[RecomendacaoSchema]:
        """Filtragem colaborativa: comprado por quem comprou o mesmo."""
        usuario_id = usuario["id"]
        data = await self.query(
            "query produtos($id: int) { "
            "u(func: eq(recomendacao.Usuario.id, $id)) { "
            f"compras: {COMPRAS} {{ p: recomendacao.destino {{ {PRODUTO} "
            f"compradores: {COMPRADORES} {{ o: recomendacao.origem "
            f"@filter(NOT eq(recomendacao.Usuario.id, $id)) {{ {USUARIO} "
            f"compras: {COMPRAS} {{ rec: recomendacao.destino {{ {PRODUTO} "
            "} } } } } } } }",
            id=usuario_id,
        )
        rows = [
            {"p": p, "o": o, **rec}
            for compra in (data["u"][0].get("compras", []) if data["u"] else [])
            for p in compra["p"]
            for comprador in p.get("compradores", [])
            for o in comprador.get("o", [])
            for outra in o.get("compras", [])
            for rec in outra["rec"]
        ]
        comprados = {row["p"]["id"] for row in rows}
        rows = [row for row in rows if row["id"] not in comprados]
        top, nomes = _top(rows, limit)

        graph = GraphBuilder()
        focus = graph.node(
            VertexConcept.USUARIO, usuario_id, usuario["nome"], "focus"
        )
        paths: defaultdict[int, int] = defaultdict(int)
        for row in rows:
            rec_id = row["id"]
            if rec_id not in top or paths[rec_id] >= PATHS_PER_ITEM:
                continue
            paths[rec_id] += 1
            p = graph.node(
                VertexConcept.PRODUTO, row["p"]["id"], row["p"]["nome"]
            )
            o = graph.node(
                VertexConcept.USUARIO, row["o"]["id"], row["o"]["nome"]
            )
            rec = graph.node(
                VertexConcept.PRODUTO,
                rec_id,
                row["nome"],
                "result",
                score=top[rec_id],
            )
            graph.edge(focus, p, "Comprou")
            graph.edge(o, p, "Comprou")
            graph.edge(o, rec, "Comprou")
        return graph.build(
            self.queries,
            [
                RecomendacaoSchema(id=id_, nome=nomes[id_], score=n)
                for id_, n in top.items()
            ],
        )

    async def fetch_usuarios_sugeridos(
        self, usuario: dict[str, Any], limit: int
    ) -> GraphSchema[RecomendacaoSchema]:
        """Amigos de amigos que o usuário ainda não segue."""
        usuario_id = usuario["id"]
        data = await self.query(
            "query seguir($id: int) { "
            "u(func: eq(recomendacao.Usuario.id, $id)) { "
            f"f: recomendacao.Segue {{ {USUARIO} "
            "s: recomendacao.Segue @filter(NOT eq(recomendacao.Usuario.id, $id)) "
            f"{{ {USUARIO} }} }} }} }}",
            id=usuario_id,
        )
        seguidos = data["u"][0].get("f", []) if data["u"] else []
        ja_segue = {f["id"] for f in seguidos}
        rows = [
            {"f": f, **s}
            for f in seguidos
            for s in f.get("s", [])
            if s["id"] not in ja_segue
        ]
        top, nomes = _top(rows, limit)

        graph = GraphBuilder()
        focus = graph.node(
            VertexConcept.USUARIO, usuario_id, usuario["nome"], "focus"
        )
        for row in rows:
            if row["id"] not in top:
                continue
            f = graph.node(
                VertexConcept.USUARIO, row["f"]["id"], row["f"]["nome"]
            )
            s = graph.node(
                VertexConcept.USUARIO,
                row["id"],
                row["nome"],
                "result",
                score=top[row["id"]],
            )
            graph.edge(focus, f, "Segue")
            graph.edge(f, s, "Segue")
        return graph.build(
            self.queries,
            [
                RecomendacaoSchema(id=id_, nome=nomes[id_], score=n)
                for id_, n in top.items()
            ],
        )
