from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema, WriteSchema

from .repository import SchemaRepository
from .schemas import SchemaRowSchema, TipoInputSchema, TipoUpdateSchema


@dataclass
class ListTiposUseCase(ApiDomain):
    context: DgraphClient

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[SchemaRowSchema]]:
        return BaseResponseSchema(
            message="Types do schema",
            data=await SchemaRepository(self.context).fetch_tipos(),
        )


@dataclass
class GetTipoUseCase(ApiDomain):
    context: DgraphClient
    nome: str

    @override
    async def execute(self) -> BaseResponseSchema[TipoInputSchema]:
        return BaseResponseSchema(
            message="Type encontrado",
            data=await SchemaRepository(self.context).get_tipo(self.nome),
        )


@dataclass
class _WriteUseCase(ApiDomain):
    context: DgraphClient
    dry_run: bool

    @cached_property
    def repository(self) -> SchemaRepository:
        return SchemaRepository(self.context, dry_run=self.dry_run)

    def done(self, data: WriteSchema) -> BaseResponseSchema[WriteSchema]:
        return BaseResponseSchema(
            message="Prévia da escrita" if self.dry_run else "Schema alterado",
            data=data,
        )


@dataclass
class CreateTipoUseCase(_WriteUseCase):
    payload: TipoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_tipo(self.payload))


@dataclass
class UpdateTipoUseCase(_WriteUseCase):
    nome: str
    payload: TipoUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(
            await self.repository.update_tipo(
                self.nome, self.payload.predicados
            )
        )


@dataclass
class DropTipoUseCase(_WriteUseCase):
    nome: str

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.drop_tipo(self.nome))
