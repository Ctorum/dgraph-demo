import ELK from 'elkjs/lib/elk-api.js'
import type { ElkExtendedEdge, ElkNode } from 'elkjs/lib/elk-api.js'
import workerUrl from 'elkjs/lib/elk-worker.min.js?url'

import type { GraphEdge, GraphNode, GraphResult } from './api'

export const NODE_W = 184
export const NODE_H = 44
/** Up to this many edges, every edge label is drawn and laid out by ELK. */
export const LABELLED_EDGES = 10

/** Above this many nodes, big groups of leaves collapse into one node. */
const COLLAPSE_AT = 24
const GROUP_MAX = 5
const GROUP_KEEP = 3

export interface Point {
  x: number
  y: number
}

export interface PlacedNode {
  node: GraphNode
  x: number
  y: number
  /** Set on summary nodes that stand for hidden leaves. */
  group?: { key: string; hidden: number }
}

export interface PlacedEdge {
  edge: GraphEdge
  /** Route from source to target, already oriented for the arrow. */
  points: Point[]
  /** Centre of the label when ELK reserved room for it. */
  labelAt?: Point
}

export interface Placed {
  nodes: PlacedNode[]
  edges: PlacedEdge[]
  width: number
  height: number
}

interface Visible {
  nodes: GraphNode[]
  edges: GraphEdge[]
  groups: Map<string, number>
}

/**
 * Leaves (degree 1) of the same type hanging off the same neighbour are
 * folded into a "+N" node once the graph gets crowded, unless expanded.
 */
function collapse(graph: GraphResult, expanded: Set<string>): Visible {
  const visible: Visible = {
    nodes: graph.nodes,
    edges: graph.edges,
    groups: new Map(),
  }
  if (graph.nodes.length <= COLLAPSE_AT) return visible

  const degree = new Map<string, GraphEdge[]>()
  for (const edge of graph.edges) {
    for (const end of [edge.source, edge.target]) {
      degree.set(end, [...(degree.get(end) ?? []), edge])
    }
  }
  const leaves = new Map<string, GraphNode[]>()
  for (const node of graph.nodes) {
    const edges = degree.get(node.id) ?? []
    if (node.role === 'focus' || edges.length !== 1) continue
    const other =
      edges[0].source === node.id ? edges[0].target : edges[0].source
    const key = `${other}|${node.type}`
    leaves.set(key, [...(leaves.get(key) ?? []), node])
  }

  const hidden = new Set<string>()
  const summaries: GraphNode[] = []
  const summaryEdges: GraphEdge[] = []
  for (const [key, members] of leaves) {
    if (members.length <= GROUP_MAX || expanded.has(key)) continue
    const rest = members.slice(GROUP_KEEP)
    rest.forEach((node) => hidden.add(node.id))
    const id = `group:${key}`
    const [neighbour, type] = key.split('|')
    const sample = degree.get(rest[0].id)![0]
    summaries.push({
      id,
      type,
      key: 0,
      label: `+${rest.length} ${type}`,
      role: 'path',
      props: {},
    })
    summaryEdges.push({
      ...sample,
      id: `${id}-edge`,
      source: sample.source === neighbour ? neighbour : id,
      target: sample.source === neighbour ? id : neighbour,
    })
    visible.groups.set(id, rest.length)
  }
  visible.nodes = [
    ...graph.nodes.filter((n) => !hidden.has(n.id)),
    ...summaries,
  ]
  visible.edges = [
    ...graph.edges.filter((e) => !hidden.has(e.source) && !hidden.has(e.target)),
    ...summaryEdges,
  ]
  return visible
}

