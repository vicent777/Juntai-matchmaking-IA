# Dataset supervisionado v1

Pipeline offline: `DatasetInput.model_validate(payload)` seguido de
`build_dataset(entrada)`. Não conecta ao banco, não chama HTTP e não treina modelos.
Usa apenas Pydantic e biblioteca padrão. Nível 1 e content-based permanecem intactos.

## Contrato e origem

Perfis são projeções com os nomes camelCase das entidades TypeORM. Não enviar
entidades inteiras: identidade pessoal, textos, URLs e campos não selecionados são
rejeitados por `extra='forbid'`. `Interaction` recebe a projeção SQL explícita
`id, investidor_id, startup_id, tipo_evento, ocorrido_em, metadados`.
O backend deverá mapear `tipoEvento`/`ocorridoEm` e relações para esses campos quando
exportar entidades, e preservar bigint como string. Exposição e snapshot são
contratos novos de intercâmbio; não representam tabelas já existentes.

UUIDs identificam perfis, não usuários. Timestamps precisam de timezone. Dinheiro
aceita strings decimais do PostgreSQL, em BRL, sem conversão cambial. Valores
negativos, não finitos, precisão maior que numeric(14,2) e intervalos de ticket
invertidos são erros. Não há clipping ou imputação silenciosa. Crescimento aceita
valores negativos dentro da precisão numeric(6,2); seus períodos e métricas são
preservados. Contagens seguem limites dos tipos reais do backend.

`origem_dados` é obrigatório (`real` ou `sintetica`). Não misturar origens em um lote.
Essa marca e a completude são declarações da fonte, não verificações de autenticidade.

## Snapshot e primeira exposição

O snapshot referencia `exposicao_id`, contém os dois perfis e declara
`historico_confirmado=true`. `estado_em` deve representar exatamente o instante da
exposição (igualdade de instantes, mesmo com fusos diferentes). É o instante do
estado histórico, não o horário de exportação. Versões antigas só podem ser
adaptadas pela fonte se ela comprovar que continuavam válidas nesse instante.
Não preencher automaticamente com o estado atual do banco.

Seleciona-se a primeira exposição contratualmente válida até o corte, por par;
empates usam o ID como desempate determinístico. Validade operacional da exposição
é responsabilidade da fonte autorizada. Snapshot ausente/não confirmado/com data
diferente exclui o par e gera qualidade: não se tenta uma exposição posterior.
Pares inconsistentes, snapshots órfãos ou IDs reutilizados com conteúdo diferente
levantam erro. Duplicatas idênticas são consolidadas com aviso. Exposições repetidas
do mesmo par e interesses distintos repetidos também geram avisos; seus IDs ficam
na auditoria. Eventos sem exposição são reportados e não criam exemplos.

## Target e completude

Janela padrão: 30 dias de 24 horas, configurável por `janela_dias`. Instantes de
referência são normalizados para UTC. Intervalo positivo: `(t0, t0 + janela]`.
Interesse exatamente em t0 é tratado conservadoramente como interesse prévio,
pois não há ordem comprovada entre ações simultâneas.

- Interesse até t0: `interesse_previo`, sem target.
- Histórico incompleto: `historico_incompleto`, sem target, mesmo com interesse
  observado; sem o passado completo não se comprova primeira conversão.
- Primeiro interesse dentro da janela e até o corte: positivo (1), inclusive se
  a janela ainda estiver aberta.
- Janela encerrada sem esse interesse: negativo (0), se o histórico é completo.
- Janela aberta sem interesse: censurado, sem target.
- Interesse tardio não altera o negativo daquela janela.

`historico_completo=true` declara cobertura desde o início da vida dos pares até
`completo_ate`, que precisa ser maior ou igual ao corte. Não basta exportar apenas
os eventos da janela. Por padrão a declaração é falsa. Eventos posteriores ao
corte são reportados e ignorados, inclusive na auditoria da linha. Metadados de
eventos nunca entram nas features. O target não depende de scores do Nível 1.

## Features e saída

Adaptador chama diretamente `app.rules.CRITERIA`, preservando score, cobertura,
estado e avaliação parcial de cada critério. Não copia regras nem altera ranking.
Inclui atributos numéricos, categorias, listas ordenadas sem repetições, contagens
de correspondência e razão capital/ticket máximo. Essa razão é descritiva e nunca
um filtro de incompatibilidade. Ticket zero deixa a razão ausente.

Dados ausentes ficam como `None` e indicadores; listas vazias são sinalizadas como
preferência/característica não informada, não incompatibilidade automática.
Valores extremos válidos são preservados. Imputação, escala e encoders ajustados
devem ser treinados somente após divisão temporal. Não há aprendizado nesta etapa.

Cada registro separa `metadados`, `features`, `rotulo` e `auditoria`; tem versões de
contrato, features e target. IDs e posição no ranking ficam fora das features.
`qualidade` lista exclusões, duplicatas, censura e limitações. Linhas sem target
são mantidas para auditoria, mas devem ser excluídas de qualquer treinamento.
`model_dump(mode='json')` produz estrutura conversível futuramente com
`pandas.json_normalize`; pandas não é uma dependência desta etapa.

## Exemplo e testes

```powershell
python -m app.supervised.example
python -m pytest tests/test_supervised.py tests/test_rules.py tests/test_eligibility.py -q
```

O exemplo contém um investidor, duas startups, duas exposições em 01/01/2026,
um interesse em 06/01/2026 e corte em 10/02/2026, com histórico completo. Produz:

| Exposição | Segmento | Score segmento | Capital BRL | Ticket máximo BRL | Razão | Target |
|---|---|---:|---:|---:|---:|---:|
| exemplo-1 | agtech | 1 | 5000 | 1000 | 5 | 1 |
| exemplo-2 | fintech | 0 | 5000 | 1000 | 5 | 0 |

Demais critérios sem informação têm score `None`, cobertura zero e indicadores de
ausência. A saída executável mostra todas as features. Nenhum resultado sintético
é evidência de desempenho preditivo.

## Dependências futuras

Antes de dados treináveis: persistir exposições reais, comprovar snapshots e
completude, definir retenção e acumular interações diversas. Depois, integrar a
exportação autorizada Node.js → Python. Só então implementar divisão temporal,
baseline supervisionado, calibração e avaliação de ranking. Nada disso é executado
por este módulo. Um registro histórico sem exposição/snapshot não se torna exemplo
válido apenas por possuir perfis atuais.
