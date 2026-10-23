import type { GraphNode, Item } from './api'

export type QueryKey =
  | 'conexoes'
  | 'aneis'
  | 'ciclos'
  | 'suspeitas'
  | 'produtos'
  | 'seguir'
  | 'ancestrais'
  | 'individuos'
  | 'relacoes'
  | 'kmapa'
  | 'kmodelo'
  | 'kinstancias'
  | 'kconexoes'
  | 'oinativos'
  | 'kinativos'
  | 'stipos'

export interface Column {
  label: string
  value: (item: Item) => string | number
  numeric?: boolean
}

export interface QueryDef {
  key: QueryKey
  title: string
  /** Pergunta que a consulta responde; recebe o rótulo do nó de partida. */
  question: (focus: string) => string
  empty: (focus: string) => string
  param?: { type: string; example: number }
  path: (id: number) => string
  columns: Column[]
  /** Nós do grafo que representam uma linha da tabela. */
  itemNodes: (item: Item, nodes: GraphNode[]) => string[]
  direction: 'RIGHT' | 'DOWN'
}

/** Which database a query reads; writes from its nodes go to the same one. */
export type Db = 'fraude' | 'recomendacao' | 'ontologia' | 'kosmos' | 'schema'

const brl = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})
export const money = (value: unknown) => brl.format(Number(value))

const ids = (type: string, ...keys: unknown[]) =>
  keys.map((key) => `${type}:${key}`)

/** Nós de domínio pelo nome (o mapa e o modelo listam nomes). */
const dominios = (nodes: GraphNode[], ...names: unknown[]) =>
  nodes
    .filter((n) => n.type === 'Dominio' && names.includes(n.label))
    .map((n) => n.id)

/** Instâncias do Kosmos têm o domínio como tipo: casa pela chave. */
const byKey = (nodes: GraphNode[], key: unknown) =>
  nodes.filter((n) => n.key === key).map((n) => n.id)

