from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.exc.exceptions import does_not_exist
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema

from .concepts import VertexConcept
from .repository import OntologiaRepository
from .schemas import AncestralSchema, IndividuoSchema, RelacaoSchema


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
