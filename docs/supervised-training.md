# Nível 2 — experimento supervisionado no cenário sintético

Treinamento offline de Regressão Logística, Random Forest e XGBoost. Nenhum
endpoint, integração ou deploy foi implementado. Nenhuma consulta ao PostgreSQL
é feita por este módulo. Backend, frontend, regras 1A, content-based 1B e gerador
sintético permanecem sem alterações nesta etapa.

## Comandos e ambiente

As dependências já estavam disponíveis no Python do sistema; não houve instalação
ou criação de ambiente virtual. `requirements-training.txt` registra as faixas
compatíveis usadas. Ambiente validado: Python 3.12, scikit-learn 1.5.1, XGBoost
3.1.2, NumPy 1.26.4, pandas 2.2.2 e joblib 1.4.2. As versões exatas, inclusive
SciPy/Python, ficam registradas em `metrics.json`.

```powershell
python -m pytest tests/test_training.py -q -p no:cacheprovider
python -m app.supervised.training --data data/synthetic/level2-seed42 --output artifacts/supervised/nova-execucao-seed42 --seed 42
python -m pytest -q -p no:cacheprovider
```

O CLI recusa sobrescrita e saídas fora de `artifacts/supervised/`, ignorado pelo
Git. A execução completa foi realizada inicialmente em `level2-seed42` e repetida
em `level2-seed42-validated`. **O relatório validado está em
`artifacts/supervised/level2-seed42-validated/metrics.json`.** A repetição aperfeiçoou
somente diagnósticos de ranking (excluindo grupos triviais) e ausência numérica;
divisões, modelos e limiares não foram alterados em função do teste.

Código em `app/supervised/training/`:

- `preparation.py`: contratos, allowlist, seleção e transformações.
- `splitting.py`: maturação, janelas temporais e reservas de entidades.
- `evaluation.py`: classificação, probabilidades, calibração, ranking e grupos.
- `experiment.py`: ajuste, baselines, persistência e comparação.
- `__main__.py`: execução por linha de comando; `__init__.py` define o pacote.

## Auditoria dos dados e features

O manifesto original e todos os hashes foram conferidos. A entrada foi revalidada
como `DatasetInput`; `dataset.jsonl` foi comparado integralmente ao resultado de
`build_dataset(input)`. O `training.jsonl` foi comparado às linhas rotuladas, com
igualdade de features/target. Versões esperadas: `supervised-v1`,
`profiles-rules-v1`, `first-interest-v1`; origem obrigatória `sintetica`.

São 17.000 pares únicos, sem pares ou exposições duplicados entre linhas. Há
14.075 rotulados e 2.925 censurados, que nunca entram no treinamento. As 3.000
exposições adicionais permanecem na auditoria do gerador; não viram linhas extras
ou exemplos compartilhados entre conjuntos.

Não se assume que todas as 114 entradas exportadas sejam úteis. Uma allowlist
baseada no contrato de features rejeita nomes inesperados em qualquer grupo.
Só entram atributos e derivações calculadas a partir do snapshot. IDs, timestamps,
posição de ranking, origem, eventos, targets e probabilidades latentes não são
features. As cidades de investidor/startup e seus indicadores são removidos por
granularidade e potencial quase identificação: restam 110 colunas candidatas.

No cenário principal foram removidas 62 constantes e uma duplicata exata,
restando 47 colunas de origem e 178 colunas após codificação. A seleção é refeita
no treino de cada cenário adicional, sem consultar a distribuição do teste.

Constantes e duplicatas exatas são identificadas **só no treino**. Campos de
cobertura, flags e vários indicadores são constantes neste dump; não agregam sinal.
Estados de critérios e suas pontuações podem ser redundantes, mas são informações
anteriores ao evento e não constituem vazamento de target. A listagem exata do que
foi mantido/removido fica em `preprocessing` de cada cenário.

