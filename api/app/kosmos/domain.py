from dataclasses import dataclass
from functools import cached_property
from typing import override

from app.api.domain import ApiDomain
from app.api.exc.exceptions import does_not_exist
from app.api.schemas import BaseResponseSchema
from app.infra.graph.adapter import DgraphClient
from app.infra.graph.schemas import GraphSchema, WriteSchema

from .concepts import ConceptTypeConcept
from .repository import KosmosRepository, KosmosWriteRepository
from .schemas import (
    BuscaSchema,
    CampoInputSchema,
    CampoSchema,
    CampoUpdateSchema,
    ConexaoSchema,
    DominioInputSchema,
    DominioUpdateSchema,
    FormularioSchema,
    InativoSchema,
    InstanciaInputSchema,
    InstanciaSchema,
    InstanciaUpdateSchema,
    RelacaoInputSchema,
    RelacaoMapaSchema,
    StatusInputSchema,
    TipoRelacaoInputSchema,
    TipoRelacaoSchema,
)


@dataclass
class GetMapaRelacoesUseCase(ApiDomain):
    context: DgraphClient

    @cached_property
    def repository(self) -> KosmosRepository:
        return KosmosRepository(self.context)

    @override
    async def execute(
        self,
    ) -> BaseResponseSchema[GraphSchema[RelacaoMapaSchema]]:
        return BaseResponseSchema(
            message="Mapa de relações encontrado",
            data=await self.repository.fetch_mapa(),
        )


@dataclass
class GetModeloDominioUseCase(ApiDomain):
    context: DgraphClient
    dominio_id: int

    @cached_property
    def repository(self) -> KosmosRepository:
        return KosmosRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[CampoSchema]]:
        dominio = await self.repository.get_dominio(self.dominio_id)
        if dominio is None:
            raise does_not_exist(f"Dominio {self.dominio_id}")
        return BaseResponseSchema(
            message="Modelo encontrado",
            data=await self.repository.fetch_modelo(dominio),
        )


@dataclass
class ListInstanciasDominioUseCase(ApiDomain):
    context: DgraphClient
    dominio_id: int
    limit: int

    @cached_property
    def repository(self) -> KosmosRepository:
        return KosmosRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[InstanciaSchema]]:
        dominio = await self.repository.get_dominio(self.dominio_id)
        if dominio is None:
            raise does_not_exist(f"Dominio {self.dominio_id}")
        return BaseResponseSchema(
            message="Instâncias encontradas",
            data=await self.repository.fetch_instancias(dominio, self.limit),
        )


@dataclass
class ListConexoesInstanciaUseCase(ApiDomain):
    context: DgraphClient
    instancia_id: int

    @cached_property
    def repository(self) -> KosmosRepository:
        return KosmosRepository(self.context)

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[ConexaoSchema]]:
        instancia = await self.repository.get_instancia(self.instancia_id)
        if instancia is None:
            raise does_not_exist(f"Instancia {self.instancia_id}")
        return BaseResponseSchema(
            message="Conexões encontradas",
            data=await self.repository.fetch_conexoes(instancia),
        )


# Writes: every use case takes ``dry_run`` and then only previews mutations.


@dataclass
class _WriteUseCase(ApiDomain):
    context: DgraphClient
    dry_run: bool

    @cached_property
    def repository(self) -> KosmosWriteRepository:
        return KosmosWriteRepository(self.context, dry_run=self.dry_run)

    async def concept(self, id_: int, *kinds: str) -> dict:
        found = await self.repository.get_concept(id_)
        if not found or (kinds and found.get("conceito") not in kinds):
            raise does_not_exist(f"{' ou '.join(kinds) or 'Nó'} {id_}")
        return found

    async def instancia(self, id_: int) -> dict:
        found = await self.repository.get_concept(id_)
        if not found or not found.get("dominio"):
            raise does_not_exist(f"Instancia {id_}")
        return found

    def done(self, data: WriteSchema) -> BaseResponseSchema[WriteSchema]:
        return BaseResponseSchema(
            message="Prévia da escrita" if self.dry_run else "Escrita aplicada",
            data=data,
        )


DONOS = (ConceptTypeConcept.DOMAIN, ConceptTypeConcept.RELATIONSHIP)


