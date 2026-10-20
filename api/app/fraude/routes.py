from typing import Annotated

from fastapi import APIRouter, Query

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema

from .domain import (
    ListAneisFraudeUseCase,
    ListCiclosContaUseCase,
    ListConexoesClienteUseCase,
    ListTransferenciasSuspeitasUseCase,
)
from .schemas import (
    AnelSchema,
    CicloSchema,
    ConexaoSchema,
    TransferenciaSchema,
)

router = APIRouter()


@router.get("/clientes/{cliente_id}/conexoes")
async def list_conexoes_cliente(
    cliente_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[ConexaoSchema]]:
    return await ListConexoesClienteUseCase(
        context=context, cliente_id=cliente_id
    ).execute()


@router.get("/aneis")
async def list_aneis(
    context: GraphContext,
    min_clientes: Annotated[int, Query(ge=2, le=1000)] = 3,
) -> BaseResponseSchema[GraphSchema[AnelSchema]]:
    return await ListAneisFraudeUseCase(
        context=context, min_clientes=min_clientes
    ).execute()


@router.get("/contas/{conta_id}/ciclos")
async def list_ciclos_conta(
    conta_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[CicloSchema]]:
    return await ListCiclosContaUseCase(
        context=context, conta_id=conta_id
    ).execute()


@router.get("/transferencias/suspeitas")
async def list_transferencias_suspeitas(
    context: GraphContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> BaseResponseSchema[GraphSchema[TransferenciaSchema]]:
    return await ListTransferenciasSuspeitasUseCase(
        context=context, limit=limit
    ).execute()
