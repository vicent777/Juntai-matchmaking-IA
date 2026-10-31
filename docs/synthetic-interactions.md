# Interações sintéticas — preparação do Nível 2

Este gerador lê investidores e startups existentes e simula exclusivamente
comportamento. Não cria perfis, escreve no PostgreSQL, chama APIs, treina modelos
ou altera os Níveis 1A/1B. O pipeline supervisionado existente é reutilizado sem
mudanças: `DatasetInput`, `ProfileSnapshot`, `build_dataset`, `build_features` e
`build_target`. Origem do lote: `sintetica`.

## Executar

Python instalado no sistema, sem ambiente virtual. Dependências adicionais
estão em `requirements-synthetic.txt` (psycopg2-binary e python-dotenv); na execução
validada ambas já estavam disponíveis. Caso necessário:

```powershell
python -m pip install -r requirements-synthetic.txt
```

A partir da raiz de `Juntai-matchmaking-IA`:

```powershell
python -m app.supervised.synthetic --env-file ../Juntai-Backend/.env --seed 42 --exposures 20000 --cutoff 2026-10-30T12:00:00Z --output data/synthetic/level2-seed42
python -m pytest tests/test_synthetic.py tests/test_supervised.py tests/test_backend_export.py -q
```

O corte é um relógio **simulado** explícito, com fuso. Reprodutibilidade exige a
mesma seed, quantidade, corte, versão do gerador/Python e mesmos perfis. Um
diretório de saída existente é recusado para preservar artefatos. Para repetir
sem consultar o banco, use os perfis exportados e outro diretório:

```powershell
python -m app.supervised.synthetic --profiles data/synthetic/level2-seed42/profiles.json --seed 42 --exposures 20000 --cutoff 2026-10-30T12:00:00Z --output data/synthetic/level2-seed42-replay
```

## Fonte e qualidade dos perfis

`source.py` inspeciona colunas, enums, constraints e índices. Conecta com
`default_transaction_read_only=on` e usa transação `REPEATABLE READ`, também marcada
somente de leitura. Todas as consultas de dados são `SELECT`. A configuração de
conexão nunca é exportada. Nenhum registro de `funil_interacoes` é misturado com
o comportamento simulado; do histórico real são lidas apenas contagens/hashes.

As projeções reutilizam os grupos de campos de `features.py`, com conversão
explícita de snake_case para camelCase, arrays de enums como `text[]` e preservação
de valores monetários Decimal. Incluem atividade e ID do usuário para o contrato
operacional, mas não nomes, emails, senhas, textos livres ou URLs. IDs e localização
continuam sendo dados vinculados à fonte: os arquivos devem permanecer locais.

Só entram perfis aprovados de usuários ativos do respectivo tipo, validados pelo
Pydantic. Investidores precisam de tipo, segmento e estágio de interesse;
startups precisam de segmento, estágio e modelo. Campos complementares ausentes
não são imputados. Intervalos de ticket inválidos e enums incompatíveis são
descartados com motivo, sem normalização silenciosa de valores legados. O enum
legado `regiao_enum` contém `recife`, `porto_digital` e `nacional`, mas esses
valores não apareceram nas projeções aproveitadas desta execução.

Na leitura validada: 3.002 investidores e 10.004 startups. Aproveitados: 3.001 e
10.001; quatro inelegíveis. Todos os aproveitados passaram pelos contratos, sem
descarte por dados inválidos ou mínimos insuficientes. Preferências principais,
ticket e risco estavam preenchidos em todos os investidores aproveitados;
campos auxiliares faltavam em um investidor e experiência setorial em 221.
Campos estruturados das startups estavam preenchidos nas 10.001 aproveitadas.
Isso comprova completude estrutural, não veracidade ou representatividade.

## Simulação e coerência temporal

- Aproximadamente 85% das exposições correspondem a pares únicos. As demais são
  novas exposições válidas do mesmo par, com UUIDs distintos. A consolidação
  existente produz uma linha por par ancorada na primeira exposição.
- A seleção combina exploração e segmentos declarados. Frequências seguem pesos
  lognormais; quando há pares suficientes, cada investidor aparece ao menos uma
  vez. Não há balanceamento por classe ou reamostragem condicionada ao target.
- Cada investidor recebe gostos latentes por setor e combinação de estágio/modelo,
  propensão individual e sensibilidade ao crescimento. O comportamento também
  considera experiência setorial, risco, tração e capital/ticket.
- A probabilidade logística inclui ruído gaussiano e sorteio Bernoulli. O gerador
  não consulta o score 1A, não reproduz seus pesos e não usa features de eventos.
  O 1A é chamado somente depois para diagnóstico, sem retroalimentar o lote.
- Primeiras exposições são distribuídas entre 1 e 120 dias antes do corte: há
  janelas encerradas e abertas. Interesse tem atraso positivo; uma parte é tardia
  (31–45 dias). Eventos posteriores ao corte não são exportados. Há no máximo
  um evento de interesse por par, além de visualizações opcionais.
- Snapshots copiam os perfis atuais e são fixos durante a simulação. Datas de
  snapshot iguais às exposições são válidas **apenas no mundo simulado**;
  `historico_confirmado=true` não afirma a existência de evidência histórica real.
  O mesmo vale para `historico_completo=true`: todo o histórico fictício desde a
  primeira exposição está disponível, não o histórico real dos usuários.

## Target, ausência de vazamento e arquivos

