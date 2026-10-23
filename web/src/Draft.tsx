import {
  type KeyboardEvent,
  type MutableRefObject,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react'

import { ApiError, request } from './api'
import { DB_LABEL, EDITS, type Draft } from './drafts'
import {
  search,
  write,
  type CampoForm,
  type Formulario,
  type Predicado,
  type Ref,
  type TipoDgraph,
  type TipoRelacao,
  type WriteRequest,
  type WriteResult,
} from './writes'

/* A draft is described by a Spec: its fields, initial values and the request
   that saves it. The panel renders the fields, previews the request with
   dry_run as you type and maps validation errors back onto the fields. */

type Values = Record<string, unknown>

type SearchKind = 'classe' | 'individuo' | 'instancia' | 'dominio'

interface SearchSpec {
  kind: SearchKind
  /** Restricts instance search to one domain. */
  dominio?: number
  /** Domain names a selector accepts; null or absent means any. */
  aceitos?: string[] | null
  multiple?: boolean
}

interface Field {
  name: string
  label: string
  kind:
    | 'text'
    | 'textarea'
    | 'number'
    | 'date'
    | 'bool'
    | 'select'
    | 'search'
    | 'pairs'
    | 'predicados'
    | 'static'
  required?: boolean
  help?: string
  placeholder?: string
  options?: { value: string; label: string }[]
  /** Suggestions for a text field. */
  list?: string[]
  pattern?: string
  search?: SearchSpec
}

interface Spec {
  title: string
  submit: string
  fields: (values: Values) => Field[]
  initial: Values
  /** null while required fields are missing. */
  request: (values: Values) => WriteRequest | null
  label?: (values: Values) => string
  /** Maps an API field error name onto a field. */
  errorField?: (name: string) => string
  /** Offered when the API answers 409 because the data changed. */
  reloadable?: boolean
}

const filled = (v: unknown) =>
  v != null && v !== '' && !(Array.isArray(v) && v.length === 0)

const refId = (v: unknown) => (v as Ref | null)?.id ?? null

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/** Only what changed goes into an edit. */
function changed(values: Values, initial: Values, map: Record<string, (v: unknown) => unknown>) {
  const body: Values = {}
  for (const [name, toBody] of Object.entries(map)) {
    if (!same(values[name], initial[name])) Object.assign(body, toBody(values[name]))
  }
  return body
}

const API_FIELD: Record<string, string> = {
  pai_id: 'pai',
  classe_id: 'classe',
  destino_id: 'destino',
  origem_id: 'destino',
  alvo_id: 'alvo',
  sujeito_id: 'sujeito',
  objeto_id: 'objeto',
  tipo_id: 'tipo',
}

const CATEGORIAS = [
  'Funcional',
  'Estrutural',
  'Arquitetura',
  'Identificação',
  'Mercado Financeiro',
  'Econômico',
  'Provedor de Dados',
]

const FIELD_TYPES = [
  { value: 'text', label: 'Texto' },
  { value: 'number', label: 'Número' },
  { value: 'percentage', label: 'Percentual' },
  { value: 'date', label: 'Data' },
  { value: 'boolean', label: 'Sim ou não' },
  { value: 'selector', label: 'Seletor' },
]

const DGRAPH_TYPES = ['string', 'int', 'float', 'bool', 'datetime', 'uid', 'geo']
const TOKENIZERS: Record<string, string[]> = {
  string: ['exact', 'hash', 'term', 'fulltext', 'trigram'],
  int: ['int'],
  float: ['float'],
  bool: ['bool'],
  datetime: ['year', 'month', 'day', 'hour'],
  geo: ['geo'],
  uid: [],
}

function pairsOf(obj: unknown): [string, string][] {
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
    k,
    typeof v === 'string' ? v : JSON.stringify(v),
  ])
}

/** Attribute values keep their JSON type when they parse as JSON. */
function objectOf(pairs: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of (pairs as [string, string][]) ?? []) {
    if (!k.trim()) continue
    try {
      out[k.trim()] = JSON.parse(v)
    } catch {
      out[k.trim()] = v
    }
  }
  return out
}

/* Kosmos instance forms come from the domain's fields. */

const fieldName = (c: CampoForm) => `c${c.id}`

function campoField(c: CampoForm): Field {
  const base = { name: fieldName(c), label: c.nome, required: c.obrigatorio }
  switch (c.tipo) {
    case 'text':
      return { ...base, kind: 'text' }
    case 'number':
    case 'percentage':
      return { ...base, kind: 'number', help: c.tipo === 'percentage' ? 'Percentual' : undefined }
    case 'date':
      return { ...base, kind: 'date' }
    case 'boolean':
      return { ...base, kind: 'bool' }
    case 'selector': {
      const aceitos = c.aceitos?.map((a) => a.nome) ?? null
      return {
        ...base,
        kind: 'search',
        help: aceitos ? `Instância de ${aceitos.join(', ')}` : 'Qualquer instância',
        search: {
          kind: 'instancia',
          dominio: c.aceitos?.length === 1 ? c.aceitos[0].id : undefined,
          aceitos,
          multiple: true,
        },
      }
    }
    default:
      return { ...base, kind: 'static', required: false, help: 'Calculado pelo sistema de origem' }
  }
}

function campoValue(c: CampoForm): unknown {
  if (c.valor == null) return c.tipo === 'selector' ? [] : ''
  if (c.tipo === 'date') return String(c.valor).slice(0, 10)
  return c.valor
}

