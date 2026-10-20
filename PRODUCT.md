# Product

## Register

product

## Users

Engenheiros e arquitetos avaliando o Dgraph como banco de grafos. Abrem a
interface no próprio monitor, durante uma avaliação técnica, para entender
como cada caso de uso (fraude, recomendação, ontologia) se comporta sobre
dados reais. Conhecem SQL e APIs; não precisam de explicação de conceito
básico, precisam ver o grafo responder.

## Product Purpose

Interface que consome a Graphs API (FastAPI sobre Dgraph) e torna visíveis
as conexões que cada consulta encontra: o anel de clientes que divide um
dispositivo, o ciclo de transferências que volta à conta de origem, o caminho
que leva a uma recomendação, a cadeia de superclasses de uma ontologia.
Sucesso: quem usa sai entendendo a forma da conexão, não só a lista de IDs.

## Brand Personality

Precisa, densa, sem enfeite. Ferramenta técnica que respeita quem a usa.
Três palavras: exata, legível, direta. O grafo desenhado é o protagonista;
o resto da interface serve a ele.

## Anti-references

- Dashboard SaaS genérico: cards com número grande, gráficos de pizza,
  sidebar azul, métricas decorativas.
- OrientDB Studio: admin cru, tabelas cinzas, formulários soltos, sem
  hierarquia.

## Design Principles

1. **A conexão é o dado.** Toda resposta da API vira desenho de nós e
   arestas antes de virar lista; a lista é apoio.
2. **Mostrar o que a consulta fez.** O caminho percorrido (de onde saiu,
   por qual aresta, onde chegou) fica explícito, não implícito.
3. **Densidade com hierarquia.** Muita informação na tela, mas sempre com
   um foco claro; nada de tudo com o mesmo peso.
4. **Sem cerimônia.** Nada de onboarding, hero ou texto explicando o óbvio
   para um engenheiro.

## Accessibility & Inclusion

WCAG AA: contraste AA em texto e marcas do grafo, navegação completa por
teclado, `prefers-reduced-motion` respeitado em layout e transições do grafo.
