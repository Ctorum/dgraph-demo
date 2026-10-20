from typing import Annotated

from fastapi import APIRouter, Query

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema

from .domain import RecommendProdutosUseCase, RecommendUsuariosUseCase
from .schemas import RecomendacaoSchema

router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/usuarios/{usuario_id}/produtos")
async def recommend_produtos(
    usuario_id: int, context: GraphContext, limit: Limit = 10
) -> BaseResponseSchema[GraphSchema[RecomendacaoSchema]]:
    return await RecommendProdutosUseCase(
        context=context, usuario_id=usuario_id, limit=limit
    ).execute()


@router.get("/usuarios/{usuario_id}/seguir")
async def recommend_usuarios(
    usuario_id: int, context: GraphContext, limit: Limit = 10
) -> BaseResponseSchema[GraphSchema[RecomendacaoSchema]]:
    return await RecommendUsuariosUseCase(
        context=context, usuario_id=usuario_id, limit=limit
    ).execute()