function campoBody(c: CampoForm, v: unknown): unknown {
  if (c.tipo === 'selector') return ((v as Ref[]) ?? []).map((r) => r.id)
  if (!filled(v)) return null
  if (c.tipo === 'number' || c.tipo === 'percentage') return Number(v)
  return v
}

async function instanciaSpec(draft: Draft, editing: boolean): Promise<Spec> {
  const from = draft.from!
  const form = await request<Formulario>(
    editing ? `/kosmos/instancias/${from.key}/formulario` : `/kosmos/dominios/${from.key}/formulario`,
  )
  const initial: Values = { apelido: form.apelido ?? '' }
  for (const c of form.campos) initial[fieldName(c)] = campoValue(c)
  const editable = form.campos.filter((c) => c.tipo !== 'computed')
  return {
    title: editing ? `Editar ${from.label}` : `Nova instância de ${from.label}`,
    submit: editing ? 'Salvar' : 'Criar instância',
    initial,
    reloadable: editing,
    fields: () => [
      {
        name: 'apelido',
        label: 'Apelido',
        kind: 'text',
        help: 'Vazio usa o primeiro campo de texto',
      },
      ...form.campos.map(campoField),
    ],
    label: (v) =>
      String(
        v.apelido ||
          editable.map((c) => v[fieldName(c)]).find((x) => typeof x === 'string' && x) ||
          'novo',
      ),
    errorField: (name) => name.replace(/^valores\.(\d+)$/, 'c$1'),
    request: (v) => {
      const missing = editable.some((c) => c.obrigatorio && !filled(v[fieldName(c)]))
      if (!editing && missing) return null
      const valores: Record<number, unknown> = {}
      for (const c of editable) {
        const name = fieldName(c)
        if (editing && same(v[name], initial[name])) continue
        const body = campoBody(c, v[name])
        if (!editing && (body == null || (Array.isArray(body) && !body.length))) continue
        valores[c.id] = body
      }
      const apelido = String(v.apelido ?? '').trim() || null
      return editing
        ? {
            method: 'PATCH',
            path: `/kosmos/instancias/${from.key}`,
            body: {
              valores,
              apelido: apelido !== initial.apelido ? apelido : null,
              version: form.version,
            },
          }
        : { method: 'POST', path: `/kosmos/dominios/${from.key}/instancias`, body: { valores, apelido } }
    },
  }
}

async function relacaoKosmosSpec(draft: Draft): Promise<Spec> {
  const from = draft.from!
  const tipos = await request<TipoRelacao[]>('/kosmos/relacoes/tipos')
  const accepts = (c: CampoForm, dominio: string) =>
    c.aceitos == null || c.aceitos.some((a) => a.nome === dominio)
  // A type fits when one of its selectors takes the starting instance.
  const usable = tipos.filter((t) => t.campos.some((c) => accepts(c, from.type)))
  const otherSide = (tipo: TipoRelacao | undefined) => {
    if (!tipo) return null
    const mine = tipo.campos.findIndex((c) => accepts(c, from.type))
    const rest = tipo.campos.filter((_, i) => i !== mine)
    if (rest.some((c) => c.aceitos == null)) return null
    return [...new Set(rest.flatMap((c) => c.aceitos!.map((a) => a.nome)))]
  }
  const target = draft.target
  const fits = (t: TipoRelacao) => {
    if (!target) return true
    const aceitos = otherSide(t)
    return aceitos == null || aceitos.includes(target.type)
  }
  const options = usable.filter(fits)
  return {
    title: `Nova relação de ${from.label}`,
    submit: 'Criar relação',
    initial: {
      tipo: options.length === 1 ? String(options[0].id) : '',
      objeto: target ? { id: target.key, nome: target.label, dominio: target.type } : null,
    },
    fields: (v) => {
      const tipo = tipos.find((t) => String(t.id) === v.tipo)
      const aceitos = otherSide(tipo)
      return [
        { name: 'sujeito', label: 'Sujeito', kind: 'static', help: `${from.label} · ${from.type}` },
        {
          name: 'tipo',
          label: 'Tipo de relação',
          kind: 'select',
          required: true,
          options: options.map((t) => ({ value: String(t.id), label: t.nome })),
          help: options.length
            ? undefined
            : `Nenhum tipo de relação aceita ${from.type}${target ? ` e ${target.type}` : ''}. Crie um a partir do domínio.`,
        },
        {
          name: 'objeto',
          label: 'Objeto',
          kind: 'search',
          required: true,
          help: aceitos ? `Instância de ${aceitos.join(', ')}` : undefined,
          search: {
            kind: 'instancia',
            aceitos,
            dominio:
              aceitos?.length === 1
                ? tipo?.campos.flatMap((c) => c.aceitos ?? []).find((a) => a.nome === aceitos[0])?.id
                : undefined,
          },
        },
      ]
    },
    label: (v) => (v.objeto as Ref | null)?.nome ?? 'destino',
    request: (v) =>
      v.tipo && refId(v.objeto) != null
        ? {
            method: 'POST',
            path: '/kosmos/relacoes',
            body: { tipo_id: Number(v.tipo), sujeito_id: from.key, objeto_id: refId(v.objeto) },
          }
        : null,
  }
}

const predicadoVazio = (prefix: string): Predicado => ({
  nome: prefix,
  tipo: 'string',
  lista: false,
  indices: [],
  reverse: false,
})

