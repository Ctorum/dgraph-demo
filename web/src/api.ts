export type Role = 'focus' | 'result' | 'path'

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

export class ApiError extends Error {
  /** HTTP status; 0 when the API itself could not be reached. */
  status: number
  detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

export async function fetchGraph(path: string): Promise<GraphResult> {
  let response: Response
  try {
    response = await fetch(`/api${path}`)
  } catch {
    throw new ApiError(0, 'A Graphs API não respondeu')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.message ?? response.statusText,
      body?.detail ?? undefined,
    )
  }
  return body.data as GraphResult
}
