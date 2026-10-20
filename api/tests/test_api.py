"""Integration smoke test against the Dgraph configured in .env."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def get(client: TestClient, path: str) -> dict:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/fraude/clientes/281/conexoes",
            lambda d: {c["id"] for c in d} >= {282},
        ),
        ("/fraude/aneis", lambda d: any(281 in a["clientes"] for a in d)),
        ("/fraude/contas/61/ciclos", lambda d: d[0]["contas"][0] == 61),
        ("/fraude/transferencias/suspeitas?limit=3", lambda d: len(d) == 3),
        (
            "/recomendacao/usuarios/1/produtos",
            lambda d: d[0]["score"] >= d[-1]["score"],
        ),
        (
            "/recomendacao/usuarios/1/seguir",
            lambda d: all(u["id"] != 1 for u in d),
        ),
        (
            "/ontologia/classes/3/ancestrais",
            lambda d: [c["nome"] for c in d] == ["Agente", "Coisa"],
        ),
        ("/ontologia/classes/1/individuos", lambda d: len(d) == 86),
        ("/ontologia/individuos/101/relacoes", lambda d: len(d) > 0),
    ],
)
def test_use_cases(client, path, expected):
    data = get(client, path)
    assert expected(data["items"])
    assert data["queries"]
    ids = {node["id"] for node in data["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])


def test_graph_marks_focus(client):
    data = get(client, "/fraude/clientes/281/conexoes")
    focus = [n["id"] for n in data["nodes"] if n["role"] == "focus"]
    assert focus == ["Cliente:281"]


def test_recomendacao_skips_owned_products(client):
    # Products the user already bought must never come back as suggestions.
    data = get(client, "/recomendacao/usuarios/1/produtos?limit=100")
    comprados = {
        e["target"]
        for e in data["edges"]
        if e["source"] == "Usuario:1" and e["label"] == "Comprou"
    }
    assert comprados
    assert not {f"Produto:{p['id']}" for p in data["items"]} & comprados


def test_not_found(client):
    response = client.get("/fraude/clientes/999999/conexoes")
    assert response.status_code == 404
    assert response.json()["message"] == "Cliente 999999 not found"