async function buildSpec(draft: Draft): Promise<Spec> {
  const { kind, from, row } = draft
  const nome: Field = { name: 'nome', label: 'Nome', kind: 'text', required: true }
  const nomeReq = (v: Values) => String(v.nome ?? '').trim()

  switch (kind) {
    case 'o-classe-raiz':
    case 'o-subclasse':
      return {
        title: from ? `Nova subclasse de ${from.label}` : 'Nova classe raiz',
        submit: 'Criar classe',
        initial: { nome: '' },
        fields: () => [nome],
        request: (v) =>
          nomeReq(v)
            ? {
                method: 'POST',
                path: '/ontologia/classes',
                body: { nome: nomeReq(v), pai_id: from?.key ?? null },
              }
            : null,
      }
    case 'o-individuo':
      return {
        title: `Novo indivíduo de ${from!.label}`,
        submit: 'Criar indivíduo',
        initial: { nome: '', atributos: [] },
        fields: () => [nome, { name: 'atributos', label: 'Atributos', kind: 'pairs' }],
        request: (v) =>
          nomeReq(v)
            ? {
                method: 'POST',
                path: '/ontologia/individuos',
                body: { nome: nomeReq(v), classe_id: from!.key, atributos: objectOf(v.atributos) },
              }
            : null,
      }
    case 'o-relacao': {
      const tipos = await request<string[]>('/ontologia/relacoes/tipos')
      const target = draft.target
      return {
        title: `Nova relação de ${from!.label}`,
        submit: 'Criar relação',
        initial: { tipo: '', destino: target ? { id: target.key, nome: target.label } : null },
        fields: () => [
          {
            name: 'tipo',
            label: 'Tipo',
            kind: 'text',
            required: true,
            list: tipos,
            pattern: '[a-z][a-z0-9_]*',
            help: 'snake_case; os existentes aparecem como sugestão',
          },
          {
            name: 'destino',
            label: 'Destino',
            kind: 'search',
            required: true,
            search: { kind: 'individuo' },
          },
        ],
        label: (v) => (v.destino as Ref | null)?.nome ?? 'destino',
        request: (v) =>
          v.tipo && refId(v.destino) != null
            ? {
                method: 'POST',
                path: '/ontologia/relacoes',
                body: { tipo: v.tipo, origem_id: from!.key, destino_id: refId(v.destino) },
              }
            : null,
      }
    }
    case 'o-editar-classe': {
      const anc = await request<{ items: { id: number; nome: string; nivel: number }[] }>(
        `/ontologia/classes/${from!.key}/ancestrais`,
      )
      const pai = anc.items.find((i) => i.nivel === 1)
      const initial = { nome: from!.label, pai: pai ? { id: pai.id, nome: pai.nome } : null }
      return {
        title: `Editar ${from!.label}`,
        submit: 'Salvar',
        initial,
        fields: () => [
          nome,
          {
            name: 'pai',
            label: 'Superclasse',
            kind: 'search',
            help: 'Vazio torna a classe raiz',
            search: { kind: 'classe' },
          },
        ],
        request: (v) =>
          nomeReq(v)
            ? {
                method: 'PATCH',
                path: `/ontologia/classes/${from!.key}`,
                body: changed(v, initial, {
                  nome: (x) => ({ nome: String(x).trim() }),
                  pai: (x) => ({ pai_id: refId(x) }),
                }),
              }
            : null,
      }
    }
    case 'o-editar-individuo': {
      const initial = { nome: from!.label, atributos: pairsOf(from!.props.atributos), classe: null }
      return {
        title: `Editar ${from!.label}`,
        submit: 'Salvar',
        initial,
        fields: () => [
          nome,
          {
            name: 'classe',
            label: 'Mover para a classe',
            kind: 'search',
            help: 'Vazio mantém as classes atuais',
            search: { kind: 'classe' },
          },
          { name: 'atributos', label: 'Atributos', kind: 'pairs' },
        ],
        request: (v) =>
          nomeReq(v)
            ? {
                method: 'PATCH',
                path: `/ontologia/individuos/${from!.key}`,
                body: changed(v, initial, {
                  nome: (x) => ({ nome: String(x).trim() }),
                  classe: (x) => (refId(x) != null ? { classe_id: refId(x) } : {}),
                  atributos: (x) => ({ atributos: objectOf(x) }),
                }),
              }
            : null,
      }
    }
    case 'k-dominio':
    case 'k-editar-dominio': {
      const editing = kind === 'k-editar-dominio'
      const initial = editing
        ? {
            nome: from!.label,
            categoria: String(from!.props.categoria ?? ''),
            descricao: String(from!.props.descricao ?? ''),
          }
        : { nome: '', categoria: 'Funcional', descricao: '' }
      const what = from?.type === 'TipoRelacao' ? 'tipo de relação' : 'domínio'
      return {
        title: editing ? `Editar ${from!.label}` : 'Novo domínio',
        submit: editing ? 'Salvar' : 'Criar domínio',
        initial,
        fields: () => [
          {
            ...nome,
            help: editing
              ? `Renomear não muda o type Dgraph do ${what}`
              : 'Também nomeia o type Dgraph das instâncias',
          },
          { name: 'categoria', label: 'Categoria', kind: 'text', list: CATEGORIAS },
          { name: 'descricao', label: 'Descrição', kind: 'textarea' },
        ],
        request: (v) => {
          if (!nomeReq(v)) return null
          if (!editing)
            return {
              method: 'POST',
              path: '/kosmos/dominios',
              body: {
                nome: nomeReq(v),
                categoria: v.categoria || 'Funcional',
                descricao: v.descricao || null,
              },
            }
          return {
            method: 'PATCH',
            path: `/kosmos/dominios/${from!.key}`,
            body: changed(v, initial, {
              nome: (x) => ({ nome: String(x).trim() }),
              categoria: (x) => ({ categoria: x }),
              descricao: (x) => ({ descricao: x }),
            }),
          }
        },
      }
    }
    case 'k-campo':
    case 'k-editar-campo': {
      const editing = kind === 'k-editar-campo'
      const initial = editing
        ? { nome: String(row!.campo), tipo: String(row!.tipo), alvo: null, obrigatorio: false }
        : { nome: '', tipo: 'text', alvo: null, obrigatorio: false }
      return {
        title: editing ? `Editar ${row!.campo}` : `Novo campo em ${from!.label}`,
        submit: editing ? 'Salvar' : 'Criar campo',
        initial,
        fields: (v) => [
          {
            ...nome,
            help: editing ? 'O predicado mantém o nome original' : 'Gera kosmos.<Nome>_<hash> no schema',
          },
          {
            name: 'tipo',
            label: 'Tipo',
            kind: 'select',
            required: true,
            options: FIELD_TYPES,
            help: editing ? 'Bloqueado se o predicado já tem valores' : undefined,
          },
          ...(v.tipo === 'selector'
            ? [
                {
                  name: 'alvo',
                  label: 'Aponta para o domínio',
                  kind: 'search' as const,
                  required: !editing,
                  help: editing && row!.destino ? `Hoje: ${row!.destino}` : undefined,
                  search: { kind: 'dominio' as const },
                },
              ]
            : []),
          ...(editing
            ? []
            : [{ name: 'obrigatorio', label: 'Obrigatório', kind: 'bool' as const }]),
        ],
        label: (v) => String(v.nome || 'novo'),
        request: (v) => {
          if (!nomeReq(v)) return null
          if (!editing) {
            if (v.tipo === 'selector' && refId(v.alvo) == null) return null
            return {
              method: 'POST',
              path: `/kosmos/dominios/${from!.key}/campos`,
              body: {
                nome: nomeReq(v),
                tipo: v.tipo,
                alvo_id: v.tipo === 'selector' ? refId(v.alvo) : null,
                obrigatorio: Boolean(v.obrigatorio),
              },
            }
          }
          return {
            method: 'PATCH',
            path: `/kosmos/campos/${row!.campo_id}`,
            body: changed(v, initial, {
              nome: (x) => ({ nome: String(x).trim() }),
              tipo: (x) => ({ tipo: x }),
              alvo: (x) => (refId(x) != null ? { alvo_id: refId(x) } : {}),
            }),
          }
        },
      }
    }
    case 'k-instancia':
      return instanciaSpec(draft, false)
    case 'k-editar-instancia':
      return instanciaSpec(draft, true)
    case 'k-tipo-relacao': {
      const sujeito = from?.type === 'Dominio' ? { id: from.key, nome: from.label } : null
      return {
        title: 'Novo tipo de relação',
        submit: 'Criar tipo de relação',
        initial: { nome: '', sujeito, objeto: null, categoria: 'Funcional', descricao: '' },
        fields: () => [
          nome,
          { name: 'sujeito', label: 'Domínio do sujeito', kind: 'search', required: true, search: { kind: 'dominio' } },
          { name: 'objeto', label: 'Domínio do objeto', kind: 'search', required: true, search: { kind: 'dominio' } },
          { name: 'categoria', label: 'Categoria', kind: 'text', list: CATEGORIAS },
          { name: 'descricao', label: 'Descrição', kind: 'textarea' },
        ],
        label: (v) => String(v.nome || 'novo'),
        request: (v) =>
          nomeReq(v) && refId(v.sujeito) != null && refId(v.objeto) != null
            ? {
                method: 'POST',
                path: '/kosmos/relacoes/tipos',
                body: {
                  nome: nomeReq(v),
                  sujeito_id: refId(v.sujeito),
                  objeto_id: refId(v.objeto),
                  categoria: v.categoria || 'Funcional',
                  descricao: v.descricao || null,
                },
              }
            : null,
      }
    }
    case 'k-relacao':
      return relacaoKosmosSpec(draft)
    case 's-tipo':
    case 's-editar-tipo': {
      const editing = kind === 's-editar-tipo'
      const atual = editing
        ? await request<TipoDgraph>(`/schema/tipos/${encodeURIComponent(from!.label)}`)
        : null
      const initial = {
        nome: atual?.nome ?? '',
        predicados: atual?.predicados ?? [predicadoVazio('')],
      }
      return {
        title: editing ? `Editar ${from!.label}` : 'Novo type Dgraph',
        submit: editing ? 'Alterar schema' : 'Criar type',
        initial,
        fields: () => [
          editing
            ? { name: 'nome', label: 'Type', kind: 'static', help: from!.label }
            : {
                ...nome,
                label: 'Type',
                placeholder: 'loja.Produto',
                pattern: '[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)*',
                help: 'dgraph.* e kosmos.* são geridos por outros módulos',
              },
          {
            name: 'predicados',
            label: 'Predicados',
            kind: 'predicados',
            required: true,
            help: editing ? 'Quem sai deixa o type; os dados ficam' : undefined,
          },
        ],
        errorField: (name) => (name.startsWith('predicados') ? 'predicados' : name),
        request: (v) => {
          const preds = (v.predicados as Predicado[]).filter((p) => p.nome.trim())
          if (!preds.length || (!editing && !nomeReq(v))) return null
          return editing
            ? {
                method: 'PUT',
                path: `/schema/tipos/${encodeURIComponent(from!.label)}`,
                body: { predicados: preds },
              }
            : { method: 'POST', path: '/schema/tipos', body: { nome: nomeReq(v), predicados: preds } }
        },
      }
    }
    case 'inativar':
    case 'reativar':
      return statusSpec(draft)
  }
}

