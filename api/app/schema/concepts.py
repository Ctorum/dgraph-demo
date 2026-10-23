from enum import StrEnum

# Managed by their own modules (or by Dgraph itself): read-only here.
PROTECTED = ("dgraph.", "kosmos.")
# Hidden from the type map: Kosmos alone has 256 types.
HIDDEN = PROTECTED


class VertexConcept(StrEnum):
    TIPO = "Tipo"
    PREDICADO = "Predicado"


class PredicateTypeConcept(StrEnum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATETIME = "datetime"
    UID = "uid"
    GEO = "geo"


TOKENIZERS = {
    PredicateTypeConcept.STRING: {
        "exact",
        "hash",
        "term",
        "fulltext",
        "trigram",
    },
    PredicateTypeConcept.INT: {"int"},
    PredicateTypeConcept.FLOAT: {"float"},
    PredicateTypeConcept.BOOL: {"bool"},
    PredicateTypeConcept.DATETIME: {"year", "month", "day", "hour"},
    PredicateTypeConcept.GEO: {"geo"},
    PredicateTypeConcept.UID: set(),
}
