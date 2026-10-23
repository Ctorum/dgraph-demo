from typing import Any

from pydantic import BaseModel, Field

from .concepts import StatusConcept, VertexConcept


def Nome(default: Any = ...) -> Any:
    return Field(default, min_length=1, max_length=120)


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
    relacao_id: int = Field(description="uid do nó Relacao, em decimal")


class InativoSchema(BaseModel):
    tipo: VertexConcept
    id: int
    nome: str
    relacao_id: int | None = None


class BuscaSchema(BaseModel):
    id: int
    nome: str
    tipo: VertexConcept


class ClasseInputSchema(BaseModel):
    nome: str = Nome()
    pai_id: int | None = Field(None, description="Superclasse; vazio cria raiz")


class ClasseUpdateSchema(BaseModel):
    nome: str | None = Nome(None)
    pai_id: int | None = Field(
        None, description="Enviar null explicitamente torna a classe raiz"
    )


class IndividuoInputSchema(BaseModel):
    nome: str = Nome()
    classe_id: int
    atributos: dict[str, Any] = Field(default_factory=dict)


class IndividuoUpdateSchema(BaseModel):
    nome: str | None = Nome(None)
    classe_id: int | None = None
    atributos: dict[str, Any] | None = None


class RelacaoInputSchema(BaseModel):
    tipo: str = Field(
        min_length=1,
        max_length=60,
        pattern=r"^[a-z][a-z0-9_]*$",
        examples=["cita"],
    )
    origem_id: int
    destino_id: int


class StatusInputSchema(BaseModel):
    status: StatusConcept
