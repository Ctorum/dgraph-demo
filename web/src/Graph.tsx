import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  NodeToolbar,
  Position,
  ReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { createContext, useContext, useEffect, useMemo, useRef } from 'react'
import type { Connection } from '@xyflow/react'

import type { GraphNode } from './api'
import {
  LABELLED_EDGES,
  NODE_H,
  NODE_W,
  edgeLabel,
  type Placed,
  type Point,
} from './layout'
import { DRAFT_ID, writeLabel, type WriteKey } from './drafts'
import { QUERIES, type Db, type QueryKey } from './queries'

/* Type vocabulary: every vertex class has a shape and a colour, and its name
   is always printed, so the type never depends on colour alone. */

type Shape = 'circle' | 'square' | 'diamond' | 'triangle' | 'hexagon'

const TYPES: Record<string, { shape: Shape; tone: string; mono?: boolean }> = {
  Cliente: { shape: 'circle', tone: 'blue' },
  Conta: { shape: 'square', tone: 'green' },
  Dispositivo: { shape: 'diamond', tone: 'amber', mono: true },
  IP: { shape: 'triangle', tone: 'teal', mono: true },
  Telefone: { shape: 'hexagon', tone: 'clay', mono: true },
  Usuario: { shape: 'circle', tone: 'blue' },
  Produto: { shape: 'square', tone: 'amber' },
  Categoria: { shape: 'diamond', tone: 'teal' },
  Classe: { shape: 'diamond', tone: 'green' },
  Individuo: { shape: 'circle', tone: 'blue' },
  Dominio: { shape: 'hexagon', tone: 'green' },
  TipoRelacao: { shape: 'diamond', tone: 'clay' },
  Campo: { shape: 'square', tone: 'teal' },
  Tipo: { shape: 'hexagon', tone: 'blue' },
  Predicado: { shape: 'circle', tone: 'teal', mono: true },
}

const FALLBACK_SHAPES: Shape[] = ['circle', 'square', 'diamond', 'triangle']
const FALLBACK_TONES = ['blue', 'green', 'amber', 'teal', 'clay']

/** Kosmos domains are open-ended: the name picks a stable shape and tone. */
function styleOf(type: string) {
  if (TYPES[type]) return TYPES[type]
  let hash = 0
  for (const ch of type) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return {
    shape: FALLBACK_SHAPES[hash % FALLBACK_SHAPES.length],
    tone: FALLBACK_TONES[(hash >>> 3) % FALLBACK_TONES.length],
  }
}

const SHAPES: Record<Shape, string> = {
  circle: 'M6 1a5 5 0 1 1 0 10A5 5 0 0 1 6 1Z',
  square: 'M1.5 1.5h9v9h-9Z',
  diamond: 'M6 .8 11.2 6 6 11.2.8 6Z',
  triangle: 'M6 1.2 11.3 10.8H.7Z',
  hexagon: 'M3.2 1.2h5.6L11.6 6l-2.8 4.8H3.2L.4 6Z',
}

export function Glyph({ type }: { type: string }) {
  const style = styleOf(type)
  return (
    <svg
      className={`glyph tone-${style.tone}`}
      viewBox="0 0 12 12"
      aria-hidden="true"
    >
      <path d={SHAPES[style.shape]} />
    </svg>
  )
}

const count = new Intl.NumberFormat('pt-BR')

/** Long hashes keep their head and tail: enough to compare by eye; names
   get a CSS ellipsis and the full text in the tooltip. */
function display(node: GraphNode) {
  const { label } = node
  return TYPES[node.type]?.mono && label.length > 18 ? `${label.slice(0, 8)}…${label.slice(-4)}` : label
}

/* Graph-level callbacks, shared by every node without re-rendering them. */

export interface GraphActions {
  activate: (node: GraphNode) => void
  run: (query: QueryKey, node: GraphNode) => void
  expand: (groupKey: string) => void
  hover: (id: string | null) => void
  actionsFor: (node: GraphNode) => QueryKey[]
  writesFor: (node: GraphNode) => WriteKey[]
  write: (kind: WriteKey, node: GraphNode) => void
  db: Db
}

const Actions = createContext<GraphActions | null>(null)

type EntityData = {
  node: GraphNode
  selected: boolean
  menuOpen: boolean
  /** Being edited or inactivated in the panel. */
  editing: boolean
  fresh: boolean
  connectable: boolean
  /** Live label of the draft node, typed in the panel. */
  draftLabel?: string
}
type GroupData = { node: GraphNode; groupKey: string; hidden: number }
type RouteData = {
  points: Point[]
  labelAt?: Point
  label: string
  showLabel: boolean
  lit: boolean
  draft: boolean
}

