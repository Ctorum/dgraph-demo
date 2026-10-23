import re
import unicodedata
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from app.api.exc.exceptions import (
    APIError,
    FieldError,
    conflict,
    does_not_exist,
    validation_error,
)
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.repository import GraphRepository, type_ddl
from app.infra.graph.schemas import (
    GraphBuilder,
    GraphSchema,
    Role,
    UndoSchema,
    WriteSchema,
    node_id,
)

from .concepts import (
    INSTANCE_FIELDS,
    NAMESPACE,
    PREDICATE_SCHEMA,
    ConceptTypeConcept,
    DirecaoConcept,
    FieldTypeConcept,
    StatusConcept,
    VertexConcept,
)
from .schemas import (
    AlvoSchema,
    BuscaSchema,
    CampoFormSchema,
    CampoInputSchema,
    CampoSchema,
    CampoUpdateSchema,
    ConexaoSchema,
    DominioInputSchema,
    DominioUpdateSchema,
    FormularioSchema,
    InativoSchema,
    InstanciaInputSchema,
    InstanciaSchema,
    InstanciaUpdateSchema,
    RefSchema,
    RelacaoInputSchema,
    RelacaoMapaSchema,
    TipoRelacaoInputSchema,
    TipoRelacaoSchema,
)

DOMINIO = VertexConcept.DOMINIO
DOMAIN = ConceptTypeConcept.DOMAIN
DOMINIO_FIELDS = (
    "uid nome: kosmos.name categoria: kosmos.category "
    "total: count(~kosmos.instanceOf)"
)
INSTANCIA_FIELDS = (
    "uid apelido: kosmos.nickname nome: kosmos.name "
    "dominio: kosmos.instanceOf { uid nome: kosmos.name }"
)
ATIVO = '@filter(NOT eq(kosmos.status, "inactive"))'
# Reverse references per field: enough to show the shape, not the census.
PER_FIELD = 20
PER_RELATION = 50


def key(uid: str) -> int:
    """Dgraph uids are hex; the API exposes them as plain integers."""
    return int(uid, 16)


def label(node: dict[str, Any]) -> str:
    return node.get("apelido") or node.get("nome") or node["uid"]


def dominio_of(node: dict[str, Any]) -> str:
    # Selectors can point straight at a concept, which has no domain.
    return node.get("dominio", {}).get("nome", "Conceito")


