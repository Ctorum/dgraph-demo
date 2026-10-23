import type { GraphEdge, GraphNode, GraphResult, Item } from './api'
import { KOSMOS_META, dbOf, type Db, type QueryKey } from './queries'
import type { WriteResult } from './writes'

export type WriteKey =
  | 'o-classe-raiz'
  | 'o-subclasse'
  | 'o-individuo'
  | 'o-relacao'
  | 'o-editar-classe'
  | 'o-editar-individuo'
  | 'k-dominio'
  | 'k-editar-dominio'
  | 'k-campo'
  | 'k-editar-campo'
  | 'k-instancia'
  | 'k-editar-instancia'
  | 'k-tipo-relacao'
  | 'k-relacao'
  | 's-tipo'
  | 's-editar-tipo'
  | 'inativar'
  | 'reativar'

/** Something being created, edited or inactivated, not saved yet. */
export interface Draft {
  kind: WriteKey
  db: Db
  /** Node it starts from, or the node edited or inactivated. */
  from?: GraphNode
  /** Relation drafts: the other end, when picked on the canvas. */
  target?: GraphNode
  /** Edits and inactivations started from a result row. */
  row?: Item
}

export const DB_LABEL: Record<Db, string> = {
  fraude: 'Fraude',
  recomendacao: 'Recomendação',
  ontologia: 'Ontologia',
  kosmos: 'Kosmos',
  schema: 'Schema',
}

export function writeLabel(kind: WriteKey, db: Db) {
  if (kind === 'inativar' && db === 'schema') return 'Remover type'
  return {
    'o-classe-raiz': '+ Classe raiz',
    'o-subclasse': '+ Subclasse',
    'o-individuo': '+ Indivíduo',
    'o-relacao': '+ Relação',
    'o-editar-classe': 'Editar',
    'o-editar-individuo': 'Editar',
    'k-dominio': '+ Domínio',
    'k-editar-dominio': 'Editar',
    'k-campo': '+ Campo',
    'k-editar-campo': 'Editar campo',
    'k-instancia': '+ Instância',
    'k-editar-instancia': 'Editar',
    'k-tipo-relacao': '+ Tipo de relação',
    'k-relacao': '+ Relação',
    's-tipo': '+ Type',
    's-editar-tipo': 'Editar predicados',
    inativar: 'Inativar',
    reativar: 'Reativar',
  }[kind]
}

/** Creations that start from nothing, offered in the rail. */
export const ROOT_WRITES: Partial<Record<Db, WriteKey[]>> = {
  ontologia: ['o-classe-raiz'],
  kosmos: ['k-dominio', 'k-tipo-relacao'],
  schema: ['s-tipo'],
}

export const inactive = (node: GraphNode) => node.props.status === 'inactive'

/** Writes that start from `node`, for a graph read by `from`. */
export function writesFor(node: GraphNode, from: QueryKey): WriteKey[] {
  if (node.role === 'draft' || node.id.startsWith('group:')) return []
  const db = dbOf(from)
  if (inactive(node)) return db === 'schema' ? [] : ['reativar']
  if (db === 'ontologia') {
    if (node.type === 'Classe')
      return ['o-subclasse', 'o-individuo', 'o-editar-classe', 'inativar']
    if (node.type === 'Individuo') return ['o-relacao', 'o-editar-individuo', 'inativar']
  }
  if (db === 'kosmos') {
    if (node.type === 'Dominio')
      return ['k-instancia', 'k-campo', 'k-tipo-relacao', 'k-editar-dominio', 'inativar']
    if (node.type === 'TipoRelacao') return ['k-campo', 'k-editar-dominio', 'inativar']
    if (!KOSMOS_META.has(node.type)) return ['k-relacao', 'k-editar-instancia', 'inativar']
  }
  if (db === 'schema' && node.type === 'Tipo') return ['s-editar-tipo', 'inativar']
  return []
}

/** Writes on a result row: relations and fields have no node of their own. */
export function rowWrites(item: Item, query: QueryKey): WriteKey[] {
  if (query === 'oinativos' || query === 'kinativos') return ['reativar']
  if (item.campo_id != null) return ['k-editar-campo', 'inativar']
  if (item.relacao_id != null) return ['inativar']
  return []
}