export const QUERIES: Record<QueryKey, QueryDef> = {
  conexoes: {
    key: 'conexoes',
    title: 'Conexões do cliente',
    question: (f) => `Quem divide dispositivo, IP ou telefone com ${f}`,
    empty: (f) =>
      `${f} não divide dispositivo, IP ou telefone com nenhum outro cliente.`,
    param: { type: 'Cliente', example: 281 },
    path: (id) => `/fraude/clientes/${id}/conexoes`,
    columns: [
      { label: 'Cliente', value: (i) => String(i.nome) },
      { label: 'Via', value: (i) => String(i.via) },
      { label: 'Identificador', value: (i) => String(i.valor) },
    ],
    itemNodes: (i) => ids('Cliente', i.id),
    direction: 'RIGHT',
  },
  aneis: {
    key: 'aneis',
    title: 'Anéis de fraude',
    question: () => 'Identificadores usados por 3 ou mais clientes',
    empty: () => 'Nenhum identificador é usado por 3 ou mais clientes.',
    path: () => '/fraude/aneis',
    columns: [
      { label: 'Via', value: (i) => String(i.via) },
      { label: 'Identificador', value: (i) => String(i.valor) },
      {
        label: 'Clientes',
        value: (i) => (i.clientes as number[]).length,
        numeric: true,
      },
    ],
    itemNodes: (i, nodes) =>
      nodes
        .filter((n) => n.type === i.via && n.label === i.valor)
        .map((n) => n.id),
    direction: 'RIGHT',
  },
  ciclos: {
    key: 'ciclos',
    title: 'Ciclos da conta',
    question: (f) => `Dinheiro que sai de ${f} e volta em 3 transferências`,
    empty: (f) =>
      `Nenhum dinheiro sai de ${f} e volta a ela em 3 transferências.`,
    param: { type: 'Conta', example: 61 },
    path: (id) => `/fraude/contas/${id}/ciclos`,
    columns: [
      {
        label: 'Ciclo',
        value: (i) => [...(i.contas as number[]), (i.contas as number[])[0]].join(' → '),
      },
    ],
    itemNodes: (i) => ids('Conta', ...(i.contas as number[])),
    direction: 'RIGHT',
  },
  suspeitas: {
    key: 'suspeitas',
    title: 'Transferências suspeitas',
    question: () => 'Transferências marcadas como suspeitas, por valor',
    empty: () => 'Nenhuma transferência está marcada como suspeita.',
    path: () => '/fraude/transferencias/suspeitas',
    columns: [
      { label: 'Origem', value: (i) => `Conta ${i.origem}` },
      { label: 'Destino', value: (i) => `Conta ${i.destino}` },
      { label: 'Valor', value: (i) => money(i.valor), numeric: true },
      {
        label: 'Dias',
        value: (i) => Number(i.dias_atras).toFixed(1),
        numeric: true,
      },
    ],
    itemNodes: (i) => ids('Conta', i.origem, i.destino),
    direction: 'RIGHT',
  },
  produtos: {
    key: 'produtos',
    title: 'Produtos recomendados',
    question: (f) => `O que compraram as pessoas que compraram o mesmo que ${f}`,
    empty: (f) =>
      `Quem comprou o mesmo que ${f} não comprou nada que ${f} ainda não tenha.`,
    param: { type: 'Usuario', example: 1 },
    path: (id) => `/recomendacao/usuarios/${id}/produtos`,
    columns: [
      { label: 'Produto', value: (i) => String(i.nome) },
      { label: 'Caminhos', value: (i) => Number(i.score), numeric: true },
    ],
    itemNodes: (i) => ids('Produto', i.id),
    direction: 'RIGHT',
  },
  seguir: {
    key: 'seguir',
    title: 'Quem seguir',
    question: (f) => `Quem é seguido por quem ${f} segue`,
    empty: (f) => `Quem ${f} segue não segue ninguém novo.`,
    param: { type: 'Usuario', example: 1 },
    path: (id) => `/recomendacao/usuarios/${id}/seguir`,
    columns: [
      { label: 'Usuário', value: (i) => String(i.nome) },
      { label: 'Em comum', value: (i) => Number(i.score), numeric: true },
    ],
    itemNodes: (i) => ids('Usuario', i.id),
    direction: 'RIGHT',
  },
  ancestrais: {
    key: 'ancestrais',
    title: 'Superclasses',
    question: (f) => `De quais classes ${f} herda`,
    empty: (f) => `${f} é a raiz da hierarquia: não herda de nenhuma classe.`,
    param: { type: 'Classe', example: 3 },
    path: (id) => `/ontologia/classes/${id}/ancestrais`,
    columns: [
      { label: 'Classe', value: (i) => String(i.nome) },
      { label: 'Nível', value: (i) => Number(i.nivel), numeric: true },
    ],
    itemNodes: (i) => ids('Classe', i.id),
    direction: 'DOWN',
  },
  individuos: {
    key: 'individuos',
    title: 'Indivíduos da classe',
    question: (f) => `Indivíduos de ${f} e de todas as subclasses`,
    empty: (f) => `Nenhum indivíduo pertence a ${f} ou às subclasses dela.`,
    param: { type: 'Classe', example: 3 },
    path: (id) => `/ontologia/classes/${id}/individuos`,
    columns: [
      { label: 'Indivíduo', value: (i) => String(i.nome) },
      { label: 'Classe', value: (i) => (i.classes as string[]).join(', ') },
    ],
    itemNodes: (i) => ids('Individuo', i.id),
    direction: 'RIGHT',
  },
  relacoes: {
    key: 'relacoes',
    title: 'Relações do indivíduo',
    question: (f) => `Com quem ${f} se relaciona, e como`,
    empty: (f) => `${f} não tem relações com outros indivíduos.`,
    param: { type: 'Individuo', example: 101 },
    path: (id) => `/ontologia/individuos/${id}/relacoes`,
    columns: [
      { label: 'Origem', value: (i) => String(i.origem) },
      { label: 'Relação', value: (i) => String(i.tipo).replaceAll('_', ' ') },
      { label: 'Destino', value: (i) => String(i.destino) },
    ],
    itemNodes: (i) => ids('Individuo', i.origem_id, i.destino_id),
    direction: 'RIGHT',
  },
  kmapa: {
    key: 'kmapa',
    title: 'Mapa de relações',
    question: () => 'Quais domínios se ligam por relações, e quantas vezes',
    empty: () => 'Nenhuma relação entre instâncias foi cadastrada.',
    path: () => '/kosmos/mapa',
    columns: [
      { label: 'Relação', value: (i) => String(i.relacao) },
      { label: 'Origem', value: (i) => String(i.origem) },
      { label: 'Destino', value: (i) => String(i.destino) },
      { label: 'Qtd', value: (i) => Number(i.quantidade), numeric: true },
    ],
    itemNodes: (i, nodes) => dominios(nodes, i.origem, i.destino),
    direction: 'RIGHT',
  },
  kmodelo: {
    key: 'kmodelo',
    title: 'Modelo do domínio',
    question: (f) => `Para onde os campos de ${f} apontam, e quem aponta para ${f}`,
    empty: (f) => `${f} não tem campos.`,
    param: { type: 'Dominio', example: 3310871 },
    path: (id) => `/kosmos/dominios/${id}/modelo`,
    columns: [
      { label: 'Campo', value: (i) => String(i.campo) },
      { label: 'Tipo', value: (i) => String(i.tipo) },
      { label: 'De', value: (i) => String(i.origem) },
      { label: 'Para', value: (i) => (i.destino == null ? '' : String(i.destino)) },
    ],
    itemNodes: (i, nodes) => dominios(nodes, i.origem, i.destino),
    direction: 'RIGHT',
  },
  kinstancias: {
    key: 'kinstancias',
    title: 'Instâncias do domínio',
    question: (f) => `Instâncias de ${f}, em ordem alfabética`,
    empty: (f) => `${f} não tem instâncias.`,
    param: { type: 'Dominio', example: 3310871 },
    path: (id) => `/kosmos/dominios/${id}/instancias`,
    columns: [
      { label: 'Instância', value: (i) => String(i.nome) },
      { label: 'Status', value: (i) => String(i.status ?? '') },
    ],
    itemNodes: (i, nodes) => byKey(nodes, i.id),
    direction: 'RIGHT',
  },
  kconexoes: {
    key: 'kconexoes',
    title: 'Conexões da instância',
    question: (f) => `Com o que ${f} se conecta: campos, referências e relações`,
    empty: (f) => `${f} não aponta nem é apontada por nenhuma instância.`,
    param: { type: 'Instancia', example: 3312744 },
    path: (id) => `/kosmos/instancias/${id}/conexoes`,
    columns: [
      { label: 'Via', value: (i) => String(i.via) },
      { label: 'Sentido', value: (i) => (i.direcao === 'saida' ? 'sai' : 'entra') },
      { label: 'Instância', value: (i) => String(i.nome) },
      { label: 'Domínio', value: (i) => String(i.dominio) },
    ],
    itemNodes: (i, nodes) => byKey(nodes, i.id),
    direction: 'RIGHT',
  },
  oinativos: {
    key: 'oinativos',
    title: 'Inativos',
    question: () => 'Classes, indivíduos e relações inativados',
    empty: () => 'Nada foi inativado na ontologia.',
    path: () => '/ontologia/inativos',
    columns: [
      { label: 'Tipo', value: (i) => String(i.tipo) },
      { label: 'Nome', value: (i) => String(i.nome) },
    ],
    itemNodes: (i) => ids(String(i.tipo), i.id),
    direction: 'RIGHT',
  },
  kinativos: {
    key: 'kinativos',
    title: 'Inativos',
    question: () => 'Domínios, campos, instâncias e relações inativados',
    empty: () => 'Nada foi inativado no Kosmos.',
    path: () => '/kosmos/inativos',
    columns: [
      { label: 'Tipo', value: (i) => String(i.tipo) },
      { label: 'Nome', value: (i) => String(i.nome) },
    ],
    itemNodes: (i, nodes) => byKey(nodes, i.id),
    direction: 'RIGHT',
  },
  stipos: {
    key: 'stipos',
    title: 'Tipos Dgraph',
    question: () => 'Types do schema e seus predicados (sem dgraph.* e kosmos.*)',
    empty: () => 'O schema não tem types fora de dgraph.* e kosmos.*.',
    path: () => '/schema/tipos',
    columns: [
      { label: 'Type', value: (i) => String(i.tipo) },
      { label: 'Predicado', value: (i) => String(i.predicado) },
      { label: 'Tipo', value: (i) => String(i.dgraph) },
      { label: 'Índices', value: (i) => (i.indices as string[]).join(', ') },
    ],
    itemNodes: (i, nodes) =>
      nodes.filter((n) => n.label === i.tipo || n.label === i.predicado).map((n) => n.id),
    direction: 'RIGHT',
  },
}

