import { DATABASES, QUERIES, READING, type QueryKey } from './queries'

interface Start {
  query: QueryKey
  id?: number
}

/** The Kosmos walk-through: four real queries, each with what to notice. */
export const TOUR: { step: Start; title: string; notice: string }[] = [
  {
    step: { query: 'kmapa' },
    title: 'As tabelas e como se ligam',
    notice:
      'Cada caixa é um domínio (uma tabela). Cada seta ◆ é um tipo de relação, com quantas relações daquele tipo existem. Ninguém desenhou esse diagrama: ele sai de uma consulta aos dados.',
  },
  {
    step: { query: 'kmodelo', id: 3310871 },
    title: 'Uma tabela por dentro',
    notice:
      'Os campos de Grupo Econômico estão na tabela à direita. Só o seletor vira seta, porque é uma chave estrangeira. O nó neutro é um tipo de relação que aponta para este domínio.',
  },
  {
    step: { query: 'kinstancias', id: 3310871 },
    title: 'As linhas',
    notice:
      'Cada nó é uma instância, uma linha da tabela. Todas apontam para o domínio por instanceOf, e a consulta só seguiu essa aresta ao contrário.',
  },
  {
    step: { query: 'kconexoes', id: 3312744 },
    title: 'Um JOIN sem JOIN',
    notice:
      'Tipo de Grupo Econômico é seta simples: uma chave estrangeira. As setas ◆ até as empresas são relações; no banco cada uma é um nó próprio, como a linha de uma tabela de junção. Clique numa empresa para continuar daqui.',
  },
]

const MAPPING: [string, string, string][] = [
  ['Tabela', 'Domínio', 'nó kosmos.Concept e um type kosmos.‹Domínio›'],
  ['Coluna', 'Campo', 'predicado kosmos.‹Campo›_‹id›'],
  ['Linha', 'Instância', 'nó com a aresta instanceOf até o domínio'],
  ['Chave estrangeira', 'Campo seletor', 'aresta [uid] @reverse até a outra instância'],
  ['Tabela de junção', 'Tipo de relação', 'nó REL_ com subject, object e relationType'],
  ['JOIN', 'Conexões da instância', 'seguir uma aresta; ~ segue ao contrário'],
]

export function Guide({
  loading,
  onRun,
  onTour,
}: {
  loading: boolean
  onRun: (step: Start) => void
  onTour: () => void
}) {
  return (
    <div className="guide" data-loading={loading}>
      <h1>Cinco casos de uso no mesmo Dgraph</h1>
      <p className="guide-lede">
        Cada consulta é uma pergunta a um banco. A resposta aparece desenhada no centro;
        ao lado ficam o endpoint chamado, a DQL exata e as linhas que voltaram.
      </p>

      <section className="guide-section">
        <h2 className="eyebrow">Como ler a tela</h2>
        <ol className="anatomy">
          <li>
            <strong>Consultas, à esquerda.</strong> O número ao lado de uma consulta é o ID
            do vértice de onde ela parte; troque e aperte Enter. Os botões tracejados criam
            algo novo naquele banco.
          </li>
          <li>
            <strong>Grafo, no centro.</strong>{' '}
            <span className="swatch swatch-focus" aria-hidden="true" /> partida,{' '}
            <span className="swatch swatch-path" aria-hidden="true" /> caminho percorrido,{' '}
            <span className="swatch swatch-result" aria-hidden="true" /> encontrado. Clique
            num nó para ver o que dá para consultar a partir dele. A trilha no topo guarda
            cada passo, e <kbd>Esc</kbd> volta um.
          </li>
          <li>
            <strong>Painel, à direita.</strong> Como ler o resultado, a DQL que a API rodou
            (copie e rode no Ratel), o vértice selecionado e as linhas. Passe o mouse numa
            linha para acender os nós dela.
          </li>
        </ol>
      </section>

      <section className="guide-section">
        <div className="section-head">
          <h2 className="eyebrow">Kosmos: do relacional ao grafo</h2>
        </div>
        <p className="guide-text">
          O Kosmos veio de um modelo relacional. A estrutura continua a mesma; o que muda
          é que chaves estrangeiras e tabelas de junção viram arestas, e um JOIN vira
          seguir uma aresta.
        </p>
        <div className="mapping-wrap">
          <table className="mapping">
            <thead>
              <tr>
                <th>Relacional</th>
                <th>Kosmos</th>
                <th>No Dgraph</th>
              </tr>
            </thead>
            <tbody>
              {MAPPING.map(([rel, kos, dg]) => (
                <tr key={rel}>
                  <td>{rel}</td>
                  <td>{kos}</td>
                  <td className="mono">{dg}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="btn btn-primary guide-tour" onClick={onTour}>
          Fazer o percurso · {TOUR.length} passos
        </button>
      </section>

      <section className="guide-section">
        <h2 className="eyebrow">Casos de uso</h2>
        {DATABASES.map((group) => (
          <div key={group.db} className="usecase">
            <h3>
              {group.label} <span>{group.about}</span>
            </h3>
            <ul className="starts">
              {group.queries.map((query) => (
                <li key={query}>
                  <button
                    type="button"
                    className="start"
                    onClick={() => onRun({ query, id: QUERIES[query].param?.example })}
                  >
                    <span className="start-title">{QUERIES[query].title}</span>
                    <span className="start-concept">{READING[query].concept}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  )
}

export function TourBar({
  index,
  onTrack,
  onGo,
  onExit,
}: {
  index: number
  /** Whether the graph on screen is this step's. */
  onTrack: boolean
  onGo: (index: number) => void
  onExit: () => void
}) {
  const step = TOUR[index]
  // The last step asks for a click away from it: that ends the walk.
  const done = !onTrack && index === TOUR.length - 1
  return (
    <section className="tour" aria-label="Percurso Kosmos" aria-live="polite">
      <p className="tour-count mono">
        {index + 1}/{TOUR.length}
      </p>
      <div className="tour-body">
        <h2>{step.title}</h2>
        <p>
          {onTrack
            ? step.notice
            : done
              ? 'Fim do percurso. Daqui em diante cada nó leva a outra consulta, e o painel explica cada uma.'
              : 'Você saiu do percurso para explorar.'}
        </p>
      </div>
      <div className="tour-actions">
        {done ? (
          <button type="button" className="btn btn-primary" onClick={onExit}>
            Concluir
          </button>
        ) : !onTrack ? (
          <button type="button" className="btn" onClick={() => onGo(index)}>
            Voltar ao passo {index + 1}
          </button>
        ) : (
          <>
            {index > 0 && (
              <button type="button" className="btn btn-quiet" onClick={() => onGo(index - 1)}>
                Anterior
              </button>
            )}
            {index < TOUR.length - 1 ? (
              <button type="button" className="btn btn-primary" onClick={() => onGo(index + 1)}>
                Próximo
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={onExit}>
                Concluir
              </button>
            )}
          </>
        )}
        <button
          type="button"
          className="btn btn-quiet btn-icon"
          aria-label="Sair do percurso"
          onClick={onExit}
        >
          ×
        </button>
      </div>
    </section>
  )
}
