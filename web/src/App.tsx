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

import { ApiError, fetchGraph, type GraphNode, type GraphResult, type Item } from './api'
import { DraftPanel } from './Draft'
import {
  EDITS,
  ROOT_WRITES,
  after,
  connectable,
  rowWrites,
  withDraft,
  writeLabel,
  writesFor,
  type Draft,
  type WriteKey,
} from './drafts'
import { Glyph, GraphView, type GraphActions } from './Graph'
import { Guide, TOUR, TourBar } from './Guide'
import { place, type Placed } from './layout'
import {
  DATABASES,
  QUERIES,
  READING,
  actionsFor,
  dbOf,
  type Db,
  type QueryDef,
  type QueryKey,
} from './queries'
import { undo, type Undo, type WriteResult } from './writes'

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

const EDIT_KEYS = new Set<WriteKey>([
  'o-editar-classe',
  'o-editar-individuo',
  'k-editar-dominio',
  'k-editar-instancia',
  's-editar-tipo',
])

const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

/** Whether the "Como ler" block stays open, remembered per browser. */
const readingOpen = () => {
  try {
    return localStorage.getItem('reading-open') !== 'false'
  } catch {
    return true
  }
}

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
  const [draft, setDraft] = useState<(Draft & { n: number }) | null>(null)
  const [draftLabel, setDraftLabel] = useState('novo')
  const [armed, setArmed] = useState(false)
  const [fresh, setFresh] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; undo?: Undo } | null>(null)
  const [guide, setGuide] = useState(false)
  const [tour, setTour] = useState<number | null>(null)
  const request = useRef(0)
  const rail = useRef<HTMLElement>(null)
  const submitDraft = useRef<(() => void) | null>(null)
  const draftDirty = useRef(false)
  const drafts = useRef(0)

  const current = history.at(-1)
  const def = current && QUERIES[current.step.query]
  const placed = layout && layout.of === current ? layout.placed : null

  /** Runs a step; `keep` is how many history entries survive before it. */
  const run = useCallback(async (step: Step, keep: number) => {
    const ticket = ++request.current
    setLoading(step)
    setMenuFor(null)
    setGuide(false)
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
    place(
      withDraft(current.result, draft),
      QUERIES[current.step.query].direction,
      expanded,
    ).then(
      (placed) =>
        alive &&
        setLayout((l) => ({ of: current, placed, version: (l?.version ?? 0) + 1 })),
    )
    return () => {
      alive = false
    }
  }, [current, expanded, draft])

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

  const from = current?.step.query ?? 'conexoes'
  const db = dbOf(from)

  const startDraft = useCallback(
    (kind: WriteKey, dbOfDraft: Db, node?: GraphNode, target?: GraphNode, row?: Item) => {
      setMenuFor(null)
      setArmed(false)
      setDraftLabel('novo')
      setDraft({ kind, db: dbOfDraft, from: node, target, row, n: ++drafts.current })
    },
    [],
  )

  const discard = useCallback(() => {
    setDraft(null)
    setArmed(false)
  }, [])

  const finish = useCallback(
    (result: WriteResult) => {
      if (!draft) return
      setDraft(null)
      setArmed(false)
      const next = after(draft, result)
      if (next) void run(next, history.length)
      else if (current) void run(current.step, history.length - 1)
      if (result.node) {
        setFresh(result.node)
        setTimeout(() => setFresh(null), 1800)
      }
      if (draft.kind === 'inativar') {
        setToast({
          message: draft.db === 'schema' ? 'Type removido' : 'Inativado',
          undo: result.desfazer ?? undefined,
        })
      } else if (draft.kind === 'reativar') {
        setToast({ message: 'Reativado', undo: result.desfazer ?? undefined })
      }
    },
    [draft, run, history.length, current],
  )

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 8000)
    return () => clearTimeout(timer)
  }, [toast])

  const revert = async (u: Undo) => {
    setToast(null)
    try {
      await undo(u)
      setToast({ message: 'Desfeito' })
      if (current) void run(current.step, history.length - 1)
    } catch (e) {
      setToast({ message: `Não deu para desfazer: ${e instanceof Error ? e.message : e}` })
    }
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (draft) {
        if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
          // The form handles it when focus is inside the panel.
          if (!event.defaultPrevented) submitDraft.current?.()
          event.preventDefault()
          return
        }
        if (event.key === 'Escape') {
          if (draftDirty.current && !armed) setArmed(true)
          else discard()
          return
        }
      }
      if (!event.metaKey && !event.ctrlKey && !event.altKey && !typing(event.target) && selected) {
        const writes = writesFor(selected, from)
        const key = event.key.toLowerCase()
        if (key === 'n' && (writes.length || actionsFor(selected, from).length)) {
          event.preventDefault()
          setMenuFor(selected.id)
          return
        }
        const kind =
          key === 'e'
            ? writes.find((w) => EDIT_KEYS.has(w))
            : key === 'r'
              ? writes.find((w) => w === 'o-relacao' || w === 'k-relacao')
              : undefined
        if (kind) {
          event.preventDefault()
          startDraft(kind, db, selected)
          return
        }
      }
      if (event.key === '?' && !typing(event.target)) {
        setGuide((g) => !g)
        return
      }
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
        else if (guide && current) setGuide(false)
        else if (!(event.target instanceof HTMLInputElement)) back()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [back, current, menuFor, draft, armed, discard, selected, from, db, startDraft, guide])

  const actions = useMemo(
    (): GraphActions => ({
      activate: (node) => {
        setSelected(node)
        const queries = actionsFor(node, from)
        const writes = writesFor(node, from)
        if (queries.length === 1) {
          void run({ query: queries[0], id: node.key, focus: node.label }, history.length)
        } else {
          setMenuFor((open) =>
            open === node.id || queries.length + writes.length === 0 ? null : node.id,
          )
        }
      },
      run: (query, node) =>
        void run({ query, id: node.key, focus: node.label }, history.length),
      expand: (key) => setExpanded((s) => new Set(s).add(key)),
      hover: (id) => setHovered(id ? [id] : []),
      actionsFor: (node) => actionsFor(node, from),
      writesFor: (node) => writesFor(node, from),
      write: (kind, node) => startDraft(kind, db, node),
      db,
    }),
    [run, history.length, from, db, startDraft],
  )

  const canConnect = useCallback((node: GraphNode) => connectable(node, from), [from])
  const editing = draft && EDITS.has(draft.kind) ? (draft.from?.id ?? null) : null

  const goTour = (index: number) => {
    setTour(index)
    void run({ ...TOUR[index].step }, index)
  }
  const onTrack =
    tour != null &&
    current?.step.query === TOUR[tour].step.query &&
    current.step.id === TOUR[tour].step.id

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
          <kbd>Esc</kbd> volta · <kbd>⌘K</kbd> ID · <kbd>?</kbd> guia
        </span>
        <button
          type="button"
          className="btn btn-quiet"
          aria-pressed={guide || !current}
          onClick={() => setGuide((g) => !g)}
          disabled={!current}
        >
          Guia
        </button>
      </header>

      <nav className="rail" aria-label="Consultas" ref={rail}>
        {DATABASES.map((group) => (
          <section key={group.label} className="rail-group">
            <h2 className="eyebrow">{group.label}</h2>
            <p className="rail-about">{group.about}</p>
            <ul>
              {group.queries.map((key) => {
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
                            title={`ID do ${q.param.type} de partida`}
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
            {ROOT_WRITES[group.db] && (
              <div className="rail-writes">
                {ROOT_WRITES[group.db]!.map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    className="rail-write"
                    aria-pressed={draft?.kind === kind && !draft.from}
                    onClick={() =>
                      startDraft(
                        kind,
                        group.db,
                        // A relation type starts from the selected domain.
                        kind === 'k-tipo-relacao' && selected?.type === 'Dominio' && db === 'kosmos'
                          ? selected
                          : undefined,
                      )
                    }
                  >
                    {writeLabel(kind, group.db)}
                  </button>
                ))}
              </div>
            )}
          </section>
        ))}
      </nav>

      <main className="canvas" id="canvas" tabIndex={-1} aria-busy={loading != null}>
        {guide || (!current && failure?.kind !== 'server') ? (
          <Guide
            loading={loading != null}
            onRun={(step) => {
              setTour(null)
              void run(step, current ? history.length : 0)
            }}
            onTour={() => goTour(0)}
          />
        ) : current && def && placed ? (
          <>
            <div className="canvas-head">
              <h1>{def.question(current.step.focus ?? '')}</h1>
              <Legend placed={placed} />
            </div>
            {tour != null && (
              <TourBar
                index={tour}
                onTrack={onTrack}
                onGo={goTour}
                onExit={() => setTour(null)}
              />
            )}
            <div className="canvas-graph" data-loading={loading != null}>
              <ReactFlowProvider key={layout!.version}>
                <GraphView
                  placed={placed}
                  actions={actions}
                  hovered={hovered}
                  selected={selected?.id ?? null}
                  menuFor={menuFor}
                  editing={editing}
                  fresh={fresh}
                  draftLabel={draftLabel}
                  canConnect={canConnect}
                  onConnect={(source, target) =>
                    startDraft(db === 'ontologia' ? 'o-relacao' : 'k-relacao', db, source, target)
                  }
                />
              </ReactFlowProvider>
              {current.result.items.length === 0 && !draft && (
                <p className="canvas-empty">{def.empty(current.step.focus ?? '')}</p>
              )}
              {toast && (
                <div className="toast" role="status">
                  <span>{toast.message}</span>
                  {toast.undo && (
                    <button type="button" className="btn" onClick={() => void revert(toast.undo!)}>
                      Desfazer
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-quiet btn-icon"
                    aria-label="Dispensar"
                    onClick={() => setToast(null)}
                  >
                    ×
                  </button>
                </div>
              )}
            </div>
          </>
        ) : failure?.kind === 'server' ? (
          <div className="canvas-start">
            <h1>A consulta falhou no servidor</h1>
            <p>{failure.message}</p>
            {failure.detail && <pre className="code">{failure.detail}</pre>}
          </div>
        ) : null}
      </main>

      <aside className="panel" aria-label="Consulta e resultado">
        {draft && (
          <DraftPanel
            key={draft.n}
            draft={draft}
            onDone={finish}
            onCancel={discard}
            onLabel={setDraftLabel}
            submitRef={submitDraft}
            dirtyRef={draftDirty}
            armed={armed}
          />
        )}
        {current && def ? (
          <Inspector
            loaded={current}
            def={def}
            loading={loading != null}
            failure={failure?.kind === 'server' ? failure : null}
            selected={draft ? null : selected}
            onHover={setHovered}
            onRun={(query, node) =>
              void run({ query, id: node.key, focus: node.label }, history.length)
            }
            onWrite={(kind, node, row) => startDraft(kind, db, node, undefined, row)}
          />
        ) : draft ? null : (
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
  const roles = new Set(placed.nodes.map((p) => p.node.role))
  const relations = placed.edges.some((p) => p.edge.props.relacao === true)
  const selectors = placed.edges.some((p) => p.edge.props.relacao === false)
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
      {roles.has('path') && (
        <li className="legend-role">
          <span className="swatch swatch-path" aria-hidden="true" /> caminho
        </li>
      )}
      <li className="legend-role">
        <span className="swatch swatch-result" aria-hidden="true" /> encontrado
      </li>
      {selectors && <li className="legend-role">→ campo seletor</li>}
      {relations && <li className="legend-role">◆ relação</li>}
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
  onWrite: (kind: WriteKey, node?: GraphNode, row?: Item) => void
}

function Inspector({
  loaded,
  def,
  loading,
  failure,
  selected,
  onHover,
  onRun,
  onWrite,
}: InspectorProps) {
  const { result, step, ms } = loaded
  const [copied, setCopied] = useState(false)
  const path = def.path(step.id ?? 0)
  const props = selected
    ? Object.entries(selected.props).filter(([, v]) => v != null)
    : []
  // Queries from the selected vertex, minus the one already on screen.
  const next = selected
    ? actionsFor(selected, step.query).filter(
        (key) => key !== step.query || selected.key !== step.id,
      )
    : []
  const writes = selected ? writesFor(selected, step.query) : []
  const db = dbOf(step.query)
  const rowActions = result.items.some((item) => rowWrites(item, step.query).length > 0)

  return (
    <>
      <details
        className="panel-section reading"
        open={readingOpen()}
        onToggle={(event) => {
          try {
            localStorage.setItem('reading-open', String(event.currentTarget.open))
          } catch {
            // Private mode: the block just opens again next time.
          }
        }}
      >
        <summary>
          <span className="eyebrow">Como ler</span>
          <span className="reading-concept">{READING[step.query].concept}</span>
        </summary>
        <p>{READING[step.query].read}</p>
      </details>

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
              void navigator.clipboard.writeText(result.queries.join('\n\n'))
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
          {writes.length > 0 && (
            <div className="vertex-actions vertex-writes">
              {writes.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className={kind === 'inativar' ? 'btn btn-quiet btn-danger-text' : 'btn'}
                  onClick={() => onWrite(kind, selected)}
                >
                  {writeLabel(kind, db)}
                </button>
              ))}
              <span className="hint">
                <kbd>N</kbd> menu · <kbd>E</kbd> editar · <kbd>R</kbd> relação
              </span>
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
                {rowActions && (
                  <th>
                    <span className="sr-only">Ações</span>
                  </th>
                )}
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
                    {rowActions && (
                      <td className="row-actions">
                        {rowWrites(item, step.query).map((kind) => (
                          <button
                            key={kind}
                            type="button"
                            className="btn btn-quiet btn-row"
                            onClick={() => onWrite(kind, undefined, item)}
                          >
                            {kind === 'inativar' && item.relacao_id != null && item.campo_id == null
                              ? 'Inativar relação'
                              : writeLabel(kind, db)}
                          </button>
                        ))}
                      </td>
                    )}
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