class KosmosRepository(GraphRepository):
    def __init__(self, context: DgraphClient, dry_run: bool = False):
        super().__init__(context=context, namespace=NAMESPACE, dry_run=dry_run)

    async def get_dominio(self, id_: int) -> dict[str, Any] | None:
        data = await self.context.query(
            f"query d($id: string) {{ d(func: uid($id)) "
            # Relation types have a model (their selectors) like domains.
            f'@filter(eq(kosmos.conceptType, "{DOMAIN}") OR '
            f'eq(kosmos.conceptType, "{ConceptTypeConcept.RELATIONSHIP}")) '
            f"{{ {DOMINIO_FIELDS} status: kosmos.status "
            "descricao: kosmos.description kosmos_id: kosmos.id "
            "conceito: kosmos.conceptType version: kosmos.version } }",
            id=hex(id_),
        )
        return data["d"][0] if data["d"] else None

    async def get_instancia(self, id_: int) -> dict[str, Any] | None:
        data = await self.context.query(
            "query i($id: string) { i(func: uid($id)) "
            "@filter(has(kosmos.instanceOf)) { "
            f"{INSTANCIA_FIELDS} status: kosmos.status "
            "fatos: count(~kosmos.factEntity) } }",
            id=hex(id_),
        )
        return data["i"][0] if data["i"] else None

    def _dominio(
        self, graph: GraphBuilder, node: dict[str, Any], role: Role = "result"
    ) -> str:
        relationship = node.get("conceito") == ConceptTypeConcept.RELATIONSHIP
        return graph.node(
            "TipoRelacao" if relationship else DOMINIO,
            key(node["uid"]),
            node["nome"],
            role,
            categoria=node.get("categoria"),
            # Relation types count relations, not instances.
            instancias=None if relationship else node.get("total"),
            **{k: node[k] for k in ("status", "descricao") if node.get(k)},
        )

    def _instancia(
        self,
        graph: GraphBuilder,
        node: dict[str, Any],
        role: Role = "result",
        **props: Any,
    ) -> str:
        return graph.node(
            dominio_of(node), key(node["uid"]), label(node), role, **props
        )

    async def fetch_mapa(self) -> GraphSchema[RelacaoMapaSchema]:
        """Domains linked by the relations that actually exist in the data."""
        # ponytail: reads every relation (~12k rows, ~2 MB) to aggregate in
        # Python; cache it if the map gets slow.
        data = await self.query(
            f"{{ r(func: has(kosmos.subject)) {ATIVO} {{ "
            f"tipo: kosmos.relationType {ATIVO} {{ nome: kosmos.name }} "
            f"s: kosmos.subject {ATIVO} {{ d: kosmos.instanceOf {ATIVO} "
            f"{{ {DOMINIO_FIELDS} }} }} "
            f"o: kosmos.object {ATIVO} {{ d: kosmos.instanceOf {ATIVO} "
            f"{{ {DOMINIO_FIELDS} }} }} }} }}"
        )
        graph = GraphBuilder()
        pares: Counter[tuple[str, str, str]] = Counter()
        for relacao in data["r"]:
            try:
                tipo = relacao["tipo"]["nome"]
                origem, destino = relacao["s"]["d"], relacao["o"]["d"]
            except KeyError:
                continue  # relação incompleta: sem sujeito ou objeto
            pares[
                (
                    tipo,
                    self._dominio(graph, origem),
                    self._dominio(graph, destino),
                )
            ] += 1
        items = []
        for (tipo, origem, destino), quantidade in pares.most_common():
            graph.edge(
                origem, destino, tipo, quantidade=quantidade, relacao=True
            )
            items.append(
                RelacaoMapaSchema(
                    relacao=tipo,
                    origem=graph.nodes[origem].label,
                    destino=graph.nodes[destino].label,
                    quantidade=quantidade,
                )
            )
        return graph.build(self.queries, items)

    async def fetch_modelo(
        self, dominio: dict[str, Any]
    ) -> GraphSchema[CampoSchema]:
        """Selector fields out of the domain and fields pointing into it."""
        data = await self.query(
            "query modelo($id: string) { d(func: uid($id)) { "
            f"campos: kosmos.hasField {ATIVO} {{ uid nome: kosmos.name "
            "tipo: kosmos.fieldType "
            f"alvo: kosmos.selectorTarget {ATIVO} {{ {DOMINIO_FIELDS} }} }} "
            f"referencias: ~kosmos.selectorTarget {ATIVO} {{ uid nome: kosmos.name "
            "tipo: kosmos.fieldType dono: ~kosmos.hasField "
            f'@filter((eq(kosmos.conceptType, "{DOMAIN}") OR '
            f'eq(kosmos.conceptType, "{ConceptTypeConcept.RELATIONSHIP}")) '
            'AND NOT eq(kosmos.status, "inactive")) '
            f"{{ {DOMINIO_FIELDS} conceito: kosmos.conceptType }} }} }} }}",
            id=dominio["uid"],
        )
        graph = GraphBuilder()
        focus = self._dominio(graph, dominio, "focus")
        nome = dominio["nome"]
        items: list[CampoSchema] = []
        node = data["d"][0] if data["d"] else {}
        for campo in node.get("campos", []):
            alvos = campo.get("alvo", [])
            for alvo in alvos:
                if alvo["uid"] != dominio["uid"]:
                    graph.edge(focus, self._dominio(graph, alvo), campo["nome"])
            items.append(
                CampoSchema(
                    campo=campo["nome"],
                    tipo=campo.get("tipo", "?"),
                    origem=nome,
                    destino=", ".join(a["nome"] for a in alvos) or None,
                    campo_id=key(campo["uid"]),
                )
            )
        for campo in node.get("referencias", []):
            for dono in campo.get("dono", []):
                if dono["uid"] == dominio["uid"]:
                    continue  # already listed among its own fields
                # Relation types point at domains through their selectors.
                graph.edge(
                    self._dominio(graph, dono, "path"), focus, campo["nome"]
                )
                items.append(
                    CampoSchema(
                        campo=campo["nome"],
                        tipo=campo.get("tipo", "?"),
                        origem=dono["nome"],
                        destino=nome,
                        campo_id=key(campo["uid"]),
                    )
                )
        return graph.build(self.queries, items)

    async def fetch_instancias(
        self, dominio: dict[str, Any], limit: int
    ) -> GraphSchema[InstanciaSchema]:
        data = await self.query(
            "query instancias($id: string, $limit: int) { d(func: uid($id)) { "
            "i: ~kosmos.instanceOf (orderasc: kosmos.nickname, first: $limit) "
            f"{ATIVO} {{ "
            "uid apelido: kosmos.nickname nome: kosmos.name status: kosmos.status } } }",
            id=dominio["uid"],
            limit=limit,
        )
        graph = GraphBuilder()
        focus = self._dominio(graph, dominio, "focus")
        items: list[InstanciaSchema] = []
        node = data["d"][0] if data["d"] else {}
        for instancia in node.get("i", []):
            id_ = graph.node(
                dominio["nome"],
                key(instancia["uid"]),
                label(instancia),
                "result",
                status=instancia.get("status"),
            )
            graph.edge(id_, focus, "instanceOf")
            items.append(
                InstanciaSchema(
                    id=key(instancia["uid"]),
                    nome=label(instancia),
                    status=instancia.get("status"),
                )
            )
        return graph.build(self.queries, items)

    async def fetch_conexoes(
        self, instancia: dict[str, Any]
    ) -> GraphSchema[ConexaoSchema]:
        """Selector values, references from other instances and relations.

        Field predicates are per domain (``kosmos.Nome_do_Campo_<hash>``), so
        the first query reads the model and the second is built from it.
        """
        # Incoming selectors target this domain or an abstract one (Persona),
        # which every instance may satisfy.
        modelo = await self.query(
            "query modelo($id: string) { "
            "var(func: uid($id)) { d as kosmos.instanceOf } "
            f'abstratos as var(func: eq(kosmos.conceptType, "{DOMAIN}")) '
            "@filter(NOT has(~kosmos.instanceOf)) "
            f"campos(func: uid(d)) {{ kosmos.hasField {ATIVO} {{ "
            "nome: kosmos.name tipo: kosmos.fieldType pred: kosmos.fieldPredicate } } "
            f"entrada(func: uid(d, abstratos)) {{ ~kosmos.selectorTarget {ATIVO} {{ "
            "nome: kosmos.name pred: kosmos.fieldPredicate } } }",
            id=instancia["uid"],
        )
        campos = [
            c
            for d in modelo["campos"]
            for c in d.get("kosmos.hasField", [])
            if c.get("pred")
        ]
        entrada = {
            c["pred"]: c["nome"]
            for d in modelo["entrada"]
            for c in d.get("~kosmos.selectorTarget", [])
            if c.get("pred")
        }
        # Not every selector predicate was declared with @reverse.
        reversos = (
            await self.context.query(
                f"schema(pred: [{', '.join(entrada)}]) {{ reverse }}"
            )
            if entrada
            else {}
        )
        com_reverso = {
            p["predicate"]
            for p in reversos.get("schema", [])
            if p.get("reverse")
        }
        entrada = {p: nome for p, nome in entrada.items() if p in com_reverso}
        saida = {
            c["pred"]: c["nome"] for c in campos if c.get("tipo") == "selector"
        }
        escalares = {
            c["pred"]: c["nome"] for c in campos if c.get("tipo") != "selector"
        }

        # Aliases are positional: the predicate names are not valid aliases.
        blocks = [
            *(f"e{i}: {p}" for i, p in enumerate(escalares)),
            *(
                f"s{i}: {p} (first: {PER_FIELD}) {ATIVO} {{ ...instancia }}"
                for i, p in enumerate(saida)
            ),
            *(
                f"r{i}: ~{p} (first: {PER_FIELD}) "
                "@filter(has(kosmos.instanceOf) AND NOT eq(kosmos.status, "
                '"inactive")) { ...instancia }'
                for i, p in enumerate(entrada)
            ),
            (
                f"sujeito: ~kosmos.subject (first: {PER_RELATION}) {ATIVO} {{ uid "
                f"via: kosmos.relationType {ATIVO} {{ nome: kosmos.name }} "
                f"outro: kosmos.object {ATIVO} {{ ...instancia }} }}"
            ),
            (
                f"objeto: ~kosmos.object (first: {PER_RELATION}) {ATIVO} {{ uid "
                f"via: kosmos.relationType {ATIVO} {{ nome: kosmos.name }} "
                f"outro: kosmos.subject {ATIVO} {{ ...instancia }} }}"
            ),
        ]
        data = await self.query(
            f"query conexoes($id: string) {{ i(func: uid($id)) {{ {' '.join(blocks)} }} }} "
            f"fragment instancia {{ {INSTANCIA_FIELDS} }}",
            id=instancia["uid"],
        )
        node = data["i"][0] if data["i"] else {}

        props = {
            nome: node[f"e{i}"]
            for i, nome in enumerate(escalares.values())
            if f"e{i}" in node
        }
        graph = GraphBuilder()
        focus = self._instancia(
            graph,
            instancia,
            "focus",
            status=instancia.get("status"),
            fatos=instancia.get("fatos"),
            **props,
        )
        items: list[ConexaoSchema] = []

        def link(
            outros: Any,
            via: str,
            direcao: DirecaoConcept,
            relacao: str | None = None,
        ) -> None:
            # Single-valued uid predicates come back as an object.
            for outro in outros if isinstance(outros, list) else [outros]:
                if outro["uid"] == instancia["uid"]:
                    continue
                other = self._instancia(graph, outro)
                # Relations are REL_ nodes drawn as one edge; selectors are
                # plain uid edges.
                if direcao == DirecaoConcept.SAIDA:
                    graph.edge(focus, other, via, relacao=relacao is not None)
                else:
                    graph.edge(other, focus, via, relacao=relacao is not None)
                items.append(
                    ConexaoSchema(
                        via=via,
                        direcao=direcao,
                        id=key(outro["uid"]),
                        nome=label(outro),
                        dominio=dominio_of(outro),
                        relacao_id=key(relacao) if relacao else None,
                    )
                )

        for i, nome in enumerate(saida.values()):
            link(node.get(f"s{i}", []), nome, DirecaoConcept.SAIDA)
        for i, nome in enumerate(entrada.values()):
            link(node.get(f"r{i}", []), nome, DirecaoConcept.ENTRADA)
        for relacao in node.get("sujeito", []):
            if "outro" in relacao and "via" in relacao:
                link(
                    relacao["outro"],
                    relacao["via"]["nome"],
                    DirecaoConcept.SAIDA,
                    relacao["uid"],
                )
        for relacao in node.get("objeto", []):
            if "outro" in relacao and "via" in relacao:
                link(
                    relacao["outro"],
                    relacao["via"]["nome"],
                    DirecaoConcept.ENTRADA,
                    relacao["uid"],
                )
        return graph.build(self.queries, items)