/** What each query shows and which graph idea it demonstrates. */
export const READING: Record<QueryKey, { concept: string; read: string }> = {
  conexoes: {
    concept: 'Vizinhança em 2 saltos',
    read: 'Cliente → identificador → outro cliente. Os nós neutros são o dispositivo, IP ou telefone em comum; os de borda rosa, os clientes encontrados. Em SQL seriam dois JOINs na tabela de uso; aqui a consulta segue UsaDispositivo, UsaIp e TemTelefone e volta pela aresta inversa (~).',
  },
  aneis: {
    concept: 'Contagem de arestas',
    read: 'Cada identificador encontrado (borda rosa) é usado por 3 ou mais clientes. Em vez de GROUP BY, a consulta conta as arestas que chegam em cada identificador: o Dgraph guarda o inverso de cada aresta, então count(~UsaDispositivo) sai direto do índice.',
  },
  ciclos: {
    concept: 'Caminho que fecha',
    read: 'Cada seta é uma transferência. Um ciclo é A → B → C → A. Em SQL isso é um self-join triplo na tabela de transferências; aqui são três saltos pela mesma aresta, exigindo que o último volte à conta de partida.',
  },
  suspeitas: {
    concept: 'Aresta com atributos',
    read: 'Cada seta é uma transferência suspeita, com o valor no rótulo. No Dgraph a transferência é um nó próprio (fraude.Transfere) com origem, destino, valor e data, como uma linha de tabela de junção; a API desenha esse nó como uma seta.',
  },
  produtos: {
    concept: 'Filtragem colaborativa',
    read: 'Você → Comprou → produto ← Comprou ← outra pessoa → Comprou → produto novo. Os nós neutros são as compras em comum e quem as fez. Caminhos conta quantas rotas chegam a cada produto: é a nota da recomendação.',
  },
  seguir: {
    concept: 'Amigos de amigos',
    read: 'Segue → Segue: quem é seguido por quem você segue, menos quem você já segue. Em comum conta quantas pessoas que você segue levam a cada sugestão.',
  },
  ancestrais: {
    concept: 'Recursão',
    read: 'SubclasseDe liga cada classe à sua superclasse. A consulta sobe a cadeia até a raiz com @recurse, sem saber a profundidade antes. Em SQL isso pede uma CTE recursiva.',
  },
  individuos: {
    concept: 'Herança',
    read: 'Indivíduos da classe e de todas as subclasses: a consulta desce SubclasseDe ao contrário e, em cada classe alcançada, pega quem é InstanciaDe dela.',
  },
  relacoes: {
    concept: 'Arestas nomeadas',
    read: 'Cada aresta leva o nome da relação (trabalha_em, orienta). O tipo da relação é o próprio predicado, não uma coluna numa tabela de tipos.',
  },
  kmapa: {
    concept: 'Modelo como dado',
    read: 'Cada caixa é um domínio, o equivalente a uma tabela no sistema de origem. Cada seta ◆ é um tipo de relação entre dois domínios, com quantas relações existem. É o diagrama ER, calculado a partir dos próprios dados.',
  },
  kmodelo: {
    concept: 'Esquema dentro do grafo',
    read: 'O domínio em preto e os domínios para onde seus campos seletores apontam, como chaves estrangeiras. Os nós neutros são tipos de relação que usam este domínio. A tabela lista todos os campos: texto, número e data viram predicados no nó da instância; seletor vira aresta.',
  },
  kinstancias: {
    concept: 'Aresta inversa',
    read: 'Cada instância é uma linha da tabela do domínio, ligada a ele por instanceOf. A consulta parte do domínio e segue essa aresta ao contrário (~kosmos.instanceOf): é o SELECT * FROM tabela.',
  },
  kconexoes: {
    concept: 'JOIN vira travessia',
    read: 'Seta simples é um campo seletor: a instância guarda o uid da outra, como uma chave estrangeira. Seta ◆ é uma relação: no Dgraph cada uma é um nó REL_ com subject e object (a linha da tabela de junção), resumido aqui como seta. Clique numa instância para seguir por ela.',
  },
  oinativos: {
    concept: 'Exclusão lógica',
    read: 'Itens com status inactive. Nada é apagado: as outras consultas filtram esse status, e Reativar devolve o item.',
  },
  kinativos: {
    concept: 'Exclusão lógica',
    read: 'Itens com status inactive. Nada é apagado: as outras consultas filtram esse status, e Reativar devolve o item.',
  },
  stipos: {
    concept: 'Schema do Dgraph',
    read: 'Cada type agrupa predicados (os nós neutros). No Dgraph o predicado existe por conta própria e pode estar em vários types; o type diz quais predicados um nó costuma ter, mas não restringe os dados.',
  },
}

