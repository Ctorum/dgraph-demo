import { request } from './api'

export interface Undo {
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body: Record<string, unknown> | null
}

export interface WriteResult {
  applied: boolean
  /** JSON mutations and schema DDL, in the order they run. */
  mutations: string[]
  queries: string[]
  /** Graph node of what was written, e.g. "Classe:18". */
  node: string | null
  key: number | null
  impacto: Record<string, number>
  desfazer: Undo | null
}

export interface WriteRequest {
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body?: unknown
}

export function write(req: WriteRequest, dryRun: boolean, signal?: AbortSignal) {
  const sep = req.path.includes('?') ? '&' : '?'
  return request<WriteResult>(dryRun ? `${req.path}${sep}dry_run=true` : req.path, {
    method: req.method,
    body: req.body,
    signal,
  })
}

export const undo = (u: Undo) =>
  write({ method: u.method, path: u.path, body: u.body ?? undefined }, false)

/** A picked vertex: what search fields hold. */
export interface Ref {
  id: number
  nome: string
  dominio?: string
}

export interface CampoForm {
  id: number
  nome: string
  tipo: string
  obrigatorio: boolean
  ordem: number
  alvos: { id: number; nome: string; abstrato: boolean }[]
  /** Domains the selector accepts; null means any. */
  aceitos: { id: number; nome: string }[] | null
  valor: unknown
}

export interface Formulario {
  dominio: { id: number; nome: string }
  campos: CampoForm[]
  apelido: string | null
  version: number | null
}

export interface TipoRelacao {
  id: number
  nome: string
  campos: CampoForm[]
}

export interface Predicado {
  nome: string
  tipo: string
  lista: boolean
  indices: string[]
  reverse: boolean
}

export interface TipoDgraph {
  nome: string
  predicados: Predicado[]
}

export const search = (
  kind: 'classe' | 'individuo' | 'instancia' | 'dominio',
  q: string,
  opts: { dominio?: number; signal?: AbortSignal } = {},
) => {
  const params = new URLSearchParams({ q })
  if (kind === 'classe' || kind === 'individuo') {
    params.set('tipo', kind === 'classe' ? 'Classe' : 'Individuo')
    return request<Ref[]>(`/ontologia/busca?${params}`, { signal: opts.signal })
  }
  params.set('tipo', kind)
  if (opts.dominio != null) params.set('dominio_id', String(opts.dominio))
  return request<Ref[]>(`/kosmos/busca?${params}`, { signal: opts.signal })
}
