from enum import StrEnum

NAMESPACE = "ontologia"


class VertexConcept(StrEnum):
    CLASSE = "Classe"
    INDIVIDUO = "Individuo"
    RELACAO = "Relacao"


class StatusConcept(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