@dataclass
class CreateDominioUseCase(_WriteUseCase):
    payload: DominioInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_dominio(self.payload))


@dataclass
class UpdateDominioUseCase(_WriteUseCase):
    """Renames or redescribes a domain or a relation type."""

    dominio_id: int
    payload: DominioUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        found = await self.concept(self.dominio_id, *DONOS)
        return self.done(
            await self.repository.update_concept(found, self.payload)
        )


@dataclass
class CreateCampoUseCase(_WriteUseCase):
    dono_id: int
    payload: CampoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        dono = await self.concept(self.dono_id, *DONOS)
        return self.done(await self.repository.create_campo(dono, self.payload))


@dataclass
class UpdateCampoUseCase(_WriteUseCase):
    campo_id: int
    payload: CampoUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        campo = await self.concept(self.campo_id, ConceptTypeConcept.FIELD)
        return self.done(
            await self.repository.update_campo(campo, self.payload)
        )


@dataclass
class CreateInstanciaUseCase(_WriteUseCase):
    dominio_id: int
    payload: InstanciaInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        dominio = await self.concept(self.dominio_id, ConceptTypeConcept.DOMAIN)
        return self.done(
            await self.repository.create_instancia(dominio, self.payload)
        )


@dataclass
class UpdateInstanciaUseCase(_WriteUseCase):
    instancia_id: int
    payload: InstanciaUpdateSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        instancia = await self.instancia(self.instancia_id)
        return self.done(
            await self.repository.update_instancia(instancia, self.payload)
        )


@dataclass
class CreateTipoRelacaoUseCase(_WriteUseCase):
    payload: TipoRelacaoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(
            await self.repository.create_tipo_relacao(self.payload)
        )


@dataclass
class CreateRelacaoUseCase(_WriteUseCase):
    payload: RelacaoInputSchema

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        return self.done(await self.repository.create_relacao(self.payload))


@dataclass
class SetStatusUseCase(_WriteUseCase):
    """Inactivates or reactivates any kosmos node; nothing is deleted."""

    id_: int
    payload: StatusInputSchema
    path: str

    @override
    async def execute(self) -> BaseResponseSchema[WriteSchema]:
        found = await self.concept(self.id_)
        return self.done(
            await self.repository.set_status(
                found, self.payload.status, self.path
            )
        )


@dataclass
class GetFormularioUseCase(_WriteUseCase):
    """Form of a domain; with ``instancia_id``, filled with its values."""

    dominio_id: int | None = None
    instancia_id: int | None = None

    @override
    async def execute(self) -> BaseResponseSchema[FormularioSchema]:
        instancia = None
        if self.instancia_id is not None:
            instancia = await self.instancia(self.instancia_id)
            dominio = instancia["dominio"]
        else:
            dominio = await self.concept(
                self.dominio_id or 0, ConceptTypeConcept.DOMAIN
            )
        return BaseResponseSchema(
            message="Formulário",
            data=await self.repository.fetch_formulario(dominio, instancia),
        )


@dataclass
class ListTiposRelacaoUseCase(ApiDomain):
    context: DgraphClient

    @override
    async def execute(self) -> BaseResponseSchema[list[TipoRelacaoSchema]]:
        return BaseResponseSchema(
            message="Tipos de relação",
            data=await KosmosWriteRepository(
                self.context
            ).fetch_tipos_relacao(),
        )


@dataclass
class ListInativosUseCase(ApiDomain):
    context: DgraphClient

    @override
    async def execute(self) -> BaseResponseSchema[GraphSchema[InativoSchema]]:
        return BaseResponseSchema(
            message="Inativos encontrados",
            data=await KosmosWriteRepository(self.context).fetch_inativos(),
        )


@dataclass
class SearchUseCase(ApiDomain):
    context: DgraphClient
    q: str
    tipo: str
    dominio_id: int | None

    @override
    async def execute(self) -> BaseResponseSchema[list[BuscaSchema]]:
        return BaseResponseSchema(
            message="Busca concluída",
            data=await KosmosWriteRepository(self.context).fetch_busca(
                self.q, self.tipo, self.dominio_id
            ),
        )
