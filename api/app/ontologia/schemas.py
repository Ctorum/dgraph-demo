from typing import Any

from pydantic import BaseModel, Field


class AncestralSchema(BaseModel):
    id: int
    nome: str = Field(examples=["Agente"])
    nivel: int = Field(description="Distância até a classe consultada")


class IndividuoSchema(BaseModel):
    id: int
    nome: str = Field(examples=["Pessoa 1"])
    atributos: dict[str, Any] | None = None
    classes: list[str] = Field(description="Classes diretas do indivíduo")


class RelacaoSchema(BaseModel):
    tipo: str = Field(examples=["trabalha_em"])
    origem_id: int
    origem: str
    destino_id: int
    destino: str
