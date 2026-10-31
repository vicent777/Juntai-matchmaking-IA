# Exportação offline de exposições persistidas — três origens

`app/supervised/backend_export.py` aceita `discovery`, `rules` e `supervised`,
incluindo as exposições permitidas pela migration `ExposicoesSupervised1793404800000`.
O adaptador nunca consulta o PostgreSQL ou perfis atuais: recebe uma projeção
exportada e validada da tabela `exposicoes_startups`.

## Contrato completo

`StoredExposure` recebe os 11 campos da tabela: `id`, `investidor_id`, `startup_id`,
`ocorrido_em`, `origem_recomendacao`, `posicao_ranking`, `versao_recomendador`,
`snapshot_perfis`, `versao_contrato`, `semantica` e `origem_dados`.

- UUIDs de perfil e snapshot precisam corresponder; timestamps exigem timezone.
- Contrato `supervised-v1`, semântica `card_50pct_1000ms_ack`, origem dos dados
  `real` ou `sintetica`, sem campos extras.
- Posição, quando presente, é inteiro estrito positivo; versão, quando presente,
  tem de 1 a 100 caracteres, como o limite da coluna PostgreSQL.
- Para `supervised`, posição e versão não vazia são obrigatórias, conforme os
  contextos emitidos pelo backend. Não se preenchem metadados perdidos com a
  versão atualmente instalada do modelo.
- Para `rules` e `discovery`, valores nulos de posição/versão continuam aceitos.
- Os snapshots reutilizam `InvestorProfile`/`StartupProfile`, que já reconheciam
  `estado`, atributos financeiros, métricas, preferências e indicadores opcionais.
  Não foi necessário alterar os contratos de features ou artefatos treinados.

O backend supervisionado persiste a projeção de `investorFeatures` e
`startupFeatures` acrescida de `estado` em cada perfil. Não persiste probabilidade,
usuário, nome, email ou senha dentro do snapshot. A fixture
`tests/fixtures/stored-supervised-exposure.json` reproduz essa estrutura, com IDs
fictícios, números/strings monetárias compatíveis e origem `sintetica` explícita.

## Adaptação e dataset

`adapt_exposure(row)` mantém sua interface: devolve `(Exposure, ProfileSnapshot)`.
Preserva origem, posição e versão, valida associação dos perfis e usa apenas
`snapshot_perfis` para os atributos. `build_dataset` seleciona a primeira exposição
do par e registra origem, posição e versão em **auditoria**, fora de `features`.
O campo `versao_recomendador` guarda a versão XGBoost sem renomear ou interpretar
seu conteúdo como variável preditora.

Exemplo offline, sem conexão ou escrita no banco:

```python
import json
from pathlib import Path
from app.supervised import DatasetInput, build_dataset
from app.supervised.backend_export import StoredExposure, adapt_exposure

row = json.loads(Path('tests/fixtures/stored-supervised-exposure.json').read_text(encoding='utf-8'))
stored = StoredExposure.model_validate(row)
exposure, snapshot = adapt_exposure(row)
dataset = build_dataset(DatasetInput(
    exposicoes=[exposure], snapshots=[snapshot], interacoes=[],
    data_corte='2026-02-10T12:00:00Z', historico_completo=True,
    completo_ate='2026-02-10T12:00:00Z', origem_dados=stored.origem_dados,
))
```

O resultado é uma linha negativa, com `startup.estado=PE`, capital/ticket máximo
igual a 2 e origem/versão/posição na auditoria. Um interesse após cinco dias
torna o target positivo, sem mudar nenhuma feature. A fixture e as interações
desse exemplo são exclusivamente sintéticas; completude refere-se ao cenário
fictício testado.

## Ausência de vazamento e limites históricos

Probabilidade prevista, target ou datas adicionados ao registro/snapshot como
atributos são rejeitados pelo contrato estrito. Metadados dos eventos podem
conter valores arbitrários, mas não são lidos por `build_features`. Mudanças em
ranking, versão do modelo ou interações alteram auditoria/labels, não features.
Nenhuma informação atual é consultada para completar um snapshot antigo.

Snapshots antigos sem `estado` ou métricas opcionais continuam válidos: os valores
permanecem ausentes e seus indicadores são preservados. Isso não torna esses
registros equivalentes em cobertura aos novos, nem autoriza reconstrução retroativa.

O timestamp da exposição é o ACK do PostgreSQL (`ocorrido_em`), não o instante
exato de exibição ou da resposta de recomendação. O backend compara revisões dos
atributos entre recomendação e confirmação e só persiste o snapshot se ainda
corresponder. O adaptador usa esse contrato: `estado_em=ocorrido_em` e
`historico_confirmado=true` declaram o snapshot recebido como persistido, mas não
autenticam a fonte nem comprovam por si só um histórico arbitrário. Deve-se usar
uma exportação autorizada; não substituir o snapshot por perfis atuais. Se essa
garantia não existir em importações históricas, não encaminhá-las como exemplos
confirmados. Não há informação suficiente para inventar datas/revisões faltantes.

A regra de target de 30 dias não mudou: positivo em `(t0,t0+30 dias]`, negativo
somente com janela encerrada e histórico completo; caso contrário, target nulo.
Interesse em t0 é tratado como prévio; tardio não reclassifica a janela anterior;
eventos após o corte são reportados e ignorados. Ausência de interesse não é
rejeição explícita.

## Pendências para dados reais

- Exportar exposições **e o histórico completo de interações** de fonte autorizada,
  preservando snapshots e versões originais, sem fabricar evidência histórica.
- Conferir `StoredExposure.origem_dados` antes de montar cada lote. A dupla
  retornada pelo adaptador não contém a origem do lote: o chamador precisa passá-la
  explicitamente a `DatasetInput` e manter lotes reais/sintéticos separados.
- Declarar completude somente quando comprovada desde o início dos pares até o
  corte; respeitar 30 dias de maturação e excluir targets nulos do treinamento.
- Avaliar cobertura, seleção/exposição por estratégia, mudanças de versões e
  viés de feedback de modelos que decidiram quais candidatas seriam exibidas.
- Fazer divisão temporal e pré-processamento ajustado apenas no treino. A versão
  do modelo e sua probabilidade não devem virar atalhos para prever o próprio
  comportamento de seleção.

Nenhuma coleta, exportação de produção, novo treinamento, ativação de estratégia
ou integração adicional foi executada por este ajuste.

## Testes

```powershell
python -m pytest tests/test_backend_export.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Os testes cobrem as três origens, interface legada, versão XGBoost, snapshot com
estado, associação de IDs, valores ausentes/inválidos, rejeição de features
indevidas, maturação/censura, interesse prévio/tardio/futuro, ausência de vazamento
por eventos/metadados e repetição determinística do dataset.

Resultado executado: **235 aprovados e um ignorado** na suíte completa; o teste
ignorado é a integração opcional de embeddings reais. Os 28 hashes dos artefatos
treinados e os seis hashes do manifesto do dataset sintético foram reconferidos.
As chaves da fixture foram também comparadas, somente em memória, com
`supervisedInvestorFeatures`, `supervisedStartupFeatures` e `project` reais do
backend: ambas as projeções e os 11 campos persistidos conferiram. Nenhuma conexão
ao PostgreSQL foi aberta nesta etapa, e backend/frontend não foram modificados.