# Writes ------------------------------------------------------------------
#
# Everything written follows the source system's conventions, read from the
# data: ``kosmos.id`` is ``_:<uuid4>``; a field predicate is
# ``kosmos.<Name, ascii, 40 chars>_<first 8 hex of the field's uuid>``; an
# instance is ``DOM_<8 hex of its domain's uuid>_<epoch ms>_<n>`` typed
# ``kosmos.<Domain_Name>``; a relation is ``REL_<8 hex of its type's uuid>``.

RELATIONSHIP = ConceptTypeConcept.RELATIONSHIP
SELECTOR = FieldTypeConcept.SELECTOR
TIPO_RELACAO = "TipoRelacao"
CAMPO = "Campo"
CONCEPT_NODE = {
    DOMAIN: DOMINIO,
    ConceptTypeConcept.FIELD: CAMPO,
    RELATIONSHIP: TIPO_RELACAO,
}
CONCEPT_FIELDS = (
    "uid nome: kosmos.name kosmos_id: kosmos.id conceito: kosmos.conceptType "
    "status: kosmos.status version: kosmos.version tipo: kosmos.fieldType "
    "pred: kosmos.fieldPredicate apelido: kosmos.nickname "
    "dominio: kosmos.instanceOf { uid nome: kosmos.name kosmos_id: kosmos.id } "
    "relacao: kosmos.relationType { uid } "
    f"sujeito: kosmos.subject {{ {INSTANCIA_FIELDS} }} "
    "alvos: kosmos.selectorTarget { uid } "
    "dono: ~kosmos.hasField { uid nome: kosmos.name conceito: kosmos.conceptType "
    "version: kosmos.version }"
)
CAMPO_FIELDS = (
    "uid nome: kosmos.name tipo: kosmos.fieldType pred: kosmos.fieldPredicate "
    "alvos: kosmos.selectorTarget { uid nome: kosmos.name "
    "total: count(~kosmos.instanceOf) }"
)

# The trigram index (for search as you type) is added the first time this
# process searches; it only adds to the nickname's existing indexes.
_search_ready = False


