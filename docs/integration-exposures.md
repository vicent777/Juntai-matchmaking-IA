# Integração Node ↔ FastAPI e exposições

## Fluxo implementado

O navegador chama apenas o backend Node (3333). O backend consulta PostgreSQL,
autoriza o investidor e chama `POST /match/rules` no FastAPI (8000). Não há acesso
ao banco pelo Python nem alteração dos algoritmos existentes.

Endpoints novos, todos autenticados e exclusivos de investidores ativos/aprovados:

- `GET /startups/recomendacoes?limite=24`: recomendações do Nível 1; limite 1–1000.
- `GET /startups/discovery?page=0&size=24&sort=compatibility`: página usada pelo
  frontend, com filtros existentes de texto, segmento, estágio, localização,
  modelo, investimento, faixa e salvos. Esta rota era chamada pela interface,
  mas não existia no backend inspecionado.
- `POST /startups/exposicoes`, JSON `{"contexto":"<contextoExposicao>"}`:
  confirma a apresentação de um card previamente entregue pelo backend.

Descoberta por compatibilidade ranqueia candidatas filtradas e pagina o top 1000.
`total` e `hasMore` referem-se a esse conjunto limitado, não ao catálogo completo.
Outras ordenações paginam o catálogo filtrado no banco. Facetas refletem filtros.
O limite de 1000 evita prometer paginação ilimitada do endpoint atual de regras.
Preferências locais de salvos/descartes continuam locais; descarte não é recusa.

Uma consulta carrega candidatas em lote, não uma consulta por startup. Acima de
10.000 candidatas, as chamadas Python são divididas em lotes de até 10.000; o
top L de cada lote é combinado com o mesmo desempate do Nível 1. Chamadas são
sequenciais e versões divergentes abortam a resposta. Não há cache persistente
nem alteração do score. O frontend deixou de gerar compatibilidades aleatórias:
scores reais são mostrados quando disponíveis; nos demais casos ficam ausentes.

## Cliente e isolamento

`MATCHMAKING_API_URL` (default `http://127.0.0.1:8000`) e
`MATCHMAKING_TIMEOUT_MS` (default 5000; máximo 60000) são configuração exclusiva
do backend. Não há variável do FastAPI no frontend. `fetch` nativo valida os
contratos de entrada/saída, não segue redirects e limita a duração inclusive da
leitura do corpo. Erros de upstream são sanitizados: timeout 504, indisponibilidade
503, contrato/HTTP 4xx do upstream 502. Não há fallback para scores inventados.

O FastAPI continua com os endpoints existentes. Nesta execução local ele deve
escutar em `127.0.0.1`; não publicar a porta 8000 para navegadores. Em implantação
separada, usar rede privada/restrição de ingresso entre serviços. Não foi criada
autenticação entre serviços nesta etapa. CORS não substitui isolamento de rede.

## Semântica e idempotência da exposição

Card com pelo menos 50% de área no viewport durante 1000 ms contínuos, com aba
visível. Abertura do perfil, cálculo do ranking ou retorno da API não registram
exposição. Cards de descoberta, cards de matches e destaque usam o mesmo detector.
Sem suporte a IntersectionObserver, não se presume visibilidade.

O backend assina um contexto de 15 minutos vinculado ao investidor, startup,
posição/origem/versão e hash das features e revisão dos perfis. O browser envia
somente esse contexto, sem escolher IDs ou timestamp. Contexto adulterado/expirado
retorna 400; de outro investidor, 403; perfil alterado, 409; startup inelegível, 404.

Re-renderização, remount ou dois cards com o mesmo contexto compartilham deduplicação
no navegador. No banco a PK é o UUID emitido para o contexto: retries concorrentes
usam `ON CONFLICT DO NOTHING` e devolvem o registro original. Novo carregamento da
lista pode emitir novo contexto e representar uma nova apresentação; não há veto
permanente por par. Falhas são silenciosas, não navegam, não fazem logout e podem
ser tentadas novamente numa nova entrada no viewport. Não há fila offline durável.

O timestamp autoritativo é `clock_timestamp()` do PostgreSQL ao confirmar o evento,
não o relógio do cliente: semântica `card_50pct_1000ms_ack`. Há atraso entre a
visibilidade real e o reconhecimento pelo servidor. A confirmação do navegador é
uma declaração de telemetria, não uma prova antifraude de atenção humana.

## Tabela e snapshots

