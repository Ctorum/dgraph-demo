from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema, WriteSchema

from .domain import (
    CreateTipoUseCase,
    DropTipoUseCase,
    GetTipoUseCase,
    ListTiposUseCase,
    UpdateTipoUseCase,
)
from .schemas import SchemaRowSchema, TipoInputSchema, TipoUpdateSchema

router = APIRouter()
DryRun = Annotated[bool, Query(description="Só monta o DDL, sem alterar")]


@router.get("/tipos")
async def list_tipos(
    context: GraphContext,
) -> BaseResponseSchema[GraphSchema[SchemaRowSchema]]:
    return await ListTiposUseCase(context=context).execute()


@router.get("/tipos/{nome}")
async def get_tipo(
    nome: str, context: GraphContext
) -> BaseResponseSchema[TipoInputSchema]:
    return await GetTipoUseCase(context=context, nome=nome).execute()


@router.post("/tipos", status_code=status.HTTP_201_CREATED)
async def create_tipo(
    payload: TipoInputSchema, context: GraphContext, dry_run: DryRun = False
) -> BaseResponseSchema[WriteSchema]:
    return await CreateTipoUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.put("/tipos/{nome}")
async def update_tipo(
    nome: str,
    payload: TipoUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> BaseResponseSchema[WriteSchema]:
    return await UpdateTipoUseCase(
        context=context, dry_run=dry_run, nome=nome, payload=payload
    ).execute()


@router.delete("/tipos/{nome}")
async def drop_tipo(
    nome: str, context: GraphContext, dry_run: DryRun = False
) -> BaseResponseSchema[WriteSchema]:
    """Drops the type; predicates and their data stay."""
    return await DropTipoUseCase(
        context=context, dry_run=dry_run, nome=nome
    ).execute()
