import { ReactFlowProvider } from '@xyflow/react'
import {
  Fragment,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { ApiError, fetchGraph, type GraphNode, type GraphResult } from './api'
import { Glyph, GraphView, type GraphActions } from './Graph'
import { place, type Placed } from './layout'
import {
  DATABASES,
  QUERIES,
  actionsFor,
  type QueryDef,
  type QueryKey,
} from './queries'

interface Step {
  query: QueryKey
  id?: number
  /** Label of the vertex the query starts from, e.g. "Cliente 281". */
  focus?: string
}

interface Loaded {
  step: Step
  result: GraphResult
  ms: number
}

type Failure =
  | { kind: 'notfound'; message: string }
  | { kind: 'down'; message: string; retry: Step; keep: number }
  | { kind: 'server'; message: string; detail?: string }

const stepTitle = (step: Step) =>
  step.focus ? `${step.focus} · ${QUERIES[step.query].title}` : QUERIES[step.query].title

const STARTS: Step[] = [
  { query: 'aneis' },
  { query: 'suspeitas' },
  { query: 'produtos', id: 1 },
  { query: 'individuos', id: 3 },
]

export default function App() {
  const [history, setHistory] = useState<Loaded[]>([])
  const [loading, setLoading] = useState<Step | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // A layout belongs to one loaded result; `version` remounts the canvas so
  // React Flow fits the viewport to each new layout.
  const [layout, setLayout] = useState<{
    of: Loaded
    placed: Placed
    version: number
  } | null>(null)
  const [hovered, setHovered] = useState<string[]>([])
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [params, setParams] = useState<Partial<Record<QueryKey, string>>>({})
  const request = useRef(0)
  const rail = useRef<HTMLElement>(null)

  const current = history.at(-1)
  const def = current && QUERIES[current.step.query]
  const placed = layout && layout.of === current ? layout.placed : null

  /** Runs a step; `keep` is how many history entries survive before it. */
  const run = useCallback(async (step: Step, keep: number) => {
    const ticket = ++request.current
    setLoading(step)
    setMenuFor(null)
    const started = performance.now()
    try {
      const def = QUERIES[step.query]
      const result = await fetchGraph(def.path(step.id ?? 0))
      if (ticket !== request.current) return
      const focus = result.nodes.find((n) => n.role === 'focus')
      const loaded: Loaded = {
        step: { ...step, focus: focus ? focus.label : step.focus },
        result,
        ms: Math.round(performance.now() - started),
      }
      setHistory((h) => [...h.slice(0, keep), loaded])
      if (step.id != null) setParams((p) => ({ ...p, [step.query]: String(step.id) }))
      setExpanded(new Set())
      setHovered([])
      setSelected(focus ?? null)
      setFailure(null)
    } catch (error) {
      if (ticket !== request.current) return
      const e = error instanceof ApiError ? error : new ApiError(500, String(error))
      if (e.status === 404) {
        const type = QUERIES[step.query].param?.type ?? 'Vértice'
        setFailure({ kind: 'notfound', message: `${type} ${step.id} não existe` })
      } else if ([0, 502, 503, 504].includes(e.status)) {
        // 0: no answer at all; 502/504: the dev proxy could not reach the
        // API; 503: the API is up but Dgraph is not.
        setFailure({
          kind: 'down',
          message: e.status === 503 ? (e.detail ?? e.message) : '',
          retry: step,
          keep,
        })
      } else {
        setFailure({ kind: 'server', message: e.message, detail: e.detail })
      }
    } finally {
      if (ticket === request.current) setLoading(null)
    }
  }, [])

  // Lay the current result out whenever it or the expanded groups change.
  useEffect(() => {
    if (!current) return
    let alive = true
    place(current.result, QUERIES[current.step.query].direction, expanded).then(
      (placed) =>
        alive &&
        setLayout((l) => ({ of: current, placed, version: (l?.version ?? 0) + 1 })),
    )
    return () => {
      alive = false
    }
  }, [current, expanded])

  const back = useCallback(() => {
    if (history.length < 2) return
    request.current++
    setLoading(null)
    setHistory((h) => h.slice(0, -1))
    setExpanded(new Set())
    setHovered([])
    setSelected(null)
    setFailure(null)
  }, [history.length])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        const active = current?.step.query
        const input =
          rail.current?.querySelector<HTMLInputElement>(`input[name="${active}"]`) ??
          rail.current?.querySelector<HTMLInputElement>('input')
        input?.focus()
        input?.select()
      } else if (event.key === 'Escape') {
        if (menuFor) setMenuFor(null)
        else if (!(event.target instanceof HTMLInputElement)) back()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [back, current, menuFor])

  const actions = useMemo(
    (): GraphActions => ({
      activate: (node) => {
        setSelected(node)
        const queries = actionsFor(node.type)
        if (queries.length === 1) {
          void run({ query: queries[0], id: node.key, focus: node.label }, history.length)
        } else {
          setMenuFor((open) => (open === node.id || !queries.length ? null : node.id))
        }
      },
      run: (query, node) =>
        void run({ query, id: node.key, focus: node.label }, history.length),
      expand: (key) => setExpanded((s) => new Set(s).add(key)),
      hover: (id) => setHovered(id ? [id] : []),
    }),
    [run, history.length],
  )

  const submit = (query: QueryKey) => {
    const def = QUERIES[query]
    const raw = params[query] ?? String(def.param?.example ?? '')
    const id = def.param ? Number.parseInt(raw, 10) : undefined
    if (def.param && !Number.isFinite(id)) return
    void run({ query, id }, 0)
  }

  return (
    <div className="shell">
      <a className="skip" href="#canvas">
        Pular para o grafo
      </a>

      {failure?.kind === 'down' && (
        <div className="banner" role="alert">
          <span>
            <strong>Sem resposta do grafo.</strong> A Graphs API ou o Dgraph por trás
            dela está fora do ar{failure.message ? `: ${failure.message}` : ''}.
          </span>
          <button
            type="button"
            className="btn"
            onClick={() => void run(failure.retry, failure.keep)}
          >
            Tentar de novo
          </button>
        </div>
      )}

      <header className="topbar">
        <span className="wordmark">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M9 10 L23 10 L16 23 Z" />
            <circle cx="9" cy="10" r="4.5" />
            <circle cx="23" cy="10" r="4.5" />
            <circle className="hot" cx="16" cy="23" r="4.5" />
          </svg>
          Graph Explorer
        </span>
        <nav className="trail" aria-label="Caminho percorrido">
          <ol>
            {history.map((entry, index) => (
              <Fragment key={index}>
                <li>
                  <button
                    type="button"
                    className="crumb"
                    aria-current={index === history.length - 1 ? 'step' : undefined}
                    onClick={() => {
                      request.current++
                      setLoading(null)
                      setFailure(null)
                      setHistory((h) => h.slice(0, index + 1))
                      setExpanded(new Set())
                      setHovered([])
                    }}
                  >
                    {stepTitle(entry.step)}
                  </button>
                </li>
              </Fragment>
            ))}
            {loading && (
              <li>
                <span className="crumb crumb-pending">{stepTitle(loading)}</span>
              </li>
            )}
            {failure?.kind === 'notfound' && (
              <li>
                <span className="crumb crumb-error" role="alert">
                  {failure.message}
                  <button
                    type="button"
                    className="crumb-dismiss"
                    aria-label="Dispensar"
                    onClick={() => setFailure(null)}
                  >
                    ×
                  </button>
                </span>
              </li>
            )}
          </ol>
        </nav>
        <span className="hint">
          <kbd>Esc</kbd> volta · <kbd>⌘K</kbd> ID
        </span>
      </header>

      <nav className="rail" aria-label="Consultas" ref={rail}>
        {DATABASES.map((db) => (
          <section key={db.label} className="rail-group">
            <h2 className="eyebrow">{db.label}</h2>
            <ul>
              {db.queries.map((key) => {
                const q = QUERIES[key]
                const active = current?.step.query === key
                return (
                  <li key={key}>
                    <form
                      className="rail-item"
                      data-active={active}
                      onSubmit={(event) => {
                        event.preventDefault()
                        submit(key)
                      }}
                    >
                      <button type="submit" className="rail-run">
                        {q.title}
                      </button>
                      {q.param && (
                        <label className="rail-param">
                          <span className="sr-only">ID do {q.param.type}</span>
                          <input
                            name={key}
                            inputMode="numeric"
                            pattern="[0-9]*"
                            autoComplete="off"
                            value={params[key] ?? String(q.param.example)}
                            onChange={(event) =>
                              setParams((p) => ({
                                ...p,
                                [key]: event.target.value.replace(/\D/g, ''),
                              }))
                            }
                          />
                        </label>
                      )}
                    </form>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </nav>

      <main className="canvas" id="canvas" tabIndex={-1} aria-busy={loading != null}>
        {current && def && placed ? (
          <>
            <div className="canvas-head">
              <h1>{def.question(current.step.focus ?? '')}</h1>
              <Legend placed={placed} />
            </div>
            <div className="canvas-graph" data-loading={loading != null}>
              <ReactFlowProvider key={layout!.version}>
                <GraphView
                  placed={placed}
                  actions={actions}
                  hovered={hovered}
                  selected={selected?.id ?? null}
                  menuFor={menuFor}
                />
              </ReactFlowProvider>
              {current.result.items.length === 0 && (
                <p className="canvas-empty">{def.empty(current.step.focus ?? '')}</p>
              )}
            </div>
          </>
        ) : failure?.kind === 'server' ? (
          <div className="canvas-start">
            <h1>A consulta falhou no servidor</h1>
            <p>{failure.message}</p>
            {failure.detail && <pre className="code">{failure.detail}</pre>}
          </div>
        ) : (
          <div className="canvas-start" data-loading={loading != null}>
            <h1>Escolha uma consulta ou comece por uma destas</h1>
            <ul className="starts">
              {STARTS.map((step) => (
                <li key={step.query}>
                  <button
                    type="button"
                    className="start"
                    onClick={() => void run(step, 0)}
                  >
                    <span className="start-title">{QUERIES[step.query].title}</span>
                    <span className="start-path mono">
                      GET {QUERIES[step.query].path(step.id ?? 0)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>

      <aside className="panel" aria-label="Consulta e resultado">
        {current && def ? (
          <Inspector
            loaded={current}
            def={def}
            loading={loading != null}
            failure={failure?.kind === 'server' ? failure : null}
            selected={selected}
            onHover={setHovered}
            onRun={(query, node) =>
              void run({ query, id: node.key, focus: node.label }, history.length)
            }
          />
        ) : (
          <p className="panel-empty">
            A consulta DQL que a API executar aparece aqui, ao lado do resultado.
          </p>
        )}
      </aside>
    </div>
  )
}

function Legend({ placed }: { placed: Placed }) {
  const types = [...new Set(placed.nodes.map((p) => p.node.type))]
  return (
    <ul className="legend" aria-label="Legenda">
      {types.map((type) => (
        <li key={type}>
          <Glyph type={type} />
          {type}
        </li>
      ))}
      <li className="legend-role">
        <span className="swatch swatch-focus" aria-hidden="true" /> partida
      </li>
      <li className="legend-role">
        <span className="swatch swatch-result" aria-hidden="true" /> encontrado
      </li>
    </ul>
  )
}

const TOKENS =
  /("(?:[^"\\]|\\.)*"|\$\w+)|(@\w+|~)|\b(query|func|eq|ge|le|gt|lt|type|uid|val|count|NOT|AND|OR|orderdesc|orderasc|first|offset|var|as|expand|has|depth|true|false)\b/g

/** Re-indents a one-line DQL query: a block per brace, a line per field. */
function format(dql: string) {
  let depth = 0
  let out = ''
  let breakNext = false
  const indent = () => '\n' + '  '.repeat(depth)
  const src = dql.replace(/\s+/g, ' ').trim()
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    if (ch === ' ' && depth > 1 && /^[A-Za-z_]\w*: /.test(src.slice(i + 1))) {
      // A field alias starts here (`nome: fraude.Cliente.nome`).
      breakNext = true
    } else if (ch === '{') {
      depth++
      out = out.trimEnd() + ' {' + indent()
      breakNext = false
    } else if (ch === '}') {
      depth--
      out = out.trimEnd() + indent() + '}'
      breakNext = true
    } else if (ch === ' ') {
      if (!breakNext && !out.endsWith(' ') && !out.endsWith(indent())) out += ' '
    } else {
      if (breakNext && !out.endsWith(indent())) out += indent()
      breakNext = false
      out += ch
    }
  }
  return out
}

function highlight(dql: string) {
  const pretty = format(dql)
  const parts: ReactNode[] = []
  let last = 0
  for (const match of pretty.matchAll(TOKENS)) {
    parts.push(pretty.slice(last, match.index))
    parts.push(
      match[1] ? (
        <span key={match.index} className="tok-str">
          {match[0]}
        </span>
      ) : (
        <b key={match.index} className="tok-kw">
          {match[0]}
        </b>
      ),
    )
    last = match.index + match[0].length
  }
  parts.push(pretty.slice(last))
  return parts
}

interface InspectorProps {
  loaded: Loaded
  def: QueryDef
  loading: boolean
  failure: { message: string; detail?: string } | null
  selected: GraphNode | null
  onHover: (ids: string[]) => void
  onRun: (query: QueryKey, node: GraphNode) => void
}

function Inspector({
  loaded,
  def,
  loading,
  failure,
  selected,
  onHover,
  onRun,
}: InspectorProps) {
  const { result, step, ms } = loaded
  const [copied, setCopied] = useState(false)
  const path = def.path(step.id ?? 0)
  const props = selected
    ? Object.entries(selected.props).filter(([, v]) => v != null)
    : []
  // Queries from the selected vertex, minus the one already on screen.
  const next = selected
    ? actionsFor(selected.type).filter(
        (key) => key !== step.query || selected.key !== step.id,
      )
    : []

  return (
    <>
      <section className="panel-section">
        <p className="endpoint mono">
          <span className="verb">GET</span> /api{path}
        </p>
        <p className="meta">
          {result.items.length} {result.items.length === 1 ? 'linha' : 'linhas'} ·{' '}
          {result.nodes.length} nós · {result.edges.length} arestas · {ms} ms
        </p>
      </section>

      <section className="panel-section">
        <div className="section-head">
          <h2 className="eyebrow">Consulta DQL · Dgraph</h2>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => {
              void navigator.clipboard.writeText(result.queries.join(';\n\n'))
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
          >
            {copied ? 'Copiada' : 'Copiar'}
          </button>
        </div>
        {failure && (
          <div className="query-error" role="alert">
            <strong>{failure.message}</strong>
            {failure.detail && <span>{failure.detail}</span>}
          </div>
        )}
        {result.queries.map((sql, index) => (
          <pre key={index} className="code">
            {highlight(sql)}
          </pre>
        ))}
      </section>

      {selected && (
        <section className="panel-section">
          <h2 className="eyebrow">Vértice selecionado</h2>
          <p className="vertex">
            <Glyph type={selected.type} />
            <span>
              <span className="vertex-label">{selected.label}</span>
              <span className="vertex-id mono">
                {selected.type} · id {selected.key}
              </span>
            </span>
          </p>
          {props.length > 0 && (
            <dl className="props">
              {props.map(([key, value]) => (
                <Fragment key={key}>
                  <dt>{key}</dt>
                  <dd className="mono">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </dd>
                </Fragment>
              ))}
            </dl>
          )}
          {next.length > 0 && (
            <div className="vertex-actions">
              {next.map((key) => (
                <button
                  key={key}
                  type="button"
                  className="btn"
                  onClick={() => onRun(key, selected)}
                >
                  {QUERIES[key].title}
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="panel-section panel-results">
        <h2 className="eyebrow">Resultado</h2>
        {loading ? (
          <div className="skeleton" aria-hidden="true">
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i} />
            ))}
          </div>
        ) : result.items.length === 0 ? (
          <p className="panel-empty">Nenhuma linha.</p>
        ) : (
          <table className="results">
            <thead>
              <tr>
                {def.columns.map((c) => (
                  <th key={c.label} className={c.numeric ? 'num' : undefined}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody onMouseLeave={() => onHover([])}>
              {result.items.map((item, index) => {
                const ids = def.itemNodes(item, result.nodes)
                return (
                  <tr
                    key={index}
                    tabIndex={0}
                    onMouseEnter={() => onHover(ids)}
                    onFocus={() => onHover(ids)}
                    onBlur={() => onHover([])}
                  >
                    {def.columns.map((c) => (
                      <td key={c.label} className={c.numeric ? 'num' : undefined}>
                        {c.value(item)}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}
