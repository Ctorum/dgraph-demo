from pydantic import BaseModel, Field

from .concepts import IdentificadorConcept


class ConexaoSchema(BaseModel):
    id: int = Field(description="ID do cliente conectado", examples=[282])
    nome: str = Field(examples=["Cliente 282"])
    via: IdentificadorConcept = Field(description="Tipo do identificador")
    valor: str = Field(
        description="Identificador compartilhado", examples=["10.1.51.1"]
    )


class AnelSchema(BaseModel):
    via: IdentificadorConcept
    valor: str = Field(examples=["e239d3d79107756fbece71454ff6f2c5"])
    clientes: list[int] = Field(
        description="Clientes que compartilham o identificador"
    )


class CicloSchema(BaseModel):
    contas: list[int] = Field(
        description="Contas do ciclo, voltando à origem",
        examples=[[61, 170, 30]],
    )


class TransferenciaSchema(BaseModel):
    origem: int = Field(description="ID da conta de origem")
    destino: int = Field(description="ID da conta de destino")
    valor: float
    dias_atras: float