/** Undirected BFS depth from the focus node, to read the graph outwards. */
function depthFromFocus(nodes: GraphNode[], edges: GraphEdge[]) {
  const depth = new Map<string, number>()
  const focus = nodes.find((n) => n.role === 'focus')
  if (!focus) return depth
  const neighbours = new Map<string, string[]>()
  for (const { source, target } of edges) {
    neighbours.set(source, [...(neighbours.get(source) ?? []), target])
    neighbours.set(target, [...(neighbours.get(target) ?? []), source])
  }
  depth.set(focus.id, 0)
  const queue = [focus.id]
  while (queue.length) {
    const id = queue.shift()!
    for (const next of neighbours.get(id) ?? []) {
      if (depth.has(next)) continue
      depth.set(next, depth.get(id)! + 1)
      queue.push(next)
    }
  }
  return depth
}

// The layout engine runs in a worker so big graphs never block the UI.
const elk = new ELK({ workerUrl })

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export function edgeLabel(edge: GraphEdge) {
  if (edge.props.valor != null) return brl.format(Number(edge.props.valor))
  return edge.label.replaceAll('_', ' ')
}

export async function place(
  graph: GraphResult,
  direction: 'RIGHT' | 'DOWN',
  expanded: Set<string>,
): Promise<Placed> {
  const visible = collapse(graph, expanded)
  const { edges, groups } = visible
  // Model order drives ELK's ordering inside a layer: best score first.
  const nodes = [...visible.nodes].sort(
    (a, b) => Number(b.props.score ?? 0) - Number(a.props.score ?? 0),
  )
  const labelled = edges.length <= LABELLED_EDGES
  const depth = depthFromFocus(nodes, edges)
  // ELK layers by edge direction; point every edge away from the focus so
  // the drawing reads focus → what it reaches, whatever the stored direction.
  const reversed = new Set(
    edges
      .filter(
        (e) => (depth.get(e.source) ?? 0) > (depth.get(e.target) ?? 0),
      )
      .map((e) => e.id),
  )
  const root: ElkNode = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': direction,
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': '64',
      'elk.layered.spacing.edgeNodeBetweenLayers': '20',
      'elk.spacing.nodeNode': '16',
      'elk.spacing.edgeEdge': '8',
      'elk.spacing.componentComponent': '40',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      // Edges into the same vertex share a trunk, like lines into a station.
      'elk.layered.mergeEdges': 'true',
      'elk.edgeLabels.inline': 'true',
    },
    children: nodes.map((n) => ({ id: n.id, width: NODE_W, height: NODE_H })),
    edges: edges.map(
      (e): ElkExtendedEdge => ({
        id: e.id,
        sources: [reversed.has(e.id) ? e.target : e.source],
        targets: [reversed.has(e.id) ? e.source : e.target],
        labels: labelled
          ? [{ text: edgeLabel(e), width: edgeLabel(e).length * 6.2 + 10, height: 16 }]
          : undefined,
      }),
    ),
  }
  const out = await elk.layout(root)

  const byId = new Map(nodes.map((n) => [n.id, n]))
  const placedEdges = new Map(
    (out.edges ?? []).map((e) => {
      const section = e.sections?.[0]
      const points = section
        ? [section.startPoint, ...(section.bendPoints ?? []), section.endPoint]
        : []
      const label = e.labels?.[0]
      const labelAt =
        label?.x != null && label.y != null
          ? { x: label.x + (label.width ?? 0) / 2, y: label.y + (label.height ?? 0) / 2 }
          : undefined
      return [
        e.id,
        { points: reversed.has(e.id) ? points.reverse() : points, labelAt },
      ] as const
    }),
  )
  return {
    nodes: (out.children ?? []).map((c) => ({
      node: byId.get(c.id)!,
      x: c.x ?? 0,
      y: c.y ?? 0,
      group: groups.has(c.id)
        ? { key: c.id.slice('group:'.length), hidden: groups.get(c.id)! }
        : undefined,
    })),
    edges: edges.map((edge) => ({
      edge,
      points: placedEdges.get(edge.id)?.points ?? [],
      labelAt: placedEdges.get(edge.id)?.labelAt,
    })),
    width: out.width ?? 0,
    height: out.height ?? 0,
  }
}
