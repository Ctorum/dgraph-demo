from enum import StrEnum

NAMESPACE = "fraude"


class VertexConcept(StrEnum):
    CLIENTE = "Cliente"
    CONTA = "Conta"


class IdentificadorConcept(StrEnum):
    """Vértices que, compartilhados entre clientes, indicam um anel."""

    DISPOSITIVO = "Dispositivo"
    IP = "IP"
    TELEFONE = "Telefone"


# Identificador -> (aresta Cliente -> identificador, predicado do valor)
IDENTIFICADORES = {
    IdentificadorConcept.DISPOSITIVO: ("UsaDispositivo", "fingerprint"),
    IdentificadorConcept.IP: ("UsaIp", "ip"),
    IdentificadorConcept.TELEFONE: ("TemTelefone", "numero"),
}