Valores numéricos usam mediana de treino e padronização. Categorias usam one-hot;
listas usam multi-hot com vocabulário de treino. Valores novos na validação/teste
são ignorados pelos encoders. Não há resampling, balanceamento artificial ou
pesos de classe. Os três modelos recebem a mesma transformação em cada cenário.

Apesar da separação computacional, os snapshots são perfis atuais colocados numa
cronologia simulada. Logo, ausência de vazamento de eventos no pipeline não prova
validade histórica dos atributos para usuários reais.

## Divisão temporal e maturação

Um corte 70/15/15 direto das linhas deixaria labels de treino amadurecendo durante
as exposições de validação e não permitiria purga adequada entre validação/teste.
Também criaria seleção otimista se fossem aceitos positivos precoces, mas não
negativos ainda imaturos. Por isso **todas as classes exigem janela completa de
30 dias até o corte**, inclusive positivos conhecidos antes.

Após reservar dois intervalos de 30 dias, o tempo restante é dividido em
70/15/15; essas proporções são de tempo útil, não do número original de linhas.
Limites exatos são registrados no JSON, em UTC. Resumo das janelas semiabertas:

| Conjunto | Exposições simuladas em UTC | Negativos | Positivos | Total | Prevalência |
|---|---|---:|---:|---:|---:|
| Treino | 01/07/2026–23/07/2026 | 2.631 | 603 | 3.234 | 18,65% |
| Validação | 22/08/2026–26/08/2026 | 623 | 157 | 780 | 20,13% |
| Teste | 25/09/2026–30/09/2026 | 422 | 107 | 529 | 20,23% |

O fim da janela de qualquer exemplo de treino é anterior à primeira exposição de
validação; o mesmo vale de validação para teste. Há 13.626 exemplos plenamente
maduros. Ficam de fora 3.374 imaturos/nulos e 9.083 maduros nos intervalos de purga.
Essa redução é uma limitação material: uma única divisão com 529 exemplos de teste
não permite conclusões fortes ou escolha definitiva de modelo.

A avaliação principal permite recorrência de entidades: 313 investidores e 167
startups aparecem tanto em treino como em teste, sempre em pares diferentes.
Nem IDs nem cidades são usados, mas outros atributos podem identificar padrões
de entidades. Por isso foram executados dois cenários adicionais com reserva por
hash determinístico de ID/seed (~20%), usada apenas para separar os dados:

| Cenário | Treino | Validação | Teste | Positivos no teste |
|---|---:|---:|---:|---:|
| Investidor não visto | 2.548 | 614 | 110 | 23 |
| Startup não vista | 2.567 | 611 | 103 | 20 |

A entidade reservada está ausente tanto do ajuste quanto da validação. Cada
cenário refaz o pré-processamento e ajusta os três modelos exclusivamente no seu
treino, mantendo a cronologia. São testes exploratórios com amostra muito pequena.

## Modelos e seleção

- Regressão Logística: C=1, máximo de 1.500 iterações; features padronizadas.
- Random Forest: 250 árvores, profundidade máxima 8, mínimo 8 exemplos por folha,
  fração máxima de features 0,7.
- XGBoost: até 500 árvores, profundidade 3, learning rate 0,05, min child weight 8,
  regularização L2=5, amostragem de linhas/colunas 0,85. Early stopping após 30
  iterações sem melhora do log loss de validação. No cenário principal, melhor
  iteração 36 (contagem iniciada em zero).

Sem busca extensa. Seed 42 e dois workers para as árvores. Cada modelo recebe um
limiar escolhido pelo maior F1 em uma grade fixa de 19 valores na validação. Os
limiares principais foram 0,10 / 0,10 / 0,20. O teste não escolhe limiares,
hiperparâmetros, encoders ou modelo. Validação é compartilhada entre early
stopping e limiar, sem nested validation; o otimismo correspondente é reconhecido.

## Resultado principal — teste temporal