function statusSpec(draft: Draft): Spec {
  const { kind, db, from, row } = draft
  const status = kind === 'inativar' ? 'inactive' : 'active'
  const nome = from?.label ?? String(row?.nome ?? row?.campo ?? row?.via ?? row?.tipo ?? '')
  let req: WriteRequest
  if (db === 'schema') {
    req = { method: 'DELETE', path: `/schema/tipos/${encodeURIComponent(from!.label)}` }
  } else if (db === 'ontologia') {
    const relacao = row?.relacao_id ?? (row?.tipo === 'Relacao' ? row.id : null)
    const path =
      relacao != null
        ? `/ontologia/relacoes/${relacao}`
        : `/ontologia/${(from?.type ?? row?.tipo) === 'Classe' ? 'classes' : 'individuos'}/${from?.key ?? row?.id}`
    req = { method: 'PUT', path: `${path}/status`, body: { status } }
  } else {
    const id = from?.key ?? row?.relacao_id ?? row?.campo_id ?? row?.id
    req = { method: 'PUT', path: `/kosmos/nos/${id}/status`, body: { status } }
  }
  const what = row?.relacao_id != null ? 'a relação' : row?.campo_id != null ? 'o campo' : ''
  return {
    title:
      db === 'schema'
        ? `Remover o type ${nome}`
        : `${kind === 'inativar' ? 'Inativar' : 'Reativar'} ${what} ${nome}`.replace(/\s+/g, ' '),
    submit: db === 'schema' ? 'Remover type' : kind === 'inativar' ? 'Inativar' : 'Reativar',
    initial: {},
    fields: () => [],
    request: () => req,
  }
}

