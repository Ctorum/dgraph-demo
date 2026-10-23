from pydantic import BaseModel, Field

from .concepts import PredicateTypeConcept

NAME = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$"


class PredicadoSchema(BaseModel):
    nome: str = Field(
        pattern=NAME, max_length=120, examples=["loja.Produto.nome"]
    )
    tipo: PredicateTypeConcept
    lista: bool = False
    indices: list[str] = Field(
        default_factory=list, examples=[["exact", "term"]]
    )
    reverse: bool = Field(False, description="Só para uid")


class TipoInputSchema(BaseModel):
    nome: str = Field(pattern=NAME, max_length=120, examples=["loja.Produto"])
    predicados: list[PredicadoSchema] = Field(min_length=1)


class TipoUpdateSchema(BaseModel):
    predicados: list[PredicadoSchema] = Field(
        min_length=1,
        description="Lista completa; quem sai deixa o type, os dados ficam",
    )


class SchemaRowSchema(BaseModel):
    tipo: str
    predicado: str
    dgraph: str = Field(description="Tipo no schema", examples=["[uid]"])
    indices: list[str] = Field(default_factory=list)
    reverse: bool = False
