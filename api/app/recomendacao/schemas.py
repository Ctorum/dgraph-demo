from pydantic import BaseModel, Field


class RecomendacaoSchema(BaseModel):
    id: int = Field(examples=[26])
    nome: str = Field(examples=["Produto 26"])
    score: int = Field(
        description="Quantos caminhos no grafo levam a este item"
    )
