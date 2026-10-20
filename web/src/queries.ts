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

const brl = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})
export const money = (value: unknown) => brl.format(Number(value))

const ids = (type: string, ...keys: unknown[]) =>
  keys.map((key) => `${type}:${key}`)

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
}

export const DATABASES: { label: string; queries: QueryKey[] }[] = [
  { label: 'Fraude', queries: ['conexoes', 'aneis', 'ciclos', 'suspeitas'] },
  { label: 'Recomendação', queries: ['produtos', 'seguir'] },
  { label: 'Ontologia', queries: ['ancestrais', 'individuos', 'relacoes'] },
]

/** Consultas que partem de um vértice, por classe do vértice. */
export const ACTIONS: Record<string, QueryKey[]> = {
  Cliente: ['conexoes'],
  Conta: ['ciclos'],
  Usuario: ['produtos', 'seguir'],
  Classe: ['ancestrais', 'individuos'],
  Individuo: ['relacoes'],
}

export const actionsFor = (type: string) =>
  ACTIONS[type]?.filter((key) => QUERIES[key].param?.type === type) ?? []
