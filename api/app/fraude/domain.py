from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.exc.exceptions import does_not_exist
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema

from .concepts import VertexConcept
from .repository import FraudeRepository
from .schemas import (
    AnelSchema,
    CicloSchema,
    ConexaoSchema,
    TransferenciaSchema,
)


@dataclass
class ListConexoesClienteUseCase(ApiDomain):
    """Clientes que compartilham dispositivo, IP ou telefone com o cliente."""

    context: DgraphClient
    cliente_id: int

    @cached_property
    def repository(self) -> FraudeRepository:
        return FraudeRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[ConexaoSchema]]:
        cliente = await self.repository.get_vertex(
            VertexConcept.CLIENTE, self.cliente_id
        )
        if cliente is None:
            raise does_not_exist(f"Cliente {self.cliente_id}")
        return BaseResponseSchema(
            message="Conexões encontradas",
            data=await self.repository.fetch_conexoes(cliente),
        )


@dataclass
class ListAneisFraudeUseCase(ApiDomain):
    """Identificadores usados por muitos clientes ao mesmo tempo."""

    context: DgraphClient
    min_clientes: int

    @cached_property
    def repository(self) -> FraudeRepository:
        return FraudeRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[AnelSchema]]:
        return BaseResponseSchema(
            message="Anéis encontrados",
            data=await self.repository.fetch_aneis(self.min_clientes),
        )


@dataclass
class ListCiclosContaUseCase(ApiDomain):
    """Dinheiro que sai da conta e volta a ela em 3 transferências."""

    context: DgraphClient
    conta_id: int

    @cached_property
    def repository(self) -> FraudeRepository:
        return FraudeRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[CicloSchema]]:
        if not await self.repository.get_vertex(
            VertexConcept.CONTA, self.conta_id
        ):
            raise does_not_exist(f"Conta {self.conta_id}")
        return BaseResponseSchema(
            message="Ciclos encontrados",
            data=await self.repository.fetch_ciclos(self.conta_id),
        )


@dataclass
class ListTransferenciasSuspeitasUseCase(ApiDomain):
    context: DgraphClient
    limit: int

    @cached_property
    def repository(self) -> FraudeRepository:
        return FraudeRepository(self.context)

    @override
    async def execute(
        self,
    ) -> BaseResponseSchema[GraphSchema[TransferenciaSchema]]:
        return BaseResponseSchema(
            message="Transferências suspeitas encontradas",
            data=await self.repository.fetch_transferencias_suspeitas(
                self.limit
            ),
        )
