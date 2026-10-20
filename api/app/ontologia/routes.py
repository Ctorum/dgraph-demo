from fastapi import APIRouter

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema

from .domain import (
    ListAncestraisClasseUseCase,
    ListIndividuosClasseUseCase,
    ListRelacoesIndividuoUseCase,
)
from .schemas import AncestralSchema, IndividuoSchema, RelacaoSchema

router = APIRouter()


@router.get("/classes/{classe_id}/ancestrais")
async def list_ancestrais(
    classe_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[AncestralSchema]]:
    return await ListAncestraisClasseUseCase(
        context=context, classe_id=classe_id
    ).execute()


@router.get("/classes/{classe_id}/individuos")
async def list_individuos(
    classe_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[IndividuoSchema]]:
    return await ListIndividuosClasseUseCase(
        context=context, classe_id=classe_id
    ).execute()


@router.get("/individuos/{individuo_id}/relacoes")
async def list_relacoes(
    individuo_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[RelacaoSchema]]:
    return await ListRelacoesIndividuoUseCase(
        context=context, individuo_id=individuo_id
    ).execute()