| Métrica | Regressão Logística | Random Forest | XGBoost |
|---|---:|---:|---:|
| ROC-AUC | 0,6290 | 0,6643 | 0,6729 |
| PR-AUC trapezoidal | 0,3069 | 0,3388 | 0,3403 |
| Average Precision | 0,3143 | 0,3455 | 0,3440 |
| Precision | 0,2278 | 0,2408 | 0,3245 |
| Recall | 0,8411 | 0,9159 | 0,5701 |
| F1 | 0,3586 | 0,3813 | 0,4136 |
| Log Loss | 0,4935 | 0,4778 | 0,4776 |
| Brier Score | 0,1566 | 0,1526 | 0,1532 |
| ECE, 10 bins | 0,0349 | 0,0329 | 0,0294 |
| Precision@1 (17 investidores elegíveis) | 0,7059 | 0,7059 | 0,7059 |

Matrizes de confusão: `[[TN,FP],[FN,TP]]`:

- Regressão Logística: `[[117,305],[17,90]]`.
- Random Forest: `[[113,309],[9,98]]`.
- XGBoost: `[[295,127],[46,61]]`.

Curvas de calibração por bin (n, probabilidade média e frequência observada) estão
no JSON. Não foi ajustado calibrador; Brier/ECE avaliam probabilidades brutas.
Bins altos têm poucas observações. ECE baixo isoladamente não comprova calibração.

O **XGBoost é o candidato exploratório indicado pela validação**, cuja AP foi
0,3081, versus 0,2720 da floresta e 0,2532 da regressão. No teste, RF supera
ligeiramente a AP e o Brier do XGBoost, enquanto XGBoost tem maior ROC-AUC, F1,
Precision e menor Log Loss. Não há vitória uniforme nem significância demonstrada.

ICs exploratórios de 95% do ROC-AUC: LR [0,5764;0,6879], RF [0,6172;0,7162],
XGB [0,6258;0,7261]. Eles se sobrepõem. O bootstrap de 200 reamostragens é por
linha, sem capturar dependência por entidade; não é um teste de superioridade.

## Baselines e ranking

O baseline probabilístico usa apenas a prevalência do treino (18,65%). No teste:
ROC-AUC=0,5, AP=0,2023, Log Loss=0,5043 e Brier=0,1616. Os três modelos melhoraram
esses indicadores neste corte sintético.

O 1A original foi reconstruído usando os mesmos snapshots e pares, sem alterar
algoritmo: ROC-AUC=0,6128 e AP=0,2658. Seu score é compatibilidade, **não uma
probabilidade calibrada**: não foram calculados Brier, Log Loss ou calibração para
ele. A comparação usa a afinidade `score` original para discriminação/ranking.

PR-AUC trapezoidal e Average Precision são distintas. Para um score constante, a
interpolação entre os extremos da curva pode gerar PR-AUC=0,6011 neste teste,
apesar de AP=0,2023 e ROC-AUC=0,5. Por isso a comparação com prevalência usa AP;
não interpretar aquele valor trapezoidal como superioridade do baseline.

Precision/Recall@K são macro médias somente entre investidores com pelo menos
max(K,2) candidatas, pelo menos um positivo e um negativo. Excluem-se grupos
triviais de uma única candidata ou classe única. Há somente **um** investidor
elegível para K=3: Precision@3=0,3333 e Recall@3=1 para os três modelos. Não há
investidor elegível para K=5/10. Assim, @K não sustenta comparação confiável.
Os resultados descrevem somente as candidatas expostas e rotuladas presentes no
teste, não recuperação de todo o catálogo e nem avaliação online de recomendação.
Mesmo para K=1, somente 17 dos 466 investidores têm ambas as classes e pelo menos
duas candidatas: a macro média não representa todos os investidores do teste.

## Generalização, overfitting e importância

