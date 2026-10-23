import zlib
from typing import Any

from app.api.exc.exceptions import (
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
    UndoSchema,
    WriteSchema,
    node_id,
)

from .concepts import HIDDEN, PROTECTED, TOKENIZERS, VertexConcept
from .schemas import PredicadoSchema, SchemaRowSchema, TipoInputSchema

TIPO = VertexConcept.TIPO
PREDICADO = VertexConcept.PREDICADO


def key(name: str) -> int:
    """Types and predicates have no uid: a stable number from the name."""
    return zlib.crc32(name.encode()) & 0x7FFFFFFF


def dgraph_type(pred: dict[str, Any]) -> str:
    return f"[{pred['type']}]" if pred.get("list") else pred["type"]


def ddl(pred: PredicadoSchema) -> str:
    tipo = f"[{pred.tipo}]" if pred.lista else pred.tipo
    index = f" @index({', '.join(pred.indices)})" if pred.indices else ""
    reverse = " @reverse" if pred.reverse else ""
    return f"{pred.nome}: {tipo}{index}{reverse} ."


def as_input(pred: dict[str, Any]) -> PredicadoSchema:
    return PredicadoSchema(
        nome=pred["predicate"],
        tipo=pred["type"],
        lista=bool(pred.get("list")),
        indices=pred.get("tokenizer", []),
        reverse=bool(pred.get("reverse")),
    )


class SchemaRepository(GraphRepository):
    def __init__(self, context: DgraphClient, dry_run: bool = False):
        super().__init__(context=context, dry_run=dry_run)

    async def _schema(self) -> tuple[dict[str, list[str]], dict[str, dict]]:
        data = await self.query("schema {}")
        types = {
            t["name"]: [f["name"] for f in t["fields"]] for t in data["types"]
        }
        preds = {p["predicate"]: p for p in data["schema"]}
        return types, preds

    async def fetch_tipos(self) -> GraphSchema[SchemaRowSchema]:
        types, preds = await self._schema()
        graph = GraphBuilder()
        items: list[SchemaRowSchema] = []
        for name, fields in sorted(types.items()):
            if name.startswith(HIDDEN):
                continue
            tipo = graph.node(
                TIPO, key(name), name, "result", predicados=len(fields)
            )
            for field in fields:
                pred = preds.get(field, {"type": "default"})
                graph.edge(
                    tipo,
                    graph.node(
                        PREDICADO,
                        key(field),
                        field,
                        "path",
                        tipo=dgraph_type(pred),
                        indices=", ".join(pred.get("tokenizer", [])) or None,
                        reverse=pred.get("reverse") or None,
                    ),
                    "campo",
                )
                items.append(
                    SchemaRowSchema(
                        tipo=name,
                        predicado=field,
                        dgraph=dgraph_type(pred),
                        indices=pred.get("tokenizer", []),
                        reverse=bool(pred.get("reverse")),
                    )
                )
        return graph.build(self.queries, items)

    async def get_tipo(self, nome: str) -> TipoInputSchema:
        types, preds = await self._schema()
        if nome not in types:
            raise does_not_exist(f"Type {nome}")
        return TipoInputSchema(
            nome=nome,
            predicados=[as_input(preds[f]) for f in types[nome] if f in preds],
        )

    async def _validate(
        self, predicados: list[PredicadoSchema], preds: dict[str, dict]
    ) -> None:
        errors: list[FieldError] = []
        seen: set[str] = set()
        for i, pred in enumerate(predicados):

            def fail(field: str, detail: str, i: int = i) -> None:
                errors.append(
                    FieldError(name=f"predicados.{i}.{field}", detail=detail)
                )

            if pred.nome in seen:
                fail("nome", "Predicado repetido")
            seen.add(pred.nome)
            if pred.nome.startswith(PROTECTED):
                fail(
                    "nome",
                    f"{pred.nome.split('.')[0]}.* é gerido por outro módulo",
                )
            invalid = set(pred.indices) - TOKENIZERS[pred.tipo]
            if invalid:
                fail(
                    "indices",
                    f"{pred.tipo} não aceita {', '.join(sorted(invalid))}",
                )
            if pred.reverse and pred.tipo != "uid":
                fail("reverse", "Só predicados uid têm reverse")
        if errors:
            raise validation_error("Predicados inválidos", fields=errors)
        # Changing the value type of a predicate that holds data is refused:
        # the existing values would not fit.
        for pred in predicados:
            atual = preds.get(pred.nome)
            if not atual or (
                atual["type"] == pred.tipo
                and bool(atual.get("list")) == pred.lista
            ):
                continue
            data = await self.query(
                f"{{ v(func: has({pred.nome})) {{ total: count(uid) }} }}"
            )
            total = data["v"][0]["total"] if data["v"] else 0
            if total:
                raise conflict(
                    f"{pred.nome} já tem {total} valores {dgraph_type(atual)}",
                    "Mudar o tipo de um predicado com dados é bloqueado.",
                )

    async def _write(
        self, nome: str, predicados: list[PredicadoSchema]
    ) -> None:
        await self.alter(
            "\n".join(
                [
                    *(ddl(p) for p in predicados),
                    type_ddl(nome, [p.nome for p in predicados]),
                ]
            )
        )

    async def create_tipo(self, payload: TipoInputSchema) -> WriteSchema:
        if payload.nome.startswith(PROTECTED):
            raise validation_error(
                "Type protegido",
                fields=[
                    FieldError(
                        name="nome",
                        detail="dgraph.* e kosmos.* são geridos por outros módulos",
                    )
                ],
            )
        types, preds = await self._schema()
        if payload.nome in types:
            raise validation_error(
                "Type existente",
                fields=[
                    FieldError(name="nome", detail=f"{payload.nome} já existe")
                ],
            )
        await self._validate(payload.predicados, preds)
        await self._write(payload.nome, payload.predicados)
        return self.written(node_id(TIPO, key(payload.nome)), key(payload.nome))

    async def update_tipo(
        self, nome: str, predicados: list[PredicadoSchema]
    ) -> WriteSchema:
        if nome.startswith(PROTECTED):
            raise validation_error("Type protegido", detail=nome)
        anterior = await self.get_tipo(nome)
        _, preds = await self._schema()
        await self._validate(predicados, preds)
        await self._write(nome, predicados)
        return self.written(
            node_id(TIPO, key(nome)),
            key(nome),
            desfazer=UndoSchema(
                method="PUT",
                path=f"/schema/tipos/{nome}",
                body={
                    "predicados": [p.model_dump() for p in anterior.predicados]
                },
            ),
        )

    async def drop_tipo(self, nome: str) -> WriteSchema:
        """Drops the type only: predicates and data stay, so it is undoable."""
        if nome.startswith(PROTECTED):
            raise validation_error("Type protegido", detail=nome)
        anterior = await self.get_tipo(nome)
        data = await self.query(
            f"{{ v(func: type({nome})) {{ total: count(uid) }} }}"
        )
        total = data["v"][0]["total"] if data["v"] else 0
        await self.alter({"drop_op": "TYPE", "drop_value": nome})
        return self.written(
            impacto={"nos": total} if total else {},
            desfazer=UndoSchema(
                method="POST", path="/schema/tipos", body=anterior.model_dump()
            ),
        )