/* Impact, as the API counts it, in words. */
const IMPACTO: Record<string, (n: number) => string> = {
  instancias: (n) => `${n} ${n === 1 ? 'instância' : 'instâncias'}`,
  individuos: (n) => `${n} ${n === 1 ? 'indivíduo' : 'indivíduos'}`,
  subclasses: (n) => `${n} ${n === 1 ? 'subclasse' : 'subclasses'}`,
  relacoes: (n) => `${n} ${n === 1 ? 'relação' : 'relações'}`,
  valores: (n) => `${n} ${n === 1 ? 'valor' : 'valores'}`,
  nos: (n) => `${n} ${n === 1 ? 'nó' : 'nós'}`,
}
const count = new Intl.NumberFormat('pt-BR')

function impactText(kind: string, db: string, impacto: Record<string, number>) {
  const parts = Object.entries(impacto).map(([k, n]) =>
    (IMPACTO[k] ?? ((x: number) => `${x} ${k}`))(n).replace(String(n), count.format(n)),
  )
  if (!parts.length) return null
  if (db === 'schema') return `${parts.join(' e ')} deixam de ter este type; predicados e dados ficam.`
  return kind === 'inativar'
    ? `${parts.join(' e ')} também saem das consultas.`
    : null
}

/* Controls -------------------------------------------------------------- */