export const DATABASES: { db: Db; label: string; about: string; queries: QueryKey[] }[] = [
  {
    db: 'fraude',
    label: 'Fraude',
    about: 'Clientes, contas e os identificadores que dividem',
    queries: ['conexoes', 'aneis', 'ciclos', 'suspeitas'],
  },
  {
    db: 'recomendacao',
    label: 'Recomendação',
    about: 'Compras e quem segue quem',
    queries: ['produtos', 'seguir'],
  },
  {
    db: 'ontologia',
    label: 'Ontologia',
    about: 'Classes com herança, indivíduos e relações',
    queries: ['ancestrais', 'individuos', 'relacoes', 'oinativos'],
  },
  {
    db: 'kosmos',
    label: 'Kosmos',
    about: 'Um modelo relacional migrado para grafo',
    queries: ['kmapa', 'kmodelo', 'kinstancias', 'kconexoes', 'kinativos'],
  },
  {
    db: 'schema',
    label: 'Schema',
    about: 'Types e predicados do próprio Dgraph',
    queries: ['stipos'],
  },
]

export const dbOf = (query: QueryKey): Db =>
  DATABASES.find((d) => d.queries.includes(query))!.db

/** Kosmos node types that are not instances of a domain. */
export const KOSMOS_META = new Set(['Dominio', 'TipoRelacao', 'Campo', 'Conceito'])

/** Consultas que partem de um vértice, por classe do vértice. */
export const ACTIONS: Record<string, QueryKey[]> = {
  Cliente: ['conexoes'],
  Conta: ['ciclos'],
  Usuario: ['produtos', 'seguir'],
  Classe: ['ancestrais', 'individuos'],
  Individuo: ['relacoes'],
}

/**
 * Consultas que partem de `node`. No Kosmos o tipo é o nome do domínio (e
 * pode colidir com os outros bancos, como Conta), então vale o banco de onde
 * o grafo veio.
 */
export function actionsFor(node: GraphNode, from: QueryKey): QueryKey[] {
  if (node.role === 'draft') return []
  const db = dbOf(from)
  if (db === 'schema') return []
  if (db === 'kosmos') {
    if (node.type === 'Dominio') return ['kinstancias', 'kmodelo']
    if (node.type === 'TipoRelacao') return ['kmodelo']
    return KOSMOS_META.has(node.type) ? [] : ['kconexoes']
  }
  return ACTIONS[node.type]?.filter((key) => QUERIES[key].param?.type === node.type) ?? []
}
