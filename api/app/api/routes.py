from typing import Any

from fastapi import APIRouter, status

from app.fraude.routes import router as fraude_router
from app.infra.graph.adapter import GraphContext
from app.kosmos.routes import router as kosmos_router
from app.ontologia.routes import router as ontologia_router
from app.recomendacao.routes import router as recomendacao_router
from app.schema.routes import router as schema_router

from .schemas import BaseResponseSchema, ErrorResponseSchema

router = APIRouter()
responses = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponseSchema},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponseSchema},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponseSchema},
}


@router.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check(
    graph: GraphContext,
) -> BaseResponseSchema[list[dict[str, Any]]]:
    return BaseResponseSchema(
        message="Service healthy", data=await graph.health()
    )


router.include_router(
    fraude_router, prefix="/fraude", tags=["Fraude"], responses=responses
)
router.include_router(
    recomendacao_router,
    prefix="/recomendacao",
    tags=["Recomendação"],
    responses=responses,
)
router.include_router(
    ontologia_router,
    prefix="/ontologia",
    tags=["Ontologia"],
    responses=responses,
)
router.include_router(
    kosmos_router, prefix="/kosmos", tags=["Kosmos"], responses=responses
)
router.include_router(
    schema_router, prefix="/schema", tags=["Schema"], responses=responses
)
