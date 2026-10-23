/** `draft` only exists client-side: the node being created. */
export type Role = 'focus' | 'result' | 'path' | 'draft'

export interface GraphNode {
  id: string
  type: string
  key: number
  label: string
  role: Role
  props: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  props: Record<string, unknown>
}

export type Item = Record<string, unknown>

export interface GraphResult {
  queries: string[]
  nodes: GraphNode[]
  edges: GraphEdge[]
  items: Item[]
}

export interface FieldError {
  name: string
  detail: string
}

export class ApiError extends Error {
  /** HTTP status; 0 when the API itself could not be reached. */
  status: number
  detail?: string
  fields: FieldError[]

  constructor(status: number, message: string, detail?: string, fields: FieldError[] = []) {
    super(message)
    this.status = status
    this.detail = detail
    this.fields = fields
  }
}

export async function request<T>(
  path: string,
  init?: { method?: string; body?: unknown; signal?: AbortSignal },
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: init?.method ?? 'GET',
      signal: init?.signal,
      headers: init?.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'A Graphs API não respondeu')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.message ?? response.statusText,
      body?.detail ?? undefined,
      // Pydantic prefixes request fields with "body."
      (body?.fields ?? []).map((f: FieldError) => ({
        ...f,
        name: f.name.replace(/^body\./, ''),
      })),
    )
  }
  return body.data as T
}

export const fetchGraph = (path: string) => request<GraphResult>(path)