| Modelo | ROC-AUC treino | Validação | Teste |
|---|---:|---:|---:|
| LR | 0,7127 | 0,5797 | 0,6290 |
| RF | 0,9132 | 0,6020 | 0,6643 |
| XGB | 0,7145 | 0,6057 | 0,6729 |

Há evidência forte de sobreajuste na RF (gap treino/teste ~0,249). LR e XGB
também têm gaps (~0,084 e ~0,042), e diferenças entre períodos. Não se ajustaram
hiperparâmetros para melhorar os resultados de teste.

| Teste de entidade inédita — ROC-AUC | LR | RF | XGB | 1A |
|---|---:|---:|---:|---:|
| Investidor | 0,6532 | 0,6667 | 0,6632 | 0,5172 |
| Startup | 0,6687 | 0,6596 | 0,6964 | 0,7352 |

No teste de startups inéditas, o 1A supera os modelos em ROC-AUC. XGBoost tem AP
0,4131 versus 0,3855 do 1A nesse cenário, mas são apenas 20 positivos. Não há
evidência de superioridade geral do supervisionado nem de vencedor estável.

Coeficientes LR e importâncias nativas de RF/XGB são exportados por coluna
codificada. RF destaca correspondência com experiência setorial, crescimento e
clientes; XGB destaca experiência setorial, estágio, segmento e perfil de risco.
Coeficientes geográficos da LR podem refletir associações espúrias. Importância
de árvore favorece alguns tipos de variável e não é evidência causal.

Métricas por segmento/estágio exigem ao menos 30 exemplos e ambas as classes.
Subgrupos menores são omitidos do JSON para evitar números sem suporte. Também
são exportadas métricas com/sem ausências existentes e um cenário artificial em
que nove medidas numéricas e capital/ticket são ocultados, com flags atualizados.
Os demais campos permanecem fixos; esse stress não substitui dados reais com
ausência, e indicadores constantes removidos no treino não passam a ser aprendidos.

## Artefatos, testes e limites

`metrics.json` consolidado contém auditoria da fonte, versões, limites das janelas,
classes, transformações, limiares, modelos, calibração, incerteza e diagnósticos.
Cada cenário tem `split.json`, `metrics.json`, três pipelines `.joblib`, predições
de teste por modelo e o XGBoost também em `.ubj`. Os pipelines contêm seleção de
colunas, imputação, scaler, one-hot/multi-hot e classificador. Recebem o DataFrame
produzido por `flatten`; não são diretamente um endpoint para perfis brutos.

As predições são conferidas após salvar/recarregar cada pipeline. `manifest.json`
contém SHA-256 de todos os artefatos e o hash do manifesto dos dados. Artefatos
podem conter IDs, categorias e estruturas aprendidas; permanecem locais/ignorados.

Testes automatizados cobrem purga temporal, exclusão de positivos imaturos,
duplicatas, entidades não vistas, allowlist, categorias novas, medianas de treino,
seleção de constantes/duplicatas, serialização, métricas e ranking não trivial.

Resultado executado: **181 testes aprovados e 1 ignorado**. O teste ignorado exige
ativação explícita para carregar embeddings reais e não participa do treinamento
supervisionado. A repetição dos nove ajustes (3 modelos × 3 cenários) confirmou
divisões idênticas e probabilidades iguais com tolerância absoluta de 1e-12;
diferença máxima observada de 1,11e-16. Os 28 hashes de artefatos conferiram, os
JSONs de métricas foram verificados sem valores não finitos e o manifesto/dataset
original foi novamente validado, sem alterações.

Não houve instalação de dependências, criação de `.venv`, acesso ao banco,
modificação do gerador, treinamento do 1B ou alteração de serviços. Estes modelos
aprendem um simulador com gostos latentes e ruído arbitrários; não representam
validação de interesse de usuários reais. O passo seguinte exige decisão do
usuário, e não foi escolhido ou integrado um modelo definitivo.
