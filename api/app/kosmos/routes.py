from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema, WriteSchema

from .domain import (
    CreateCampoUseCase,
    CreateDominioUseCase,
    CreateInstanciaUseCase,
    CreateRelacaoUseCase,
    CreateTipoRelacaoUseCase,
    GetFormularioUseCase,
    GetMapaRelacoesUseCase,
    GetModeloDominioUseCase,
    ListConexoesInstanciaUseCase,
    ListInativosUseCase,
    ListInstanciasDominioUseCase,
    ListTiposRelacaoUseCase,
    SearchUseCase,
    SetStatusUseCase,
    UpdateCampoUseCase,
    UpdateDominioUseCase,
    UpdateInstanciaUseCase,
)
from .schemas import (
    BuscaSchema,
    CampoInputSchema,
    CampoSchema,
    CampoUpdateSchema,
    ConexaoSchema,
    DominioInputSchema,
    DominioUpdateSchema,
    FormularioSchema,
    InativoSchema,
    InstanciaInputSchema,
    InstanciaSchema,
    InstanciaUpdateSchema,
    RelacaoInputSchema,
    RelacaoMapaSchema,
    StatusInputSchema,
    TipoRelacaoInputSchema,
    TipoRelacaoSchema,
)

DryRun = Annotated[bool, Query(description="Só monta a mutation, sem gravar")]
Write = BaseResponseSchema[WriteSchema]

router = APIRouter()


@router.get("/mapa")
async def get_mapa(
    context: GraphContext,
) -> BaseResponseSchema[GraphSchema[RelacaoMapaSchema]]:
    return await GetMapaRelacoesUseCase(context=context).execute()


@router.get("/dominios/{dominio_id}/modelo")
async def get_modelo(
    dominio_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[CampoSchema]]:
    return await GetModeloDominioUseCase(
        context=context, dominio_id=dominio_id
    ).execute()


@router.get("/dominios/{dominio_id}/instancias")
async def list_instancias(
    dominio_id: int,
    context: GraphContext,
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
) -> BaseResponseSchema[GraphSchema[InstanciaSchema]]:
    return await ListInstanciasDominioUseCase(
        context=context, dominio_id=dominio_id, limit=limit
    ).execute()


@router.get("/instancias/{instancia_id}/conexoes")
async def list_conexoes(
    instancia_id: int, context: GraphContext
) -> BaseResponseSchema[GraphSchema[ConexaoSchema]]:
    return await ListConexoesInstanciaUseCase(
        context=context, instancia_id=instancia_id
    ).execute()


@router.get("/inativos")
async def list_inativos(
    context: GraphContext,
) -> BaseResponseSchema[GraphSchema[InativoSchema]]:
    return await ListInativosUseCase(context=context).execute()


@router.get("/busca")
async def search(
    context: GraphContext,
    q: Annotated[str, Query(max_length=80)] = "",
    tipo: Literal["instancia", "dominio"] = "instancia",
    dominio_id: int | None = None,
) -> BaseResponseSchema[list[BuscaSchema]]:
    return await SearchUseCase(
        context=context, q=q, tipo=tipo, dominio_id=dominio_id
    ).execute()


@router.post("/dominios", status_code=status.HTTP_201_CREATED)
async def create_dominio(
    payload: DominioInputSchema, context: GraphContext, dry_run: DryRun = False
) -> Write:
    return await CreateDominioUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.patch("/dominios/{dominio_id}")
async def update_dominio(
    dominio_id: int,
    payload: DominioUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    """Also renames relation types, which share the concept shape."""
    return await UpdateDominioUseCase(
        context=context, dry_run=dry_run, dominio_id=dominio_id, payload=payload
    ).execute()


@router.post("/dominios/{dono_id}/campos", status_code=status.HTTP_201_CREATED)
async def create_campo(
    dono_id: int,
    payload: CampoInputSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    """Adds a field to a domain or a relation type."""
    return await CreateCampoUseCase(
        context=context, dry_run=dry_run, dono_id=dono_id, payload=payload
    ).execute()


@router.patch("/campos/{campo_id}")
async def update_campo(
    campo_id: int,
    payload: CampoUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    return await UpdateCampoUseCase(
        context=context, dry_run=dry_run, campo_id=campo_id, payload=payload
    ).execute()


@router.get("/dominios/{dominio_id}/formulario")
async def get_formulario(
    dominio_id: int, context: GraphContext
) -> BaseResponseSchema[FormularioSchema]:
    return await GetFormularioUseCase(
        context=context, dry_run=True, dominio_id=dominio_id
    ).execute()


@router.post(
    "/dominios/{dominio_id}/instancias", status_code=status.HTTP_201_CREATED
)
async def create_instancia(
    dominio_id: int,
    payload: InstanciaInputSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    return await CreateInstanciaUseCase(
        context=context, dry_run=dry_run, dominio_id=dominio_id, payload=payload
    ).execute()


@router.get("/instancias/{instancia_id}/formulario")
async def get_formulario_instancia(
    instancia_id: int, context: GraphContext
) -> BaseResponseSchema[FormularioSchema]:
    return await GetFormularioUseCase(
        context=context, dry_run=True, instancia_id=instancia_id
    ).execute()


@router.patch("/instancias/{instancia_id}")
async def update_instancia(
    instancia_id: int,
    payload: InstanciaUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    return await UpdateInstanciaUseCase(
        context=context,
        dry_run=dry_run,
        instancia_id=instancia_id,
        payload=payload,
    ).execute()


@router.get("/relacoes/tipos")
async def list_tipos_relacao(
    context: GraphContext,
) -> BaseResponseSchema[list[TipoRelacaoSchema]]:
    return await ListTiposRelacaoUseCase(context=context).execute()


@router.post("/relacoes/tipos", status_code=status.HTTP_201_CREATED)
async def create_tipo_relacao(
    payload: TipoRelacaoInputSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    return await CreateTipoRelacaoUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.post("/relacoes", status_code=status.HTTP_201_CREATED)
async def create_relacao(
    payload: RelacaoInputSchema, context: GraphContext, dry_run: DryRun = False
) -> Write:
    return await CreateRelacaoUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.put("/nos/{no_id}/status")
async def set_status(
    no_id: int,
    payload: StatusInputSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> Write:
    """Inactivates or reactivates a domain, field, relation type, instance
    or relation. Inactive nodes leave every query."""
    return await SetStatusUseCase(
        context=context,
        dry_run=dry_run,
        id_=no_id,
        payload=payload,
        path=f"/kosmos/nos/{no_id}/status",
    ).execute()