function SearchInput({
  id,
  spec,
  value,
  onChange,
  invalid,
  describedBy,
}: {
  id: string
  spec: SearchSpec
  value: unknown
  onChange: (v: unknown) => void
  invalid: boolean
  describedBy?: string
}) {
  const picked: Ref[] = spec.multiple
    ? ((value as Ref[]) ?? [])
    : value
      ? [value as Ref]
      : []
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<Ref[]>([])
  const [active, setActive] = useState(0)
  const [state, setState] = useState<'idle' | 'loading' | 'short' | 'none'>('idle')
  const listId = `${id}-list`
  const showInput = spec.multiple || picked.length === 0

  useEffect(() => {
    if (!open) return
    const needsText = spec.kind === 'instancia' && spec.dominio == null
    if (needsText && q.trim().length < 3) {
      setOptions([])
      setState('short')
      return
    }
    const ctrl = new AbortController()
    setState('loading')
    const timer = setTimeout(() => {
      search(spec.kind, q.trim(), { dominio: spec.dominio, signal: ctrl.signal })
        .then((found) => {
          const ok = found.filter(
            (r) => !spec.aceitos || !r.dominio || spec.aceitos.includes(r.dominio),
          )
          setOptions(ok)
          setActive(0)
          setState(ok.length ? 'idle' : 'none')
        })
        .catch(() => {})
    }, 180)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // aceitos is rebuilt on every render; its content is the dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, open, spec.kind, spec.dominio, spec.aceitos?.join()])
  const choices = options.filter((o) => !picked.some((p) => p.id === o.id))

  const pick = (ref: Ref) => {
    onChange(spec.multiple ? [...picked, ref] : ref)
    setQ('')
    setOpen(false)
  }
  const remove = (ref: Ref) =>
    onChange(spec.multiple ? picked.filter((p) => p.id !== ref.id) : null)

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActive((a) => Math.min(a + 1, choices.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (event.key === 'Enter' && open && choices[active]) {
      event.preventDefault()
      pick(choices[active])
    } else if (event.key === 'Escape' && open) {
      // Closing the list must not also discard the draft.
      event.stopPropagation()
      event.nativeEvent.stopImmediatePropagation()
      setOpen(false)
    } else if (event.key === 'Backspace' && !q && picked.length) {
      remove(picked[picked.length - 1])
    }
  }

  return (
    <div className="combo">
      {picked.length > 0 && (
        <ul className="chips">
          {picked.map((ref) => (
            <li key={ref.id} className="chip">
              <span>{ref.nome}</span>
              {ref.dominio && <span className="chip-meta">{ref.dominio}</span>}
              <button
                type="button"
                aria-label={`Remover ${ref.nome}`}
                onClick={() => remove(ref)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {showInput && (
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && choices[active] ? `${listId}-${active}` : undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          value={q}
          placeholder={spec.kind === 'dominio' ? 'Buscar domínio' : 'Buscar'}
          onChange={(event) => {
            setQ(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKey}
        />
      )}
      {open && showInput && (
        <ul className="combo-list" id={listId} role="listbox">
          {choices.map((ref, index) => (
            <li
              key={ref.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault()
                pick(ref)
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span>{ref.nome}</span>
              {ref.dominio && ref.dominio !== 'Dominio' && (
                <span className="chip-meta">{ref.dominio}</span>
              )}
            </li>
          ))}
          {(state !== 'idle' || (options.length > 0 && !choices.length)) && (
            <li className="combo-note" role="presentation">
              {state === 'loading'
                ? 'Buscando…'
                : state === 'short'
                  ? 'Digite 3 letras do apelido'
                  : state === 'none' || !choices.length
                    ? 'Nada encontrado'
                    : ''}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}

function PairsInput({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const pairs = (value as [string, string][]) ?? []
  const set = (index: number, at: 0 | 1, text: string) =>
    onChange(pairs.map((p, i) => (i === index ? (at ? [p[0], text] : [text, p[1]]) : p)))
  return (
    <div className="pairs">
      {pairs.map(([k, v], index) => (
        <div key={index} className="pair">
          <input
            aria-label={`Chave ${index + 1}`}
            value={k}
            placeholder="chave"
            onChange={(e) => set(index, 0, e.target.value)}
          />
          <input
            aria-label={`Valor ${index + 1}`}
            value={v}
            placeholder="valor"
            onChange={(e) => set(index, 1, e.target.value)}
          />
          <button
            type="button"
            className="btn btn-quiet btn-icon"
            aria-label={`Remover atributo ${k || index + 1}`}
            onClick={() => onChange(pairs.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-quiet" onClick={() => onChange([...pairs, ['', '']])}>
        + Atributo
      </button>
    </div>
  )
}

function PredicadosInput({
  value,
  onChange,
  prefix,
}: {
  value: unknown
  onChange: (v: unknown) => void
  prefix: string
}) {
  const preds = (value as Predicado[]) ?? []
  const set = (index: number, patch: Partial<Predicado>) =>
    onChange(preds.map((p, i) => (i === index ? { ...p, ...patch } : p)))
  return (
    <div className="preds">
      {preds.map((p, index) => (
        <fieldset key={index} className="pred">
          <legend className="sr-only">Predicado {index + 1}</legend>
          <div className="pred-row">
            <input
              aria-label={`Nome do predicado ${index + 1}`}
              className="mono"
              value={p.nome}
              placeholder={`${prefix || 'loja.Produto'}.nome`}
              onChange={(e) => set(index, { nome: e.target.value })}
            />
            <select
              aria-label={`Tipo do predicado ${index + 1}`}
              value={p.tipo}
              onChange={(e) =>
                set(index, {
                  tipo: e.target.value,
                  indices: [],
                  reverse: e.target.value === 'uid' && p.reverse,
                })
              }
            >
              {DGRAPH_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-quiet btn-icon"
              aria-label={`Remover ${p.nome || `predicado ${index + 1}`}`}
              onClick={() => onChange(preds.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
          <div className="pred-flags">
            <label>
              <input
                type="checkbox"
                checked={p.lista}
                onChange={(e) => set(index, { lista: e.target.checked })}
              />
              lista
            </label>
            {p.tipo === 'uid' && (
              <label>
                <input
                  type="checkbox"
                  checked={p.reverse}
                  onChange={(e) => set(index, { reverse: e.target.checked })}
                />
                @reverse
              </label>
            )}
            {TOKENIZERS[p.tipo].map((tok) => (
              <label key={tok}>
                <input
                  type="checkbox"
                  checked={p.indices.includes(tok)}
                  onChange={(e) =>
                    set(index, {
                      indices: e.target.checked
                        ? [...p.indices, tok]
                        : p.indices.filter((t) => t !== tok),
                    })
                  }
                />
                {tok}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <button
        type="button"
        className="btn btn-quiet"
        onClick={() => onChange([...preds, predicadoVazio(prefix ? `${prefix}.` : '')])}
      >
        + Predicado
      </button>
    </div>
  )
}

function display(v: unknown): string {
  if (!filled(v)) return '—'
  if (Array.isArray(v))
    return v.map((x) => (typeof x === 'object' && x ? ((x as Ref).nome ?? JSON.stringify(x)) : String(x))).join(', ')
  if (typeof v === 'object') return (v as Ref).nome ?? JSON.stringify(v)
  if (typeof v === 'boolean') return v ? 'sim' : 'não'
  return String(v)
}

/* Panel ----------------------------------------------------------------- */

export interface DraftPanelProps {
  draft: Draft
  onDone: (result: WriteResult) => void
  onCancel: () => void
  onLabel: (label: string) => void
  /** Set by the panel: submits from a global ⌘↵. */
  submitRef: MutableRefObject<(() => void) | null>
  /** Set by the panel: whether Esc would lose typed values. */
  dirtyRef: MutableRefObject<boolean>
  armed: boolean
}

export function DraftPanel({
  draft,
  onDone,
  onCancel,
  onLabel,
  submitRef,
  dirtyRef,
  armed,
}: DraftPanelProps) {
  const [spec, setSpec] = useState<Spec | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [values, setValues] = useState<Values>({})
  const [preview, setPreview] = useState<WriteResult | null>(null)
  const [previewError, setPreviewError] = useState<ApiError | null>(null)
  const [submitError, setSubmitError] = useState<ApiError | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('')
  const [reloads, setReloads] = useState(0)
  const baseId = useId()
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    let alive = true
    setSpec(null)
    setLoadError(null)
    setSubmitError(null)
    setAttempted(false)
    buildSpec(draft)
      .then((s) => {
        if (!alive) return
        setSpec(s)
        setValues(s.initial)
      })
      .catch((e) => alive && setLoadError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [draft, reloads])

  // First field gets focus once the form exists.
  useEffect(() => {
    if (!spec) return
    const first = formRef.current?.querySelector<HTMLElement>(
      'input:not([type=checkbox]), select, textarea, button.btn-primary',
    )
    first?.focus()
  }, [spec])

  const req = useMemo(() => (spec ? spec.request(values) : null), [spec, values])
  const dirty = spec ? !same(values, spec.initial) : false
  dirtyRef.current = dirty

  useEffect(() => {
    if (spec?.label) onLabel(spec.label(values))
    else if (typeof values.nome === 'string') onLabel(values.nome || 'novo')
  }, [spec, values, onLabel])

  // Preview: the API builds the exact mutation with dry_run.
  useEffect(() => {
    if (!req) {
      setPreview(null)
      setPreviewError(null)
      return
    }
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      write(req, true, ctrl.signal)
        .then((r) => {
          setPreview(r)
          setPreviewError(null)
        })
        .catch((e) => {
          if (e instanceof ApiError) {
            setPreview(null)
            setPreviewError(e)
          }
        })
    }, 280)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [req])

  const submit = useCallback(async () => {
    if (!spec || saving) return
    setAttempted(true)
    if (!req) return
    setSaving(true)
    setSubmitError(null)
    try {
      onDone(await write(req, false))
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e : new ApiError(500, String(e)))
    } finally {
      setSaving(false)
    }
  }, [spec, req, saving, onDone])
  submitRef.current = () => void submit()

  if (loadError)
    return (
      <section className="panel-section draft">
        <p className="query-error" role="alert">
          <strong>Não deu para abrir o formulário</strong>
          <span>{loadError}</span>
        </p>
        <button type="button" className="btn" onClick={onCancel}>
          Fechar
        </button>
      </section>
    )
  if (!spec)
    return (
      <section className="panel-section draft">
        <div className="skeleton" aria-hidden="true">
          {Array.from({ length: 4 }, (_, i) => (
            <span key={i} />
          ))}
        </div>
      </section>
    )

  const errorSource = submitError ?? previewError
  const errors: Record<string, string> = {}
  for (const f of errorSource?.fields ?? []) {
    const name = spec.errorField?.(f.name) ?? API_FIELD[f.name] ?? f.name
    errors[name] = errors[name] ? `${errors[name]}; ${f.detail}` : f.detail
  }
  const fields = spec.fields(values)
  const missing = fields.filter((f) => f.required && !filled(values[f.name]))
  const shown = (f: Field) =>
    attempted ||
    submitError != null ||
    (!same(values[f.name], spec.initial[f.name]) && filled(values[f.name]))
  const generalError = errorSource && !errorSource.fields.length ? errorSource : null
  const isEdit = EDITS.has(draft.kind)
  const isStatus = draft.kind === 'inativar' || draft.kind === 'reativar'
  const longForm = fields.length > 12
  const visible = longForm && filter
    ? fields.filter(
        (f) => f.label.toLowerCase().includes(filter.toLowerCase()) || errors[f.name],
      )
    : fields
  const diff = isEdit && !isStatus
    ? fields
        .filter((f) => f.kind !== 'static' && !same(values[f.name], spec.initial[f.name]))
        .map((f) => [f.label, display(spec.initial[f.name]), display(values[f.name])] as const)
    : []
  const impact = preview ? impactText(draft.kind, draft.db, preview.impacto) : null

  const control = (f: Field) => {
    const id = `${baseId}-${f.name}`
    const error = shown(f) ? errors[f.name] : undefined
    const describedBy = [f.help && `${id}-help`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
    const set = (v: unknown) => setValues((old) => ({ ...old, [f.name]: v }))
    const common = {
      id,
      'aria-invalid': error ? true : undefined,
      'aria-describedby': describedBy,
      'aria-required': f.required || undefined,
    }
    let input
    switch (f.kind) {
      case 'static':
        input = null
        break
      case 'textarea':
        input = (
          <textarea {...common} rows={3} value={String(values[f.name] ?? '')} onChange={(e) => set(e.target.value)} />
        )
        break
      case 'number':
        input = (
          <input {...common} type="number" step="any" value={String(values[f.name] ?? '')} onChange={(e) => set(e.target.value)} />
        )
        break
      case 'date':
        input = (
          <input {...common} type="date" value={String(values[f.name] ?? '')} onChange={(e) => set(e.target.value)} />
        )
        break
      case 'bool':
        input = (
          <select
            {...common}
            value={values[f.name] === true ? 'sim' : values[f.name] === false ? 'nao' : ''}
            onChange={(e) => set(e.target.value === '' ? '' : e.target.value === 'sim')}
          >
            <option value="">—</option>
            <option value="sim">Sim</option>
            <option value="nao">Não</option>
          </select>
        )
        break
      case 'select':
        input = (
          <select {...common} value={String(values[f.name] ?? '')} onChange={(e) => set(e.target.value)}>
            {!values[f.name] && <option value="">Escolha</option>}
            {f.options?.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        )
        break
      case 'search':
        input = (
          <SearchInput
            id={id}
            spec={f.search!}
            value={values[f.name]}
            onChange={set}
            invalid={Boolean(error)}
            describedBy={describedBy}
          />
        )
        break
      case 'pairs':
        input = <PairsInput value={values[f.name]} onChange={set} />
        break
      case 'predicados':
        input = (
          <PredicadosInput value={values[f.name]} onChange={set} prefix={String(values.nome ?? '')} />
        )
        break
      default:
        input = (
          <>
            <input
              {...common}
              value={String(values[f.name] ?? '')}
              placeholder={f.placeholder}
              pattern={f.pattern}
              list={f.list ? `${id}-list` : undefined}
              autoComplete="off"
              className={f.pattern ? 'mono' : undefined}
              onChange={(e) => set(e.target.value)}
            />
            {f.list && (
              <datalist id={`${id}-list`}>
                {f.list.map((o) => (
                  <option key={o} value={o} />
                ))}
              </datalist>
            )}
          </>
        )
    }
    const grouped = f.kind === 'pairs' || f.kind === 'predicados'
    return (
      <div key={f.name} className="field" data-kind={f.kind}>
        {grouped || f.kind === 'static' ? (
          <span className="field-label" id={`${id}-label`}>
            {f.label}
            {f.required && <span className="req" aria-hidden="true"> *</span>}
          </span>
        ) : (
          <label className="field-label" htmlFor={id}>
            {f.label}
            {f.required && <span className="req" aria-hidden="true"> *</span>}
          </label>
        )}
        {input}
        {f.help && (
          <span className="field-help" id={`${id}-help`}>
            {f.help}
          </span>
        )}
        {error && (
          <span className="field-error" id={`${id}-error`}>
            {error}
          </span>
        )}
      </div>
    )
  }

  return (
    <>
      <section className="panel-section draft" aria-labelledby={`${baseId}-title`}>
        <h2 className="eyebrow">
          {isStatus ? 'Status' : isEdit ? 'Edição' : 'Rascunho'} · {DB_LABEL[draft.db]}
        </h2>
        <p className="draft-title" id={`${baseId}-title`}>
          {spec.title}
        </p>
        <form
          ref={formRef}
          className="draft-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
              event.preventDefault()
              void submit()
            }
          }}
        >
          {longForm && (
            <input
              className="field-filter"
              type="search"
              aria-label="Filtrar campos"
              placeholder={`Filtrar ${fields.length} campos`}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          )}
          {visible.map(control)}

          {diff.length > 0 && (
            <dl className="diff" aria-label="Alterações">
              {diff.map(([label, before, now]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>
                    <s>{before}</s> → <span>{now}</span>
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {isStatus && (
            <p className="draft-impact">
              {impact ??
                (draft.kind === 'inativar' && draft.db !== 'schema'
                  ? 'Nada mais sai das consultas junto.'
                  : draft.kind === 'reativar'
                    ? 'Volta a aparecer nas consultas.'
                    : 'Os predicados e os dados ficam; o type pode ser recriado.')}
            </p>
          )}

          {(generalError || submitError?.status === 409) && (
            <div className="query-error" role="alert">
              <strong>{(submitError ?? generalError)!.message}</strong>
              {(submitError ?? generalError)!.detail && <span>{(submitError ?? generalError)!.detail}</span>}
              {spec.reloadable && submitError?.status === 409 && (
                <button type="button" className="btn" onClick={() => setReloads((n) => n + 1)}>
                  Recarregar
                </button>
              )}
            </div>
          )}
          {attempted && missing.length > 0 && (
            <p className="field-error" role="alert">
              Falta preencher: {missing.map((f) => f.label).join(', ')}
            </p>
          )}

          <div className="draft-actions">
            <button
              type="submit"
              className={draft.kind === 'inativar' ? 'btn btn-primary btn-danger' : 'btn btn-primary'}
              disabled={saving}
              aria-disabled={!req || undefined}
            >
              {saving ? 'Salvando…' : spec.submit}
              <kbd>⌘↵</kbd>
            </button>
            <button type="button" className="btn btn-quiet" onClick={onCancel}>
              Descartar <kbd>Esc</kbd>
            </button>
          </div>
          {armed && (
            <p className="draft-armed" role="status">
              Esc de novo descarta o que você digitou.
            </p>
          )}
        </form>
      </section>

      <section className="panel-section">
        <h2 className="eyebrow">
          {draft.db === 'schema' ? 'Alter · Dgraph' : 'Mutation · Dgraph'}
        </h2>
        {preview ? (
          preview.mutations.length ? (
            preview.mutations.map((m, index) => (
              <pre key={index} className="code code-mutation">
                {m}
              </pre>
            ))
          ) : (
            <p className="panel-empty">Nada mudou ainda.</p>
          )
        ) : (
          <p className="panel-empty">
            {req
              ? previewError
                ? 'A mutation aparece quando os campos acima estiverem válidos.'
                : 'Montando a mutation…'
              : `Preencha ${missing.map((f) => f.label).join(', ') || 'os campos'} para ver a mutation.`}
          </p>
        )}
      </section>
    </>
  )
}
