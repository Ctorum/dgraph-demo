from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.exc.exceptions import does_not_exist
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema, WriteSchema, node_id

from .concepts import VertexConcept
from .repository import OntologiaRepository
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
    StatusInputSchema,
)


@dataclass
class ListAncestraisClasseUseCase(ApiDomain):
    context: DgraphClient
    classe_id: int

    @cached_property
    def repository(self) -> OntologiaRepository:
        return OntologiaRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[AncestralSchema]]:
        classe = await self.repository.get_vertex(
            VertexConcept.CLASSE, self.classe_id
        )
        if classe is None:
            raise does_not_exist(f"Classe {self.classe_id}")
        return BaseResponseSchema(
            message="Hierarquia encontrada",
            data=await self.repository.fetch_ancestrais(classe),
        )


@dataclass
class ListIndividuosClasseUseCase(ApiDomain):
    context: DgraphClient
    classe_id: int

    @cached_property
    def repository(self) -> OntologiaRepository:
        return OntologiaRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[IndividuoSchema]]:
        classe = await self.repository.get_vertex(
            VertexConcept.CLASSE, self.classe_id
        )
        if classe is None:
            raise does_not_exist(f"Classe {self.classe_id}")
        return BaseResponseSchema(
            message="Indivíduos encontrados",
            data=await self.repository.fetch_individuos(classe),
        )


@dataclass
class ListRelacoesIndividuoUseCase(ApiDomain):
    context: DgraphClient
    individuo_id: int

    @cached_property
    def repository(self) -> OntologiaRepository:
        return OntologiaRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[RelacaoSchema]]:
        individuo = await self.repository.get_vertex(
            VertexConcept.INDIVIDUO, self.individuo_id
        )
        if individuo is None:
            raise does_not_exist(f"Individuo {self.individuo_id}")
        return BaseResponseSchema(
            message="Relações encontradas",
            data=await self.repository.fetch_relacoes(individuo),
        )


# Writes: every use case takes ``dry_run`` and then only previews mutations.


@dataclass
class _WriteUseCase(ApiDomain):
    context: DgraphClient
    dry_run: bool

    @cached_property
    def repository(self) -> OntologiaRepository:
        return OntologiaRepository(self.context, dry_run=self.dry_run)

    async def classe(self, id_: int) -> dict:
        found = await self.repository.get_vertex(VertexConcept.CLASSE, id_)
        if found is None:
            raise does_not_exist(f"Classe {id_}")
        return found

    async def individuo(self, id_: int) -> dict:
        found = await self.repository.get_vertex(VertexConcept.INDIVIDUO, id_)
        if found is None:
            raise does_not_exist(f"Individuo {id_}")
        return found

    def done(self, data: WriteSchema) -> BaseResponseSchema[WriteSchema]:
        return BaseResponseSchema(
            message="Prévia da escrita" if self.dry_run else "Escrita aplicada",
            data=data,
        )


@dataclass
class CreateClasseUseCase(_WriteUseCase):
    payload: ClasseInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_classe(self.payload))


@dataclass
class UpdateClasseUseCase(_WriteUseCase):
    classe_id: int
    payload: ClasseUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        classe = await self.classe(self.classe_id)
        return self.done(
            await self.repository.update_classe(classe, self.payload)
        )


@dataclass
class CreateIndividuoUseCase(_WriteUseCase):
    payload: IndividuoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_individuo(self.payload))


@dataclass
class UpdateIndividuoUseCase(_WriteUseCase):
    individuo_id: int
    payload: IndividuoUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        individuo = await self.individuo(self.individuo_id)
        return self.done(
            await self.repository.update_individuo(individuo, self.payload)
        )


@dataclass
class CreateRelacaoUseCase(_WriteUseCase):
    payload: RelacaoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_relacao(self.payload))


@dataclass
class SetStatusUseCase(_WriteUseCase):
    """Inactivates or reactivates a class, individual or relation."""

    vertex: VertexConcept
    id_: int
    payload: StatusInputSchema
    path: str

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        if self.vertex == VertexConcept.RELACAO:
            found = await self.repository.get_relacao(self.id_)
            if found is None:
                raise does_not_exist(f"Relacao {self.id_}")
            origem = found.get("origem", [{}])[0].get("id")
            node = node_id(VertexConcept.INDIVIDUO, origem) if origem else None
        else:
            found = await (
                self.classe(self.id_)
                if self.vertex == VertexConcept.CLASSE
                else self.individuo(self.id_)
            )
            node = node_id(self.vertex, self.id_)
        return self.done(
            await self.repository.set_status(
                self.vertex, found, self.payload.status, node, self.path
            )
        )


@dataclass
class ListInativosUseCase(ApiDomain):
    context: DgraphClient

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[InativoSchema]]:
        return BaseResponseSchema(
            message="Inativos encontrados",
            data=await OntologiaRepository(self.context).fetch_inativos(),
        )


@dataclass
class SearchUseCase(ApiDomain):
    context: DgraphClient
    q: str
    tipo: VertexConcept

    @override
    async def execute(self) -> BaseResponseSchema[list[BuscaSchema]]:
        return BaseResponseSchema(
            message="Busca concluída",
            data=await OntologiaRepository(self.context).fetch_busca(
                self.q, self.tipo
            ),
        )


@dataclass
class ListTiposRelacaoUseCase(ApiDomain):
    context: DgraphClient

    @override
    async def execute(self) -> BaseResponseSchema[list[str]]:
        return BaseResponseSchema(
            message="Tipos de relação",
            data=await OntologiaRepository(self.context).fetch_tipos_relacao(),
        )
