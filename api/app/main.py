from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.exc import (
    APIError,
    api_error_handler,
    pydantic_validation_error_handler,
)
from app.api.routes import router
from app.infra.graph.adapter import create_graph_adapter
from app.settings import VERSION, EnvironmentEnum, server_settings

IS_PROD = server_settings.ENVIRONMENT == EnvironmentEnum.PROD


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_graph_adapter(app):
        yield


def get_app() -> FastAPI:
    app = FastAPI(
        title="Graphs API",
        description="Casos de uso de banco de grafos sobre Dgraph",
        version=VERSION,
        openapi_url=None if IS_PROD else "/openapi.json",
        docs_url=None if IS_PROD else "/docs",
        redoc_url=None if IS_PROD else "/redoc",
        lifespan=lifespan,
    )
    app.add_exception_handler(APIError, api_error_handler)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(
        RequestValidationError,
        pydantic_validation_error_handler,  # pyright: ignore[reportArgumentType]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(router=router)
    return app


app = get_app()

if __name__ == "__main__":
    from granian.constants import Interfaces, Loops
    from granian.server import Server

    logger.info(
        f"Listening on {server_settings.SERVER_HOST}:{server_settings.SERVER_PORT}"
    )
    Server(
        "app.main:app",
        address=server_settings.SERVER_HOST,
        port=server_settings.SERVER_PORT,
        interface=Interfaces.ASGI,
        log_access=True,
        workers=server_settings.WORKERS,
        loop=Loops.uvloop,
    ).serve()
