from typing import Any

from pydantic import BaseModel, Field

from .concepts import DirecaoConcept, FieldTypeConcept, StatusConcept


def Nome(default: Any = ...) -> Any:
    return Field(default, min_length=1, max_length=120)


class RelacaoMapaSchema(BaseModel):
    relacao: str = Field(examples=["Membros do Grupo Econômico"])
    origem: str = Field(
        description="Domínio do sujeito", examples=["Grupo Econômico"]
    )
    destino: str = Field(description="Domínio do objeto", examples=["Empresa"])
    quantidade: int


class CampoSchema(BaseModel):
    campo: str = Field(examples=["Tipo de Grupo Econômico"])
    tipo: str = Field(examples=["selector"])
    origem: str = Field(description="Domínio dono do campo")
    destino: str | None = Field(
        None, description="Domínio para onde o seletor aponta"
    )
    campo_id: int = Field(description="uid do conceito do campo")


class InstanciaSchema(BaseModel):
    id: int = Field(description="uid do Dgraph em decimal")
    nome: str = Field(examples=["Grupo Gerdau"])
    status: str | None = None


class ConexaoSchema(BaseModel):
    via: str = Field(
        description="Campo ou relação", examples=["Persona Vinculada"]
    )
    direcao: DirecaoConcept
    id: int
    nome: str
    dominio: str
    relacao_id: int | None = Field(
        None, description="uid da relação reificada, quando a conexão é uma"
    )


class RefSchema(BaseModel):
    id: int
    nome: str


class AlvoSchema(RefSchema):
    abstrato: bool = Field(
        False, description="Domínio sem instâncias próprias (ex.: Persona)"
    )


class CampoFormSchema(BaseModel):
    id: int
    nome: str
    tipo: str
    obrigatorio: bool
    ordem: int
    alvos: list[AlvoSchema] = Field(default_factory=list)
    aceitos: list[RefSchema] | None = Field(
        None,
        description="Domínios que o seletor aceita: os alvos concretos e, "
        "para alvos abstratos, os domínios já usados no campo. null = qualquer",
    )
    valor: Any = None


class FormularioSchema(BaseModel):
    """Fields of a domain (and, editing, the instance's current values)."""

    dominio: RefSchema
    campos: list[CampoFormSchema]
    apelido: str | None = None
    version: int | None = None


class BuscaSchema(BaseModel):
    id: int
    nome: str
    dominio: str


class TipoRelacaoSchema(BaseModel):
    id: int
    nome: str
    campos: list[CampoFormSchema] = Field(
        description="Seletores: sujeito e objeto preenchem os que aceitam "
        "seus domínios"
    )


class InativoSchema(BaseModel):
    tipo: str = Field(examples=["Dominio", "Campo", "Empresa"])
    id: int
    nome: str
    relacao_id: int | None = None


class DominioInputSchema(BaseModel):
    nome: str = Nome()
    categoria: str = Field("Funcional", max_length=60)
    descricao: str | None = Field(None, max_length=2000)


class DominioUpdateSchema(BaseModel):
    nome: str | None = Nome(None)
    categoria: str | None = Field(None, max_length=60)
    descricao: str | None = Field(None, max_length=2000)


class CampoInputSchema(BaseModel):
    nome: str = Nome()
    tipo: FieldTypeConcept
    alvo_id: int | None = Field(None, description="Domínio alvo do seletor")
    obrigatorio: bool = False


class CampoUpdateSchema(BaseModel):
    nome: str | None = Nome(None)
    tipo: FieldTypeConcept | None = None
    alvo_id: int | None = None
    obrigatorio: bool | None = None


class InstanciaInputSchema(BaseModel):
    valores: dict[int, Any] = Field(
        default_factory=dict,
        description="Valor por id do campo; seletores recebem lista de ids",
    )
    apelido: str | None = Field(None, max_length=200)


class InstanciaUpdateSchema(InstanciaInputSchema):
    version: int = Field(description="Versão lida; outra versão gera 409")


class TipoRelacaoInputSchema(BaseModel):
    nome: str = Nome()
    categoria: str = Field("Funcional", max_length=60)
    descricao: str | None = Field(None, max_length=2000)
    sujeito_id: int = Field(description="Domínio do sujeito")
    objeto_id: int = Field(description="Domínio do objeto")


class RelacaoInputSchema(BaseModel):
    tipo_id: int
    sujeito_id: int
    objeto_id: int


class StatusInputSchema(BaseModel):
    status: StatusConcept
