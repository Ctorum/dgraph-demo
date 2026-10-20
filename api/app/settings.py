import tomllib
from enum import StrEnum
from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


@cache
def pyproject() -> dict:
    """Loads the pyproject.toml file and returns its contents as a dictionary."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class EnvironmentEnum(StrEnum):
    DEV = "development"
    PROD = "production"
    STAGING = "staging"
    TEST = "test"


class ServerSettings(Settings):
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    LOG_LEVEL: str = "info"
    ENVIRONMENT: EnvironmentEnum = EnvironmentEnum.DEV
    WORKERS: int = 1


class GraphSettings(Settings):
    DGRAPH_URL: str = "http://localhost:8080"
    DGRAPH_TIMEOUT: float = 10.0


server_settings = ServerSettings()
graph_settings = GraphSettings()
VERSION = pyproject()["project"]["version"]
APP_NAME = pyproject()["project"]["name"]