/** Relation drafts can start by dragging one instance onto another. */
export function connectable(node: GraphNode, from: QueryKey) {
  if (node.role === 'draft' || node.id.startsWith('group:') || inactive(node)) return false
  const db = dbOf(from)
  if (db === 'ontologia') return node.type === 'Individuo'
  return db === 'kosmos' && !KOSMOS_META.has(node.type)
}

export const DRAFT_ID = 'draft'

/** The node (and edge) a draft adds to the drawing while it is open. */
function overlay(draft: Draft): { node?: GraphNode; edge?: [string, string, string] } {
  const { kind, from, target } = draft
  const node = (type: string): GraphNode => ({
    id: DRAFT_ID,
    type,
    key: 0,
    label: 'novo',
    role: 'draft',
    props: {},
  })
  switch (kind) {
    case 'o-classe-raiz':
      return { node: node('Classe') }
    case 'o-subclasse':
      return { node: node('Classe'), edge: [DRAFT_ID, from!.id, 'SubclasseDe'] }
    case 'o-individuo':
      return { node: node('Individuo'), edge: [DRAFT_ID, from!.id, 'InstanciaDe'] }
    case 'o-relacao':
    case 'k-relacao':
      return target
        ? { edge: [from!.id, target.id, 'nova relação'] }
        : { node: node(kind === 'o-relacao' ? 'Individuo' : 'Instância'), edge: [from!.id, DRAFT_ID, 'nova relação'] }
    case 'k-dominio':
      return { node: node('Dominio') }
    case 'k-campo':
      return { node: node('Campo'), edge: [from!.id, DRAFT_ID, 'hasField'] }
    case 'k-instancia':
      return { node: node(from!.label), edge: [DRAFT_ID, from!.id, 'instanceOf'] }
    case 'k-tipo-relacao':
      return from
        ? { node: node('TipoRelacao'), edge: [DRAFT_ID, from.id, 'sujeito'] }
        : { node: node('TipoRelacao') }
    case 's-tipo':
      return { node: node('Tipo') }
    default:
      return {}
  }
}

export function withDraft(result: GraphResult, draft: Draft | null): GraphResult {
  if (!draft) return result
  const { node, edge } = overlay(draft)
  if (!node && !edge) return result
  // After navigating away the starting node may be gone from the drawing.
  const present = new Set([...result.nodes.map((n) => n.id), DRAFT_ID])
  const edges: GraphEdge[] =
    edge && present.has(edge[0]) && present.has(edge[1])
    ? [
        {
          id: `${DRAFT_ID}-edge`,
          source: edge[0],
          target: edge[1],
          label: edge[2],
          props: { draft: true },
        },
      ]
    : []
  return {
    ...result,
    nodes: node ? [...result.nodes, node] : result.nodes,
    edges: [...result.edges, ...edges],
  }
}

/** Where to go once the write lands; null reruns the query on screen. */
export function after(
  draft: Draft,
  result: WriteResult,
): { query: QueryKey; id?: number } | null {
  const key = result.key ?? undefined
  switch (draft.kind) {
    case 'o-classe-raiz':
    case 'o-subclasse':
      return { query: 'ancestrais', id: key }
    case 'o-individuo':
      return { query: 'relacoes', id: key }
    case 'o-relacao':
      return { query: 'relacoes', id: draft.from!.key }
    case 'k-dominio':
    case 'k-tipo-relacao':
      return { query: 'kmodelo', id: key }
    case 'k-campo':
      return { query: 'kmodelo', id: draft.from!.key }
    case 'k-instancia':
      return { query: 'kconexoes', id: key }
    case 'k-relacao':
      return { query: 'kconexoes', id: draft.from!.key }
    case 's-tipo':
      return { query: 'stipos' }
    default:
      return null
  }
}

/** Kinds that edit what is already drawn instead of adding to it. */
export const EDITS = new Set<WriteKey>([
  'o-editar-classe',
  'o-editar-individuo',
  'k-editar-dominio',
  'k-editar-instancia',
  's-editar-tipo',
  'inativar',
  'reativar',
])