function EntityNode({ data }: NodeProps<Node<EntityData>>) {
  const actions = useContext(Actions)!
  const { node, selected, menuOpen, editing, fresh, connectable, draftLabel } = data
  const queries = actions.actionsFor(node)
  const writes = actions.writesFor(node)
  const hasMenu = queries.length + writes.length > 1 || (!queries.length && writes.length > 0)
  const menu = useRef<HTMLDivElement>(null)
  const risco = Number(node.props.risco ?? 0)
  const isDraft = node.id === DRAFT_ID

  useEffect(() => {
    if (menuOpen) menu.current?.querySelector('button')?.focus()
  }, [menuOpen])

  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={connectable} />
      <button
        type="button"
        className="node"
        data-role={node.role}
        data-action={queries.length > 0 || writes.length > 0}
        data-editing={editing || undefined}
        data-fresh={fresh || undefined}
        data-inactive={node.props.status === 'inactive' || undefined}
        aria-pressed={selected}
        aria-haspopup={hasMenu ? 'menu' : undefined}
        aria-expanded={hasMenu ? menuOpen : undefined}
        title={isDraft ? 'Rascunho: ainda não foi gravado' : node.label}
        disabled={isDraft}
        onClick={() => actions.activate(node)}
        onMouseEnter={() => actions.hover(node.id)}
        onMouseLeave={() => actions.hover(null)}
        onFocus={() => actions.hover(node.id)}
        onBlur={() => actions.hover(null)}
      >
        <Glyph type={node.type} />
        <span className="node-text">
          <span className="node-type">{node.type}</span>
          <span className={TYPES[node.type]?.mono ? 'node-label mono' : 'node-label'}>
            {isDraft ? draftLabel || 'novo' : display(node)}
          </span>
        </span>
        {isDraft && <span className="badge badge-draft">novo</span>}
        {node.props.status === 'inactive' && <span className="badge">inativo</span>}
        {(risco >= 50 || node.props.bloqueado === true) && (
          <span className="badge badge-risk">
            {node.props.bloqueado === true ? 'bloqueado' : `risco ${risco}`}
          </span>
        )}
        {node.props.instancias != null && (
          <span className="badge">{count.format(Number(node.props.instancias))}</span>
        )}
        {node.props.score != null && (
          <span className="badge">×{String(node.props.score)}</span>
        )}
      </button>
      <Handle type="source" position={Position.Right} isConnectable={connectable} />
      {hasMenu && (
        <NodeToolbar isVisible={menuOpen} position={Position.Bottom} offset={6}>
          <div className="node-menu" role="menu" ref={menu}>
            {queries.map((key) => (
              <button
                key={key}
                type="button"
                role="menuitem"
                onClick={() => actions.run(key, node)}
              >
                {QUERIES[key].title}
              </button>
            ))}
            {queries.length > 0 && writes.length > 0 && (
              <hr className="node-menu-sep" aria-hidden="true" />
            )}
            {writes.map((kind) => (
              <button
                key={kind}
                type="button"
                role="menuitem"
                className="node-menu-write"
                onClick={() => actions.write(kind, node)}
              >
                {writeLabel(kind, actions.db)}
              </button>
            ))}
          </div>
        </NodeToolbar>
      )}
    </>
  )
}

function GroupNode({ data }: NodeProps<Node<GroupData>>) {
  const actions = useContext(Actions)!
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <button
        type="button"
        className="node node-group"
        onClick={() => actions.expand(data.groupKey)}
      >
        <Glyph type={data.node.type} />
        <span className="node-text">
          <span className="node-type">{data.node.type}</span>
          <span className="node-label">+{data.hidden} ocultos</span>
        </span>
        <span className="badge">mostrar</span>
      </button>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </>
  )
}

const ARROW = 7

/** Orthogonal ELK route with softened corners and a hand-drawn arrow. */
function RouteEdge({ data }: EdgeProps<Edge<RouteData>>) {
  const { points, labelAt, label, showLabel, lit, draft } = data!
  const geometry = useMemo(() => {
    if (points.length < 2) return null
    const end = points[points.length - 1]
    const prev = points[points.length - 2]
    const len = Math.hypot(end.x - prev.x, end.y - prev.y) || 1
    const ux = (end.x - prev.x) / len
    const uy = (end.y - prev.y) / len
    const base = { x: end.x - ux * ARROW, y: end.y - uy * ARROW }
    const line = [...points.slice(0, -1), base]

    let d = `M${line[0].x},${line[0].y}`
    for (let i = 1; i < line.length - 1; i++) {
      const [a, b, c] = [line[i - 1], line[i], line[i + 1]]
      const r = Math.min(
        8,
        Math.hypot(b.x - a.x, b.y - a.y) / 2,
        Math.hypot(c.x - b.x, c.y - b.y) / 2,
      )
      const inX = Math.sign(b.x - a.x)
      const inY = Math.sign(b.y - a.y)
      const outX = Math.sign(c.x - b.x)
      const outY = Math.sign(c.y - b.y)
      d += ` L${b.x - inX * r},${b.y - inY * r}`
      d += ` Q${b.x},${b.y} ${b.x + outX * r},${b.y + outY * r}`
    }
    d += ` L${base.x},${base.y}`

    const half = ARROW * 0.55
    const arrow =
      `M${end.x},${end.y}` +
      ` L${base.x - uy * half},${base.y + ux * half}` +
      ` L${base.x + uy * half},${base.y - ux * half}Z`

    // Label on the longest straight run, where it collides least.
    let best = 0
    let mid = points[0]
    for (let i = 1; i < points.length; i++) {
      const [a, b] = [points[i - 1], points[i]]
      const run = Math.hypot(b.x - a.x, b.y - a.y)
      if (run > best) {
        best = run
        mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
      }
    }
    return { d, arrow, mid: labelAt ?? mid }
  }, [points, labelAt])

  if (!geometry) return null
  return (
    <g className={['route', lit && 'lit', draft && 'draft'].filter(Boolean).join(' ')}>
      <path className="route-line" d={geometry.d} />
      <path className="route-arrow" d={geometry.arrow} />
      {showLabel && (
        <foreignObject
          x={geometry.mid.x - 60}
          y={geometry.mid.y - 10}
          width={120}
          height={20}
          className="route-label-box"
        >
          <span className="route-label">{label}</span>
        </foreignObject>
      )}
    </g>
  )
}