O pipeline aplica a janela de 30 dias: interesse em `(t0,t0+30 dias]` até o corte
é positivo; janela encerrada e sem esse interesse é negativa; janela aberta sem
interesse é censurada. Interesse tardio não converte a janela anterior em positiva.
Ausência de interesse não representa rejeição explícita. Nenhum evento `recusado`
é inventado. Históricos incompletos continuam sem target no contrato existente.

Features vêm exclusivamente do snapshot da primeira exposição; rótulos usam os
eventos posteriores. A exportação verifica a correspondência. Os arquivos são:

| Arquivo | Conteúdo |
|---|---|
| `profiles.json` | Projeções da fonte e qualidade; permite reprodução offline |
| `input.json` | Contrato `DatasetInput`: exposições, interações, snapshots e corte |
| `dataset.jsonl` | Uma `DatasetRow` por par, incluindo nulos e auditoria |
| `training.jsonl` | Apenas `features` e target 0/1, sem IDs/datas/eventos/auditoria |
| `quality.json` | Avisos do pipeline, incluindo censura e múltiplas exposições |
| `summary.json` | Estatísticas, versões, qualidade e evidências de preservação da fonte |
| `manifest.json` | SHA-256 dos outros arquivos |

`training.jsonl` é entrada para experimentos posteriores, não uma matriz já
codificada: listas, categorias, valores ausentes e seus indicadores preservam o
contrato. São 57 atributos (9 numéricos, 14 categóricos, 10 multivalorados e 24
derivados), acompanhados de 57 indicadores de ausência. Imputação, codificação,
divisão temporal/por entidade e treinamento não são executados.

O gerador executa duas vezes e compara o SHA-256 da entrada para verificar
reprodutibilidade. Os arquivos exportados são relidos, validados pelos contratos
e contados; todos os hashes do manifesto são verificados. Antes e depois da
execução são comparados contagens/hashes de todas as tabelas públicas e definições
de colunas/enums/índices/constraints. Uma mudança externa também interrompe a
validação. Nenhum banco descartável ou migration é necessário.

Todo `data/synthetic/` está ignorado no Git. O CLI limita a saída a subdiretórios
desse caminho e recusa sobrescrita. O `.gitignore` não impede um `git add -f`;
os artefatos não devem ser incluídos em commits.

## Execução de referência — seed 42

| Indicador | Resultado |
|---|---:|
| Investidores utilizados | 3.001 |
| Startups utilizadas | 7.962 |
| Exposições | 20.000 |
| Pares únicos | 17.000 |
| Exposições adicionais de pares existentes | 3.000 |
| Eventos de interesse explícito | 3.266 |
| Targets positivos em até 30 dias | 3.017 |
| Targets negativos | 11.058 |
| Targets indefinidos (censura) | 2.925 |
| Linhas exportadas para treinamento posterior | 14.075 |
| Taxa de interesse observado por par | 19,21% |
| Positivos entre linhas rotuladas | 21,44% |
| Pares descartados pelo pipeline | 0 |

Há 249 interesses tardios, que não tornam positivo o target de 30 dias. Foram
gerados 17.314 eventos totais, incluindo visualizações. Os oito segmentos e seis
estágios estão representados. Frequências por investidor: 1–69 exposições; por
startup utilizada: 1–13. Os avisos de múltiplas exposições são esperados e não
representam perda de pares. Não houve snapshot inválido ou evento futuro.

Como diagnóstico independente, há 1.482 pares com score 1A ≥ 0,8 e target negativo,
e 2.392 pares com score < 0,8 e target positivo. Isso evidencia divergência entre
regras e simulação, mas não demonstra que o comportamento seja realista.

O `juntai_db` permaneceu inalterado: as contagens e hashes de todas as tabelas,
bem como o schema inspecionado, coincidiram. `exposicoes_startups` continuou com
zero registros e `funil_interacoes` com um. Não houve alterações adicionais no
backend ou frontend nesta etapa.

## Limitações para generalização

Os exemplos podem servir para validar contratos e um futuro fluxo de treinamento,
mas qualquer desempenho mede a capacidade de aprender este simulador. Gostos,
ruído, propensões e atrasos são hipóteses arbitrárias, sem calibração em usuários.
Perfis do dump também podem ter padrões artificiais e não foram auditados quanto
à veracidade. Snapshots atuais não oferecem avaliação histórica real. Repetição
de entidades entre divisões pode inflar métricas; isso deve ser tratado quando
os experimentos forem autorizados. Não comparar modelos como evidência de
qualidade de recomendação real com base apenas neste lote.

Nenhum modelo foi treinado e nenhum endpoint supervisionado foi criado.

## Validação executada

`python -m pytest -q -p no:cacheprovider`: **171 aprovados e 1 ignorado**. O teste
ignorado é a integração opcional com embeddings reais, que exige ativação explícita
e pode baixar pesos; não é necessário para este gerador. Os testes novos cobrem
reprodutibilidade, IDs existentes, tempo, targets, ausência de vazamento por
eventos, comportamento independente do 1A, integridade dos arquivos, parâmetros
inválidos, fonte somente de leitura e rejeição de perfis inválidos/inelegíveis.

A reprodução offline completa de 20.000 exposições confirmou igualdade byte a
byte de `profiles.json`, `input.json`, `dataset.jsonl`, `training.jsonl` e
`quality.json`. `summary.json` e seu manifesto diferem intencionalmente na
proveniência: uma execução consultou o banco e a outra usou arquivos. A validação
de exportação confirmou 17.000 linhas de auditoria e 14.075 linhas rotuladas,
com todos os hashes válidos. Uma leitura final independente voltou a confirmar
que contagens/hashes das tabelas e schema coincidem com o início.