Migration **criada e não executada**:
`Juntai-Backend/src/shared/database/migrations/1793232000000-ExposicoesStartups.ts`.
Cria somente `exposicoes_startups` e índice por investidor/startup/data.

Campos: UUID da exposição, FKs investidor/startup, `ocorrido_em` timestamptz,
origem, posição opcional, versão opcional, `snapshot_perfis` jsonb, versão de
contrato, semântica e origem dos dados. FKs seguem exclusão em cascata dos perfis;
remoção do perfil também remove esse histórico. Não altera `funil_interacoes`.
O `down` recusa rollback automático para não apagar exposições coletadas.
`synchronize` foi fixado em `false`, independentemente do ambiente.

Na confirmação, a transação bloqueia perfis/usuários com leitura compartilhada,
revalida elegibilidade e compara os hashes ao contexto entregue. Só então captura
projeções permitidas para ML: preferências, categorias, métricas, tickets e
experiência. Não armazena nome, email, senha, bio, textos livres, URLs, cidade,
estado ou IDs de usuário no snapshot. Guarda IDs dos perfis para associação.
Mudanças entre entrega e confirmação excluem o registro, em vez de fabricar um
snapshot retroativo. O estado permanece bloqueado até a inserção.

## Compatibilidade com o pipeline

`app/supervised/backend_export.py` recebe uma projeção da linha exportada, sem
consultar o banco. `adapt_exposure(row)` valida e retorna `(Exposure,
ProfileSnapshot)`. `estado_em` corresponde ao reconhecimento do evento no banco.
Só deve ser usado em linhas produzidas por este fluxo transacional confiável.

A origem `real`/`sintetica` da linha deve determinar o lote de DatasetInput;
o adaptador não declara completude do histórico. Interações existentes continuam
com IDs de perfis e timestamps próprios. Interesse anterior ao reconhecimento
pode ser excluído conservadoramente pelo target. Nenhum interesse passado é
alterado ou preenchido artificialmente.

## Execução local

1. Configurar as duas variáveis do cliente no `.env` do **backend**, seguindo
   `.env.example`. Manter `VITE_API_URL` apontando para o backend conforme a
   configuração existente do frontend, nunca para 8000.
2. Revisar a migration e a lista de migrations pendentes. Aplicação ao banco
   existente depende de autorização do responsável; nenhum comando foi executado
   nesta entrega. `migration:run` aplica todas as pendentes, não apenas esta.
3. Após autorização e aplicação, iniciar Python com
   `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, backend com
   `npm.cmd run dev` e frontend com `npm.cmd run dev` em seus diretórios.
4. Entrar como investidor aprovado, abrir descoberta e observar que somente cards
   visíveis geram POST. O Network mostra requisições ao backend, sem acesso ao
   FastAPI. Repetir a confirmação com o mesmo contexto deve devolver o mesmo ID.
5. Antes de aplicar a migration, a consulta de recomendações pode ser testada;
   confirmação de exposição ainda falhará pela tabela ausente, sem bloquear a UI.

Não executar fluxos reais para testar persistência sem autorizar alterações de
dados reais. Os testes desta entrega usam exclusivamente fixtures e mocks.

## Verificação automatizada

Backend: `$env:ADMIN_DB_TEST='0'; node --test tests/*.test.cjs` e
`node node_modules/typescript/bin/tsc --noEmit`.
Frontend: `node --test tests/exposureVisibility.test.mjs`, `npm.cmd run typecheck`,
`npm.cmd run lint`. Testes frontend usam Node 24 com suporte a TypeScript nativo.
Python: `python -m pytest -q`.

Fixtures sintéticas de contrato estão em `tests/fixtures/matchmaking-contract.json`
nos repositórios Python e backend, permitindo testes independentes. A fixture
Python é verificada contra `RulesRequest` e `rank` reais, sem HTTP. Nenhuma métrica
sintética é apresentada como desempenho preditivo. Testes de persistência usam
mocks: aplicação SQL, FKs, locks e concorrência devem ser validados futuramente
em PostgreSQL descartável, não no banco principal.

## Próximos passos não executados

Autorizar/aplicar migrations revisadas, validar em banco descartável, definir
monitoramento de falhas da telemetria e retenção, coletar exposições e interações
reais, implementar exportação Node autorizada com watermark de completude e,
posteriormente, validar temporalmente e treinar o Nível 2. O adaptador Python não
é uma rota de exportação nem a integração de treinamento.
