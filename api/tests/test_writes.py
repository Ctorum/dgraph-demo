"""Writes against the Dgraph in .env. Almost all run with ``dry_run``, which
validates and builds the mutation without applying it."""

import json
import re
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import graph_settings

# Grupo Econômico (domain), Grupo Gerdau and Grupo Empresarial (instances),
# Membros do Grupo Econômico (relation type), as loaded in the Kosmos data.
GRUPO_ECONOMICO = 0x328517
GRUPO_GERDAU = 0x328C68
GRUPO_EMPRESARIAL = 0x328C78
MEMBROS = 0x328670


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def write(
    client: TestClient, method: str, path: str, body: dict
) -> httpx.Response:
    sep = "&" if "?" in path else "?"
    return client.request(method, f"{path}{sep}dry_run=true", json=body)


def preview(client: TestClient, method: str, path: str, body: dict) -> dict:
    response = write(client, method, path, body)
    assert response.status_code < 300, response.text
    data = response.json()["data"]
    assert data["applied"] is False
    return data


def fields(response: httpx.Response) -> dict[str, str]:
    return {f["name"]: f["detail"] for f in response.json()["fields"]}


def test_ontologia_classe_preview(client):
    data = preview(
        client, "POST", "/ontologia/classes", {"nome": "Nova", "pai_id": 3}
    )
    (mutation,) = [json.loads(m) for m in data["mutations"]]
    node = mutation["set"][0]
    assert node["dgraph.type"] == "ontologia.Classe"
    assert node["ontologia.Classe.id"] == data["key"]
    assert node["ontologia.SubclasseDe"]


def test_ontologia_rejects_cycle(client):
    response = write(client, "PATCH", "/ontologia/classes/1", {"pai_id": 3})
    assert response.status_code == 422
    assert "pai_id" in fields(response)


def test_kosmos_campo_follows_source_conventions(client):
    data = preview(
        client,
        "POST",
        f"/kosmos/dominios/{GRUPO_ECONOMICO}/campos",
        {"nome": "Código Interno", "tipo": "text"},
    )
    predicate, type_ = data["mutations"][:2]
    assert re.fullmatch(
        r"kosmos\.Codigo_Interno_[0-9a-f]{8}: string @index\(term\) \.",
        predicate,
    )
    assert type_.startswith("type kosmos.Grupo_Economico {")
    assert predicate.split(":")[0] in type_


def test_kosmos_instancia_follows_source_conventions(client):
    form = client.get(f"/kosmos/dominios/{GRUPO_ECONOMICO}/formulario").json()[
        "data"
    ]
    by_name = {c["nome"]: c["id"] for c in form["campos"]}
    data = preview(
        client,
        "POST",
        f"/kosmos/dominios/{GRUPO_ECONOMICO}/instancias",
        {
            "valores": {
                by_name["Nome do Grupo Econômico"]: "Grupo Teste",
                by_name["Tipo de Grupo Econômico"]: [GRUPO_EMPRESARIAL],
            }
        },
    )
    node = json.loads(data["mutations"][0])["set"][0]
    # Grupo Econômico's kosmos.id starts with a9b0ee12.
    assert re.fullmatch(r"DOM_a9b0ee12_\d{13}_0", node["kosmos.name"])
    assert node["dgraph.type"] == "kosmos.Grupo_Economico"
    assert node["kosmos.nickname"] == "Grupo Teste"


def test_kosmos_instancia_validates_fields(client):
    form = client.get(f"/kosmos/dominios/{GRUPO_ECONOMICO}/formulario").json()[
        "data"
    ]
    tipo = next(
        c["id"]
        for c in form["campos"]
        if c["nome"] == "Tipo de Grupo Econômico"
    )
    response = write(
        client,
        "POST",
        f"/kosmos/dominios/{GRUPO_ECONOMICO}/instancias",
        {"valores": {tipo: [GRUPO_GERDAU]}},
    )
    assert response.status_code == 422
    errors = fields(response)
    assert any("Obrigatório" in e for e in errors.values())
    assert errors[f"valores.{tipo}"].endswith(
        "não é de Tipo de Grupo Econômico"
    )


def test_kosmos_relacao_checks_domains(client):
    response = write(
        client,
        "POST",
        "/kosmos/relacoes",
        {
            "tipo_id": MEMBROS,
            "sujeito_id": GRUPO_GERDAU,
            "objeto_id": GRUPO_EMPRESARIAL,
        },
    )
    assert response.status_code == 422
    assert "objeto_id" in fields(response)


def test_kosmos_stale_version_conflicts(client):
    response = write(
        client,
        "PATCH",
        f"/kosmos/instancias/{GRUPO_GERDAU}",
        {"valores": {}, "version": 999},
    )
    assert response.status_code == 409


def test_schema_refuses_type_change_with_data(client):
    response = write(
        client,
        "POST",
        "/schema/tipos",
        {
            "nome": "zz.Y",
            "predicados": [{"nome": "ontologia.Classe.nome", "tipo": "int"}],
        },
    )
    assert response.status_code == 409


def test_schema_type_round_trip(client):
    body = {
        "nome": "zztest.Coisa",
        "predicados": [
            {
                "nome": "zztest.Coisa.nome",
                "tipo": "string",
                "indices": ["exact"],
            }
        ],
    }
    try:
        assert client.post("/schema/tipos", json=body).status_code == 201
        assert client.get("/schema/tipos/zztest.Coisa").json()[
            "data"
        ] == body | {
            "predicados": [
                body["predicados"][0] | {"lista": False, "reverse": False}
            ]
        }
        undo = client.delete("/schema/tipos/zztest.Coisa").json()["data"][
            "desfazer"
        ]
        assert undo == {
            "method": "POST",
            "path": "/schema/tipos",
            "body": body
            | {
                "predicados": [
                    body["predicados"][0] | {"lista": False, "reverse": False}
                ]
            },
        }
        assert client.get("/schema/tipos/zztest.Coisa").status_code == 404
    finally:
        httpx.post(
            f"{graph_settings.DGRAPH_URL}/alter",
            json={"drop_attr": "zztest.Coisa.nome"},
        )


def test_writes_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(graph_settings, "WRITE_ENABLED", False)
    response = client.post("/ontologia/classes", json={"nome": "Bloqueada"})
    assert response.status_code == 403
