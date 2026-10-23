from enum import StrEnum

NAMESPACE = "kosmos"


class VertexConcept(StrEnum):
    # Instances take their domain's name as type; only domains are fixed.
    DOMINIO = "Dominio"


class ConceptTypeConcept(StrEnum):
    DOMAIN = "domain"
    FIELD = "field"
    RELATIONSHIP = "relationship"


class DirecaoConcept(StrEnum):
    SAIDA = "saida"
    ENTRADA = "entrada"


class StatusConcept(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class FieldTypeConcept(StrEnum):
    # "computed" fields exist in the data but are filled by the source
    # system, so they cannot be created here.
    TEXT = "text"
    NUMBER = "number"
    PERCENTAGE = "percentage"
    DATE = "date"
    BOOLEAN = "boolean"
    SELECTOR = "selector"


# DQL schema of a field predicate, matching what the source system declares.
PREDICATE_SCHEMA = {
    FieldTypeConcept.TEXT: "string @index(term)",
    FieldTypeConcept.NUMBER: "float @index(float)",
    FieldTypeConcept.PERCENTAGE: "float @index(float)",
    FieldTypeConcept.DATE: "datetime @index(day)",
    FieldTypeConcept.BOOLEAN: "bool",
    FieldTypeConcept.SELECTOR: "[uid] @reverse",
}

# Predicates every instance type carries besides its fields.
INSTANCE_FIELDS = [
    "kosmos.createdAt",
    "kosmos.description",
    "kosmos.instanceOf",
    "kosmos.name",
    "kosmos.nickname",
    "kosmos.status",
    "kosmos.updatedAt",
    "kosmos.version",
]