const nodeTypes = { entity: EntityNode, group: GroupNode }
const edgeTypes = { route: RouteEdge }

export interface GraphViewProps {
  placed: Placed
  actions: GraphActions
  /** Hovered nodes: they, their neighbours and their edges stay lit. */
  hovered: string[]
  selected: string | null
  menuFor: string | null
  editing: string | null
  fresh: string | null
  draftLabel: string
  /** Whether a node can start or end a relation drawn by dragging. */
  canConnect: (node: GraphNode) => boolean
  onConnect: (source: GraphNode, target: GraphNode) => void
}

export function GraphView({
  placed,
  actions,
  hovered,
  selected,
  menuFor,
  editing,
  fresh,
  draftLabel,
  canConnect,
  onConnect,
}: GraphViewProps) {
  const byId = useMemo(() => new Map(placed.nodes.map((p) => [p.node.id, p.node])), [placed])
  const lit = useMemo(() => {
    if (!hovered.length) return null
    const ids = new Set(hovered)
    for (const { edge } of placed.edges) {
      if (hovered.includes(edge.source)) ids.add(edge.target)
      if (hovered.includes(edge.target)) ids.add(edge.source)
    }
    return ids
  }, [hovered, placed])

  const nodes = useMemo(
    (): Node[] =>
      placed.nodes.map(({ node, x, y, group }) => ({
        id: node.id,
        type: group ? 'group' : 'entity',
        position: { x, y },
        width: NODE_W,
        height: NODE_H,
        draggable: false,
        selectable: false,
        className: lit && !lit.has(node.id) ? 'dim' : undefined,
        data: group
          ? { node, groupKey: group.key, hidden: group.hidden }
          : {
              node,
              selected: selected === node.id,
              menuOpen: menuFor === node.id,
              editing: editing === node.id,
              fresh: fresh === node.id,
              connectable: canConnect(node),
              draftLabel: node.id === DRAFT_ID ? draftLabel : undefined,
            },
      })),
    [placed, lit, selected, menuFor, editing, fresh, draftLabel, canConnect],
  )

  const edges = useMemo((): Edge[] => {
    const crowded = placed.edges.length > LABELLED_EDGES
    return placed.edges.map(({ edge, points, labelAt }) => {
      const touches = hovered.includes(edge.source) || hovered.includes(edge.target)
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: 'route',
        selectable: false,
        focusable: false,
        className: lit && !touches ? 'dim' : undefined,
        data: {
          points,
          labelAt,
          label: edgeLabel(edge),
          showLabel: !crowded || touches || edge.props.draft === true,
          lit: touches,
          draft: edge.props.draft === true,
        },
      }
    })
  }, [placed, hovered, lit])

  return (
    <Actions.Provider value={actions}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable
        isValidConnection={(c) => {
          const source = byId.get(c.source)
          const target = byId.get(c.target)
          return Boolean(
            source && target && c.source !== c.target && canConnect(source) && canConnect(target),
          )
        }}
        onConnect={(c: Connection) => {
          const source = byId.get(c.source)
          const target = byId.get(c.target)
          if (source && target) onConnect(source, target)
        }}
        // Handles are small: dropping anywhere on a node also connects.
        onConnectEnd={(event, state) => {
          if (state.isValid || !state.fromNode) return
          const point = 'changedTouches' in event ? event.changedTouches[0] : event
          const id = document
            .elementFromPoint(point.clientX, point.clientY)
            ?.closest<HTMLElement>('.react-flow__node')?.dataset.id
          const source = byId.get(state.fromNode.id)
          const target = id ? byId.get(id) : undefined
          if (source && target && source !== target && canConnect(target)) onConnect(source, target)
        }}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{
          padding: 0.12,
          maxZoom: 1,
          // Keep labels legible on wide screens; phones fit the whole graph.
          minZoom: window.innerWidth < 720 ? 0.2 : 0.6,
        }}
        minZoom={0.15}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        aria-label="Grafo do resultado"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </Actions.Provider>
  )
}