def ascii_name(nome: str, limit: int | None = None) -> str:
    plain = (
        unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_")[:limit]


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_kosmos_id() -> tuple[str, str]:
    uuid = str(uuid4())
    return f"_:{uuid}", uuid[:8]


def short(concept: dict[str, Any]) -> str:
    """The 8 hex the source system derives names from."""
    kosmos_id = concept.get("kosmos_id") or ""
    return (
        kosmos_id[2:10]
        if kosmos_id.startswith("_:")
        else concept["uid"][2:].zfill(8)[-8:]
    )


def clean(node: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if v is not None}


def field_error(name: str, detail: str) -> APIError:
    return validation_error(
        detail, fields=[FieldError(name=name, detail=detail)]
    )


def ordered(campos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(campos, key=lambda c: c.get("ordem", 0))


class KosmosWriteRepository(KosmosRepository):
    async def get_concept(self, id_: int) -> dict[str, Any] | None:
        """Any kosmos node: domain, field, relation type, instance, relation."""
        data = await self.context.query(
            f"query c($id: string) {{ c(func: uid($id)) {{ {CONCEPT_FIELDS} }} }}",
            id=hex(id_),
        )
        row = data["c"][0] if data["c"] else None
        # uid() echoes any uid back: a node without predicates does not exist.
        return row if row and len(row) > 1 else None

    async def get_relationship(self, id_: int) -> dict[str, Any]:
        found = await self.get_concept(id_)
        if not found or found.get("conceito") != RELATIONSHIP:
            raise does_not_exist(f"Tipo de relação {id_}")
        return found

    async def campos(self, dono: str) -> list[dict[str, Any]]:
        """Active fields of a domain or relation type, in form order."""
        data = await self.query(
            f"{{ d(func: uid({dono})) {{ kosmos.hasField "
            "@facets(ordem: order, obrigatorio: required) "
            f"{ATIVO} {{ {CAMPO_FIELDS} }} }} }}"
        )
        rows = data["d"][0].get("kosmos.hasField", []) if data["d"] else []
        return ordered(rows)

    async def aceitos(
        self, campo: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """Domains a selector accepts; None means any.

        An abstract target (Persona) has no instances of its own, and the
        model does not say who satisfies it, so the data does: the domains
        already used in this field. A field with no data yet accepts any.
        """
        if campo.get("tipo") != SELECTOR:
            return None
        alvos = campo.get("alvos", [])
        concretos = [a for a in alvos if a.get("total")]
        if len(concretos) == len(alvos):
            return concretos
        pred = campo["pred"]
        data = await self.query(
            f"{{ var(func: has({pred})) {{ v as {pred} }} "
            "var(func: uid(v)) { d as kosmos.instanceOf } "
            "n(func: uid(d)) { uid nome: kosmos.name } }"
        )
        return (concretos + data["n"]) if data["n"] else None

    async def _instance_type(self, dono: dict[str, Any]) -> str:
        """Dgraph type of the dono's instances (or reified relations)."""
        reverse = (
            "~kosmos.relationType"
            if dono.get("conceito") == RELATIONSHIP
            else "~kosmos.instanceOf"
        )
        data = await self.query(
            f"{{ t(func: uid({dono['uid']})) {{ i: {reverse} (first: 1) "
            "{ dgraph.type } } }"
        )
        types = [
            t
            for row in data["t"]
            for i in row.get("i", [])
            for t in i.get("dgraph.type", [])
            if t != "kosmos.Relationship"
        ]
        return types[0] if types else f"kosmos.{ascii_name(dono['nome'])}"

    async def _type_fields(self, name: str) -> list[str]:
        data = await self.context.query(f"schema(type: [{name}]) {{}}")
        types = data.get("types") or []
        return [f["name"] for f in types[0]["fields"]] if types else []

    async def _extend_type(self, name: str, predicates: list[str]) -> None:
        fields = await self._type_fields(name) or list(INSTANCE_FIELDS)
        await self.alter(
            type_ddl(name, fields + [p for p in predicates if p not in fields])
        )

    async def _unique(
        self, nome: str, conceito: str, skip: str | None = None
    ) -> None:
        data = await self.query(
            "query u($nome: string) { u(func: eq(kosmos.name, $nome)) "
            f'@filter(eq(kosmos.conceptType, "{conceito}")) {{ uid }} }}',
            nome=nome,
        )
        if any(row["uid"] != skip for row in data["u"]):
            raise field_error(
                "nome", f"Já existe um {CONCEPT_NODE[conceito]} {nome}"
            )

    def _concept_node(
        self, kid: str, nome: str, conceito: str, now: str, **extra: Any
    ) -> dict[str, Any]:
        prefix = {DOMAIN: "domain", RELATIONSHIP: "relationship"}.get(
            conceito, "field"
        )
        return clean(
            {
                "dgraph.type": "kosmos.Concept",
                "kosmos.id": kid,
                "kosmos.name": nome,
                "kosmos.apiName": [f"{prefix}:{ascii_name(nome).lower()}"],
                "kosmos.conceptType": conceito,
                "kosmos.status": StatusConcept.ACTIVE,
                "kosmos.version": 1,
                "kosmos.createdAt": now,
                "kosmos.updatedAt": now,
            }
            | extra
        )

    def _node_id(self, found: dict[str, Any]) -> str | None:
        """Graph node that shows ``found`` once written."""
        k = key(found["uid"])
        if found.get("relacao"):
            sujeito = found.get("sujeito") or {}
            return (
                node_id(dominio_of(sujeito), key(sujeito["uid"]))
                if sujeito
                else None
            )
        if found.get("dominio"):
            return node_id(found["dominio"]["nome"], k)
        if found.get("conceito") == ConceptTypeConcept.FIELD:
            dono = (found.get("dono") or [None])[0]
            return self._node_id(dono) if dono else None
        conceito = CONCEPT_NODE.get(found.get("conceito", ""))
        return node_id(conceito, k) if conceito else None

    # Domains --------------------------------------------------------------

    async def create_dominio(self, payload: DominioInputSchema) -> WriteSchema:
        await self._unique(payload.nome, DOMAIN)
        base = ascii_name(payload.nome)
        if not base:
            raise field_error("nome", "O nome precisa de letras ou números")
        type_name = f"kosmos.{base}"
        if await self._type_fields(type_name):
            raise field_error("nome", f"O type {type_name} já existe no schema")
        kid, _ = new_kosmos_id()
        await self.alter(type_ddl(type_name, INSTANCE_FIELDS))
        node = self._concept_node(
            kid,
            payload.nome,
            DOMAIN,
            stamp(),
            **{
                "uid": "_:dominio",
                "kosmos.description": payload.descricao,
                "kosmos.category": payload.categoria,
            },
        )
        uids = await self.mutate({"set": [node]})
        k = key(uids["dominio"]) if "dominio" in uids else None
        return self.written(node_id(DOMINIO, k) if k else None, k)

    async def update_concept(
        self, found: dict[str, Any], payload: DominioUpdateSchema
    ) -> WriteSchema:
        """Renames or redescribes a domain or relation type."""
        if payload.nome is not None and payload.nome != found["nome"]:
            await self._unique(
                payload.nome, found["conceito"], skip=found["uid"]
            )
        changes = clean(
            {
                "kosmos.name": payload.nome,
                "kosmos.category": payload.categoria,
                "kosmos.description": payload.descricao,
            }
        )
        if changes:
            await self.mutate({"set": [self._bump(found) | changes]})
        return self.written(self._node_id(found), key(found["uid"]))

    def _bump(self, found: dict[str, Any]) -> dict[str, Any]:
        return {
            "uid": found["uid"],
            "kosmos.version": (found.get("version") or 0) + 1,
            "kosmos.updatedAt": stamp(),
        }

    # Fields ---------------------------------------------------------------

    async def _alvo(
        self, alvo_id: int | None, tipo: FieldTypeConcept
    ) -> dict[str, Any] | None:
        if tipo != SELECTOR:
            if alvo_id is not None:
                raise field_error(
                    "alvo_id", "Só seletores apontam para um domínio"
                )
            return None
        if alvo_id is None:
            raise field_error(
                "alvo_id", "Escolha o domínio para onde o seletor aponta"
            )
        alvo = await self.get_concept(alvo_id)
        if not alvo or alvo.get("conceito") != DOMAIN:
            raise field_error("alvo_id", f"{alvo_id} não é um domínio")
        return alvo

    async def create_campo(
        self, dono: dict[str, Any], payload: CampoInputSchema
    ) -> WriteSchema:
        alvo = await self._alvo(payload.alvo_id, payload.tipo)
        campos = await self.campos(dono["uid"])
        if any(c["nome"].casefold() == payload.nome.casefold() for c in campos):
            raise field_error(
                "nome", f"{dono['nome']} já tem o campo {payload.nome}"
            )
        base = ascii_name(payload.nome, 40)
        if not base:
            raise field_error("nome", "O nome precisa de letras ou números")
        kid, short8 = new_kosmos_id()
        pred = f"kosmos.{base}_{short8}"
        await self.alter(f"{pred}: {PREDICATE_SCHEMA[payload.tipo]} .")
        await self._extend_type(await self._instance_type(dono), [pred])
        now = stamp()
        campo = self._concept_node(
            kid,
            payload.nome,
            ConceptTypeConcept.FIELD,
            now,
            **{
                "uid": "_:campo",
                "kosmos.fieldType": payload.tipo,
                "kosmos.fieldPredicate": pred,
                "kosmos.category": "Estrutural",
                "kosmos.selectorTarget": [{"uid": alvo["uid"]}]
                if alvo
                else None,
            },
        )
        ordem = max((c.get("ordem", 0) for c in campos), default=-1) + 1
        await self.mutate(
            {
                "set": [
                    campo,
                    self._bump(dono)
                    | {
                        "kosmos.hasField": [
                            {
                                "uid": "_:campo",
                                "kosmos.hasField|order": ordem,
                                "kosmos.hasField|required": payload.obrigatorio,
                            }
                        ]
                    },
                ]
            }
        )
        return self.written(self._node_id(dono), key(dono["uid"]))

    async def update_campo(
        self, campo: dict[str, Any], payload: CampoUpdateSchema
    ) -> WriteSchema:
        dono = (campo.get("dono") or [None])[0]
        if dono is None:
            raise does_not_exist(f"Dono do campo {campo['nome']}")
        irmaos = await self.campos(dono["uid"])
        atual = next((c for c in irmaos if c["uid"] == campo["uid"]), {})
        changes: dict[str, Any] = {}
        deletes: list[dict[str, Any]] = []
        if payload.nome is not None and payload.nome != campo["nome"]:
            if any(
                c["nome"].casefold() == payload.nome.casefold()
                for c in irmaos
                if c["uid"] != campo["uid"]
            ):
                raise field_error(
                    "nome", f"{dono['nome']} já tem o campo {payload.nome}"
                )
            changes["kosmos.name"] = payload.nome
        tipo = payload.tipo or FieldTypeConcept(campo.get("tipo", "text"))
        if payload.tipo is not None and payload.tipo != campo.get("tipo"):
            valores = await self.query(
                f"{{ v(func: has({campo['pred']})) {{ total: count(uid) }} }}"
            )
            total = valores["v"][0]["total"] if valores["v"] else 0
            if total:
                raise conflict(
                    f"{campo['pred']} já tem {total} valores",
                    "Mudar o tipo de um predicado com dados é bloqueado: os "
                    "valores atuais não cabem no tipo novo.",
                )
            await self.alter(
                f"{campo['pred']}: {PREDICATE_SCHEMA[payload.tipo]} ."
            )
            changes["kosmos.fieldType"] = payload.tipo
            if payload.tipo != SELECTOR:
                deletes.append(
                    {"uid": campo["uid"], "kosmos.selectorTarget": None}
                )
        if payload.alvo_id is not None or (
            payload.tipo == SELECTOR and payload.tipo != campo.get("tipo")
        ):
            alvo = await self._alvo(payload.alvo_id, tipo)
            deletes.append({"uid": campo["uid"], "kosmos.selectorTarget": None})
            changes["kosmos.selectorTarget"] = (
                [{"uid": alvo["uid"]}] if alvo else None
            )
        sets = []
        if changes:
            sets.append(self._bump(campo) | clean(changes))
        if payload.obrigatorio is not None:
            sets.append(
                {
                    "uid": dono["uid"],
                    "kosmos.hasField": [
                        {
                            "uid": campo["uid"],
                            "kosmos.hasField|order": atual.get("ordem", 0),
                            "kosmos.hasField|required": payload.obrigatorio,
                        }
                    ],
                }
            )
        mutations = ([{"delete": deletes}] if deletes else []) + (
            [{"set": sets}] if sets else []
        )
        if mutations:
            await self.mutate(*mutations)
        return self.written(self._node_id(dono), key(dono["uid"]))

    # Instances ------------------------------------------------------------

    async def _valores(
        self,
        campos: list[dict[str, Any]],
        valores: dict[int, Any],
        creating: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        """Validated predicate values to set, and predicates to clear."""
        by_id = {key(c["uid"]): c for c in campos}
        errors: list[FieldError] = []
        sets: dict[str, Any] = {}
        clears: list[str] = []
        selecionados: dict[str, list[int]] = {}

        def fail(id_: int, detail: str) -> None:
            errors.append(FieldError(name=f"valores.{id_}", detail=detail))

        for id_ in valores.keys() - by_id.keys():
            fail(id_, "Este campo não pertence ao domínio")
        for id_, campo in by_id.items():
            raw = valores.get(id_)
            vazio = raw is None or raw == "" or raw == []
            if vazio:
                if creating and campo.get("obrigatorio"):
                    fail(id_, "Obrigatório")
                elif not creating and id_ in valores:
                    clears.append(campo["pred"])
                continue
            tipo = campo.get("tipo")
            try:
                match tipo:
                    case "text":
                        sets[campo["pred"]] = str(raw).strip()
                    case "number" | "percentage":
                        sets[campo["pred"]] = float(raw)
                    case "date":
                        day = date.fromisoformat(str(raw)[:10])
                        sets[campo["pred"]] = f"{day.isoformat()}T00:00:00Z"
                    case "boolean":
                        if not isinstance(raw, bool):
                            raise TypeError
                        sets[campo["pred"]] = raw
                    case "selector":
                        ids = raw if isinstance(raw, list) else [raw]
                        selecionados[campo["pred"]] = [int(i) for i in ids]
                    case _:
                        fail(id_, "Calculado pelo sistema de origem")
            except TypeError, ValueError:
                fail(
                    id_,
                    {"date": "Data inválida", "boolean": "Use sim ou não"}.get(
                        tipo or "", "Número inválido"
                    ),
                )

        if selecionados:
            todos = sorted({i for ids in selecionados.values() for i in ids})
            data = await self.query(
                f"{{ v(func: uid({', '.join(hex(i) for i in todos)})) "
                "{ uid d: kosmos.instanceOf { uid } } }"
            )
            dominio = {
                key(row["uid"]): row.get("d", {}).get("uid")
                for row in data["v"]
            }
            for campo in campos:
                ids = selecionados.get(campo["pred"])
                if ids is None:
                    continue
                aceitos = await self.aceitos(campo)
                uids = {a["uid"] for a in aceitos or []}
                for i in ids:
                    if dominio.get(i) is None:
                        fail(key(campo["uid"]), f"{i} não é uma instância")
                    elif aceitos is not None and dominio[i] not in uids:
                        nomes = ", ".join(a["nome"] for a in aceitos)
                        fail(key(campo["uid"]), f"{i} não é de {nomes}")
                sets[campo["pred"]] = [{"uid": hex(i)} for i in ids]
                if not creating:
                    clears.append(campo["pred"])
        if errors:
            raise validation_error("Valores inválidos", fields=errors)
        return sets, clears

    def _apelido(
        self,
        campos: list[dict[str, Any]],
        sets: dict[str, Any],
        apelido: str | None,
    ) -> str | None:
        """The source system shows the first text field as the nickname."""
        if apelido:
            return apelido
        for campo in campos:
            if campo.get("tipo") == "text" and campo["pred"] in sets:
                return sets[campo["pred"]]
        return None

    async def create_instancia(
        self, dominio: dict[str, Any], payload: InstanciaInputSchema
    ) -> WriteSchema:
        campos = await self.campos(dominio["uid"])
        sets, _ = await self._valores(campos, payload.valores, creating=True)
        apelido = self._apelido(campos, sets, payload.apelido)
        if not apelido:
            raise field_error(
                "apelido", "Dê um apelido ou preencha um campo de texto"
            )
        kid, _ = new_kosmos_id()
        now = stamp()
        ms = int(datetime.now(UTC).timestamp() * 1000)
        node = {
            "uid": "_:instancia",
            "dgraph.type": await self._instance_type(dominio),
            "kosmos.id": kid,
            "kosmos.name": f"DOM_{short(dominio)}_{ms}_0",
            "kosmos.nickname": apelido,
            "kosmos.instanceOf": {"uid": dominio["uid"]},
            "kosmos.status": StatusConcept.ACTIVE,
            "kosmos.version": 1,
            "kosmos.createdAt": now,
            "kosmos.updatedAt": now,
        } | sets
        uids = await self.mutate({"set": [node]})
        k = key(uids["instancia"]) if "instancia" in uids else None
        return self.written(node_id(dominio["nome"], k) if k else None, k)

    async def update_instancia(
        self, instancia: dict[str, Any], payload: InstanciaUpdateSchema
    ) -> WriteSchema:
        atual = instancia.get("version") or 1
        if payload.version != atual:
            raise conflict(
                "A instância mudou desde que você abriu",
                f"Você editou a versão {payload.version}; a atual é {atual}.",
            )
        campos = await self.campos(instancia["dominio"]["uid"])
        sets, clears = await self._valores(
            campos, payload.valores, creating=False
        )
        mutations: list[dict[str, Any]] = []
        if clears:
            mutations.append(
                {"delete": [{"uid": instancia["uid"], p: None} for p in clears]}
            )
        changes = sets | clean({"kosmos.nickname": payload.apelido})
        if changes or clears:
            mutations.append({"set": [self._bump(instancia) | changes]})
            await self.mutate(*mutations)
        return self.written(self._node_id(instancia), key(instancia["uid"]))

    async def fetch_formulario(
        self, dominio: dict[str, Any], instancia: dict[str, Any] | None = None
    ) -> FormularioSchema:
        campos = await self.campos(dominio["uid"])
        valores: dict[str, Any] = {}
        if instancia and campos:
            blocks = " ".join(
                f"s{i}: {c['pred']} {{ uid apelido: kosmos.nickname nome: kosmos.name }}"
                if c.get("tipo") == SELECTOR
                else f"e{i}: {c['pred']}"
                for i, c in enumerate(campos)
            )
            data = await self.query(
                f"{{ i(func: uid({instancia['uid']})) {{ {blocks} }} }}"
            )
            row = data["i"][0] if data["i"] else {}
            for i, campo in enumerate(campos):
                if f"e{i}" in row:
                    valores[campo["uid"]] = row[f"e{i}"]
                elif f"s{i}" in row:
                    alvos = row[f"s{i}"]
                    valores[campo["uid"]] = [
                        {"id": key(a["uid"]), "nome": label(a)}
                        for a in (alvos if isinstance(alvos, list) else [alvos])
                    ]
        return FormularioSchema(
            dominio=RefSchema(id=key(dominio["uid"]), nome=dominio["nome"]),
            campos=[
                await self._campo_form(c, valores.get(c["uid"])) for c in campos
            ],
            apelido=label(instancia) if instancia else None,
            version=(instancia.get("version") or 1) if instancia else None,
        )

    async def _campo_form(
        self, campo: dict[str, Any], valor: Any = None
    ) -> CampoFormSchema:
        aceitos = await self.aceitos(campo)
        return CampoFormSchema(
            id=key(campo["uid"]),
            nome=campo["nome"],
            tipo=campo.get("tipo", "text"),
            obrigatorio=bool(campo.get("obrigatorio")),
            ordem=campo.get("ordem", 0),
            alvos=[
                AlvoSchema(
                    id=key(a["uid"]),
                    nome=a["nome"],
                    abstrato=not a.get("total"),
                )
                for a in campo.get("alvos", [])
            ],
            aceitos=None
            if aceitos is None
            else [RefSchema(id=key(a["uid"]), nome=a["nome"]) for a in aceitos],
            valor=valor,
        )

    # Relations ------------------------------------------------------------

    async def fetch_tipos_relacao(self) -> list[TipoRelacaoSchema]:
        data = await self.query(
            f'{{ r(func: eq(kosmos.conceptType, "{RELATIONSHIP}"), '
            f"orderasc: kosmos.name) {ATIVO} {{ uid nome: kosmos.name kosmos.hasField "
            "@facets(ordem: order, obrigatorio: required) "
            f'@filter(eq(kosmos.fieldType, "{SELECTOR}") AND NOT eq(kosmos.status, '
            f'"inactive")) {{ {CAMPO_FIELDS} }} }} }}'
        )
        return [
            TipoRelacaoSchema(
                id=key(r["uid"]),
                nome=r["nome"],
                campos=[
                    await self._campo_form(c)
                    for c in ordered(r.get("kosmos.hasField", []))
                ],
            )
            for r in data["r"]
        ]

    async def create_tipo_relacao(
        self, payload: TipoRelacaoInputSchema
    ) -> WriteSchema:
        await self._unique(payload.nome, RELATIONSHIP)
        lados = []
        for name, id_ in (
            ("sujeito_id", payload.sujeito_id),
            ("objeto_id", payload.objeto_id),
        ):
            found = await self.get_concept(id_)
            if not found or found.get("conceito") != DOMAIN:
                raise field_error(name, f"{id_} não é um domínio")
            lados.append(found)
        sujeito, objeto = lados
        nomes = [sujeito["nome"], objeto["nome"]]
        if nomes[0] == nomes[1]:
            nomes = [f"{nomes[0]} (sujeito)", f"{nomes[1]} (objeto)"]
        base = ascii_name(payload.nome)
        if not base:
            raise field_error("nome", "O nome precisa de letras ou números")
        now = stamp()
        kid, _ = new_kosmos_id()
        campos, preds, edges = [], [], []
        for ordem, (nome, alvo) in enumerate(zip(nomes, lados, strict=True)):
            campo_kid, short8 = new_kosmos_id()
            pred = f"kosmos.{ascii_name(nome, 40)}_{short8}"
            preds.append(pred)
            campos.append(
                self._concept_node(
                    campo_kid,
                    nome,
                    ConceptTypeConcept.FIELD,
                    now,
                    **{
                        "uid": f"_:campo{ordem}",
                        "kosmos.fieldType": SELECTOR,
                        "kosmos.fieldPredicate": pred,
                        "kosmos.category": "Estrutural",
                        "kosmos.selectorTarget": [{"uid": alvo["uid"]}],
                    },
                )
            )
            edges.append(
                {
                    "uid": f"_:campo{ordem}",
                    "kosmos.hasField|order": ordem,
                    "kosmos.hasField|required": True,
                }
            )
        await self.alter(
            "\n".join(f"{p}: {PREDICATE_SCHEMA[SELECTOR]} ." for p in preds)
        )
        await self._extend_type(f"kosmos.{base}", preds)
        tipo = self._concept_node(
            kid,
            payload.nome,
            RELATIONSHIP,
            now,
            **{
                "uid": "_:tipo",
                "kosmos.description": payload.descricao,
                "kosmos.category": payload.categoria,
                "kosmos.hasField": edges,
            },
        )
        uids = await self.mutate({"set": [tipo, *campos]})
        k = key(uids["tipo"]) if "tipo" in uids else None
        return self.written(node_id(TIPO_RELACAO, k) if k else None, k)

    async def create_relacao(self, payload: RelacaoInputSchema) -> WriteSchema:
        tipo = await self.get_relationship(payload.tipo_id)
        campos = [
            c
            for c in await self.campos(tipo["uid"])
            if c.get("tipo") == SELECTOR
        ]
        lados: list[tuple[dict[str, Any], dict[str, Any]]] = []
        usados: set[str] = set()
        for name, papel, id_ in (
            ("sujeito_id", "sujeito", payload.sujeito_id),
            ("objeto_id", "objeto", payload.objeto_id),
        ):
            found = await self.get_concept(id_)
            if not found or not found.get("dominio"):
                raise field_error(name, f"{id_} não é uma instância")
            dominio = found["dominio"]["uid"]
            campo = None
            for c in campos:
                if c["uid"] in usados:
                    continue
                aceitos = await self.aceitos(c)
                if aceitos is None or dominio in {a["uid"] for a in aceitos}:
                    campo = c
                    break
            if campo is None:
                raise field_error(
                    name,
                    f"{tipo['nome']} não aceita {found['dominio']['nome']} como {papel}",
                )
            usados.add(campo["uid"])
            lados.append((found, campo))
        (sujeito, campo_s), (objeto, campo_o) = lados
        completo = all(
            c["uid"] in usados for c in campos if c.get("obrigatorio")
        )
        now = stamp()
        kid, _ = new_kosmos_id()
        ms = int(datetime.now(UTC).timestamp() * 1000)
        await self.mutate(
            {
                "set": [
                    {
                        "uid": "_:relacao",
                        "dgraph.type": [
                            await self._instance_type(tipo),
                            "kosmos.Relationship",
                        ],
                        "kosmos.id": kid,
                        "kosmos.name": f"REL_{short(tipo)}_{ms}_0",
                        "kosmos.nickname": f"{label(sujeito)} | {label(objeto)}",
                        "kosmos.subject": {"uid": sujeito["uid"]},
                        "kosmos.object": {"uid": objeto["uid"]},
                        "kosmos.relationType": {"uid": tipo["uid"]},
                        "kosmos.completionStatus": "complete"
                        if completo
                        else "incomplete",
                        "kosmos.status": StatusConcept.ACTIVE,
                        "kosmos.version": 1,
                        "kosmos.createdAt": now,
                        "kosmos.updatedAt": now,
                        campo_s["pred"]: [{"uid": sujeito["uid"]}],
                        campo_o["pred"]: [{"uid": objeto["uid"]}],
                    }
                ]
            }
        )
        return self.written(self._node_id(sujeito), key(sujeito["uid"]))

    # Status ---------------------------------------------------------------

    async def impacto(self, found: dict[str, Any]) -> dict[str, int]:
        uid = found["uid"]
        conceito = found.get("conceito")
        if found.get("relacao"):
            return {}
        if found.get("dominio"):
            counts = "a: count(~kosmos.subject) b: count(~kosmos.object)"
        elif conceito == DOMAIN:
            counts = "instancias: count(~kosmos.instanceOf)"
        elif conceito == RELATIONSHIP:
            counts = "relacoes: count(~kosmos.relationType)"
        else:
            data = await self.query(
                f"{{ v(func: has({found['pred']})) {{ valores: count(uid) }} }}"
            )
            return {
                k: v
                for k, v in (data["v"][0] if data["v"] else {}).items()
                if v
            }
        data = await self.query(f"{{ v(func: uid({uid})) {{ {counts} }} }}")
        row = data["v"][0] if data["v"] else {}
        if "a" in row or "b" in row:
            row = {"relacoes": row.get("a", 0) + row.get("b", 0)}
        return {k: v for k, v in row.items() if v}

    async def set_status(
        self, found: dict[str, Any], status: StatusConcept, path: str
    ) -> WriteSchema:
        previous = found.get("status") or StatusConcept.ACTIVE
        impacto = (
            await self.impacto(found)
            if status == StatusConcept.INACTIVE
            else {}
        )
        await self.mutate(
            {"set": [self._bump(found) | {"kosmos.status": status}]}
        )
        return self.written(
            self._node_id(found),
            key(found["uid"]),
            impacto=impacto,
            desfazer=UndoSchema(
                method="PUT", path=path, body={"status": previous}
            ),
        )

    async def fetch_inativos(self) -> GraphSchema[InativoSchema]:
        data = await self.query(
            '{ v(func: eq(kosmos.status, "inactive"), first: 200) { '
            "uid nome: kosmos.name apelido: kosmos.nickname "
            "conceito: kosmos.conceptType "
            "dominio: kosmos.instanceOf { nome: kosmos.name } "
            f"sujeito: kosmos.subject {{ {INSTANCIA_FIELDS} }} "
            f"objeto: kosmos.object {{ {INSTANCIA_FIELDS} }} "
            "relacao: kosmos.relationType { nome: kosmos.name } } }"
        )
        graph = GraphBuilder()
        items: list[InativoSchema] = []
        for row in data["v"]:
            k = key(row["uid"])
            if row.get("relacao"):
                if not (row.get("sujeito") and row.get("objeto")):
                    continue
                graph.edge(
                    self._instancia(graph, row["sujeito"]),
                    self._instancia(graph, row["objeto"]),
                    row["relacao"]["nome"],
                )
                items.append(
                    InativoSchema(
                        tipo="Relação",
                        id=k,
                        nome=f"{row['relacao']['nome']}: {label(row['sujeito'])} | "
                        f"{label(row['objeto'])}",
                        relacao_id=k,
                    )
                )
                continue
            tipo = (
                row["dominio"]["nome"]
                if row.get("dominio")
                else CONCEPT_NODE.get(row.get("conceito", ""), "Conceito")
            )
            graph.node(
                tipo, k, label(row), "result", status=StatusConcept.INACTIVE
            )
            items.append(InativoSchema(tipo=tipo, id=k, nome=label(row)))
        return graph.build(self.queries, items)

    async def fetch_busca(
        self, q: str, tipo: str, dominio_id: int | None
    ) -> list[BuscaSchema]:
        termo = q.strip()
        if tipo == "dominio":
            data = await self.query(
                f'{{ d(func: eq(kosmos.conceptType, "{DOMAIN}")) {ATIVO} '
                "{ uid nome: kosmos.name } }"
            )
            found = [
                d for d in data["d"] if termo.casefold() in d["nome"].casefold()
            ]
            found.sort(
                key=lambda d: (
                    not d["nome"].casefold().startswith(termo.casefold()),
                    d["nome"],
                )
            )
            return [
                BuscaSchema(id=key(d["uid"]), nome=d["nome"], dominio="Dominio")
                for d in found[:20]
            ]
        filtro = 'has(kosmos.instanceOf) AND NOT eq(kosmos.status, "inactive")'
        if dominio_id is not None:
            filtro += f" AND uid_in(kosmos.instanceOf, {hex(dominio_id)})"
        if len(termo) >= 3:
            await self._ensure_search()
            pattern = re.escape(termo).replace("/", "\\/")
            root = f"regexp(kosmos.nickname, /{pattern}/i), first: 20"
        elif dominio_id is not None:
            root = f"uid({hex(dominio_id)})"
            data = await self.query(
                f"{{ v(func: {root}) {{ i: ~kosmos.instanceOf (orderasc: kosmos.nickname, "
                f"first: 20) {ATIVO} {{ {INSTANCIA_FIELDS} }} }} }}"
            )
            rows = data["v"][0].get("i", []) if data["v"] else []
            return [
                BuscaSchema(
                    id=key(r["uid"]), nome=label(r), dominio=dominio_of(r)
                )
                for r in rows
            ]
        else:
            return []
        data = await self.query(
            f"{{ v(func: {root}) @filter({filtro}) {{ {INSTANCIA_FIELDS} }} }}"
        )
        return [
            BuscaSchema(id=key(r["uid"]), nome=label(r), dominio=dominio_of(r))
            for r in data["v"]
        ]

    async def _ensure_search(self) -> None:
        global _search_ready
        if not _search_ready:
            await self.context.alter(
                "kosmos.nickname: string @index(term, exact, trigram) ."
            )
            _search_ready = True
