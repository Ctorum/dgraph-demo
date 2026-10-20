from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.exc.exceptions import does_not_exist
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema

from .concepts import VertexConcept
from .repository import RecomendacaoRepository
from .schemas import RecomendacaoSchema


@dataclass
class RecommendProdutosUseCase(ApiDomain):
    context: DgraphClient
    usuario_id: int
    limit: int

    @cached_property
    def repository(self) -> RecomendacaoRepository:
        return RecomendacaoRepository(self.context)

    @override
    async def execute(
        self,
    ) -> BaseResponseSchema[GraphSchema[RecomendacaoSchema]]:
        usuario = await self.repository.get_vertex(
            VertexConcept.USUARIO, self.usuario_id
        )
        if usuario is None:
            raise does_not_exist(f"Usuario {self.usuario_id}")
        return BaseResponseSchema(
            message="Produtos recomendados",
            data=await self.repository.fetch_produtos(usuario, self.limit),
        )


@dataclass
class RecommendUsuariosUseCase(ApiDomain):
    context: DgraphClient
    usuario_id: int
    limit: int

    @cached_property
    def repository(self) -> RecomendacaoRepository:
        return RecomendacaoRepository(self.context)

    @override
    async def execute(
        self,
    ) -> BaseResponseSchema[GraphSchema[RecomendacaoSchema]]:
        usuario = await self.repository.get_vertex(
            VertexConcept.USUARIO, self.usuario_id
        )
        if usuario is None:
            raise does_not_exist(f"Usuario {self.usuario_id}")
        return BaseResponseSchema(
            message="Usuários sugeridos",
            data=await self.repository.fetch_usuarios_sugeridos(
                usuario, self.limit
            ),
        )
