.PHONY: install api web test up down dump

install:
	$(MAKE) -C api install
	cd web && npm install

# API em :28000 (FastAPI + OrientDB do .env)
api:
	$(MAKE) -C api dev

# Interface em :5173, com /api apontando para a API
web:
	cd web && npm run dev

test:
	$(MAKE) -C api test
	cd web && npm run build

# API em :3081 e interface em :3080, em containers (Dgraph precisa estar de pé)
up:
	docker compose up -d --build

down:
	docker compose down

# Exporta o Dgraph (RDF + schema) para ./dump. O /admin só aceita chamadas
# de dentro do container, por isso o export roda lá e é copiado depois.
dump:
	docker exec dgraph-alpha sh -c 'rm -rf /dgraph/export && curl -sf localhost:8080/admin -H "Content-Type: application/json" -d "{\"query\":\"mutation { export(input: {format: \\\"rdf\\\"}) { response { code } } }\"}"'
	rm -rf dump && mkdir dump
	docker exec dgraph-alpha sh -c 'cd /dgraph/export/dgraph.* && tar c .' | tar x -C dump
	docker exec dgraph-alpha rm -rf /dgraph/export
	@ls -la dump
