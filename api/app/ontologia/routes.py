from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import GraphContext
from app.infra.graph.schemas import GraphSchema, WriteSchema

from .concepts import VertexConcept
from .domain import (
    CreateClasseUseCase,
    CreateIndividuoUseCase,
    CreateRelacaoUseCase,
    ListAncestraisClasseUseCase,
    ListInativosUseCase,
    ListIndividuosClasseUseCase,
    ListRelacoesIndividuoUseCase,
    ListTiposRelacaoUseCase,
    SearchUseCase,
    SetStatusUseCase,
    UpdateClasseUseCase,
    UpdateIndividuoUseCase,
)
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

DryRun = Annotated[bool, Query(description="Só monta a mutation, sem gravar")]

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


@router.get("/inativos")
async def list_inativos(
    context: GraphContext,
) -> BaseResponseSchema[GraphSchema[InativoSchema]]:
    return await ListInativosUseCase(context=context).execute()


@router.get("/busca")
async def search(
    context: GraphContext,
    q: Annotated[str, Query(max_length=80)] = "",
    tipo: VertexConcept = VertexConcept.CLASSE,
) -> BaseResponseSchema[list[BuscaSchema]]:
    return await SearchUseCase(context=context, q=q, tipo=tipo).execute()


@router.get("/relacoes/tipos")
async def list_tipos_relacao(
    context: GraphContext,
) -> BaseResponseSchema[list[str]]:
    return await ListTiposRelacaoUseCase(context=context).execute()


@router.post("/classes", status_code=status.HTTP_201_CREATED)
async def create_classe(
    payload: ClasseInputSchema, context: GraphContext, dry_run: DryRun = False
) -> BaseResponseSchema[WriteSchema]:
    return await CreateClasseUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.patch("/classes/{classe_id}")
async def update_classe(
    classe_id: int,
    payload: ClasseUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> BaseResponseSchema[WriteSchema]:
    return await UpdateClasseUseCase(
        context=context, dry_run=dry_run, classe_id=classe_id, payload=payload
    ).execute()


@router.post("/individuos", status_code=status.HTTP_201_CREATED)
async def create_individuo(
    payload: IndividuoInputSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> BaseResponseSchema[WriteSchema]:
    return await CreateIndividuoUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


@router.patch("/individuos/{individuo_id}")
async def update_individuo(
    individuo_id: int,
    payload: IndividuoUpdateSchema,
    context: GraphContext,
    dry_run: DryRun = False,
) -> BaseResponseSchema[WriteSchema]:
    return await UpdateIndividuoUseCase(
        context=context,
        dry_run=dry_run,
        individuo_id=individuo_id,
        payload=payload,
    ).execute()


@router.post("/relacoes", status_code=status.HTTP_201_CREATED)
async def create_relacao(
    payload: RelacaoInputSchema, context: GraphContext, dry_run: DryRun = False
) -> BaseResponseSchema[WriteSchema]:
    return await CreateRelacaoUseCase(
        context=context, dry_run=dry_run, payload=payload
    ).execute()


# Status: inactivated vertices leave every query; nothing is deleted.
_PATHS = {
    VertexConcept.CLASSE: "classes",
    VertexConcept.INDIVIDUO: "individuos",
    VertexConcept.RELACAO: "relacoes",
}


def _status_route(vertex: VertexConcept) -> None:
    path = f"/{_PATHS[vertex]}/{{id_}}/status"

    @router.put(path, name=f"set_status_{_PATHS[vertex]}")
    async def set_status(
        id_: int,
        payload: StatusInputSchema,
        context: GraphContext,
        dry_run: DryRun = False,
    ) -> BaseResponseSchema[WriteSchema]:
        return await SetStatusUseCase(
            context=context,
            dry_run=dry_run,
            vertex=vertex,
            id_=id_,
            payload=payload,
            path=f"/ontologia/{_PATHS[vertex]}/{id_}/status",
        ).execute()


for _vertex in VertexConcept:
    _status_route(_vertex)
