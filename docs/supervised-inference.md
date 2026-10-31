# POST /match/supervised — inferência experimental do Nível 2

Endpoint aditivo do FastAPI. Não substitui `/match/rules`, não modifica
`/match/content` e não está integrado ao backend ou ranking principal. Não há
treinamento, acesso ao PostgreSQL, atualização do dataset ou gravação de eventos
durante inferência.

## Modelo e compatibilidade

Bundle padrão: `artifacts/supervised/level2-seed42-validated/`.
Arquivo carregado: `temporal/xgboost.joblib`, contendo `Preprocessor` ajustado e
`XGBClassifier`. O `.ubj` sozinho não contém imputação/encoders e não é usado pelo
endpoint. Modelo: `xgboost-level2-seed42-temporal-v1`.

- Contrato: `supervised-v1`.
- Features: `profiles-rules-v1`.
- Target: `first-interest-v1`; interesse explícito em até 30 dias.
- Treinamento: comportamento sintético, avaliação temporal; modelo experimental.
- Entrada de transformação: 110 colunas em ordem fixa; seleção ajustada de 47
  colunas e expansão para 178 features codificadas, sem IDs/cidades preditores.

O bundle possui manifesto, métricas, versões e seleção de colunas. Foi acrescentado
um registro de inferência versionado, `app/supervised/inference/trusted_model.json`,
sem modificar o bundle. Ele fixa os hashes dos artefatos, código normalizado de
features/contratos, dependências e listas ordenadas de colunas de entrada/saída.
O SHA-256 do pipeline autorizado é:

```text
0a63a678282ea0332894b2aef0425f5d98d0d845bc8b6d84541973785c92c6a6
```

Carregamento lazy e protegido por lock: uma única carga bem-sucedida por processo.
Não há fallback para outro modelo. Antes de desserializar são verificados os
hashes contra o registro externo ao bundle, o manifesto, origem/versões, código
de features e versões instaladas. O loader desserializa os bytes já verificados,
evitando reler um caminho que pudesse mudar entre hash e carregamento. Depois,
verifica os tipos, seleção, nomes/ordem codificados, quantidade de features e
classes `[0,1]`. Um manifesto colocado junto de um pickle não concede confiança.

Só diretórios locais resolvidos dentro de `artifacts/supervised/` são aceitos.
Arquivos que escapem do bundle por links também são recusados. Mudar a variável
de ambiente apenas muda o local de um bundle **idêntico ao autorizado**; não
autoriza novos modelos. Novos artefatos exigem validação e revisão explícita do
registro versionado. Não há parâmetros HTTP para selecionar arquivos/modelos.

## Iniciar e configurar

Python 3.12. As versões exatas das bibliotecas estão em
`requirements-supervised.txt`. Elas já estavam instaladas nesta implementação;
não houve instalação ou criação de ambiente virtual. Se necessário, o arquivo
pode ser usado para preparar outro ambiente compatível.

A partir da raiz do repositório, PowerShell:

```powershell
# Opcional: o valor abaixo já é o padrão. Reinicie o processo após alterá-lo.
$env:SUPERVISED_MODEL_DIR = 'E:\ViniciusDoc\Projetos\Juntai-matchmaking-IA\artifacts\supervised\level2-seed42-validated'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`.
Contrato: `http://127.0.0.1:8000/openapi.json`.
Em desenvolvimento com outro FastAPI já em 8000, use `--port 8001`; foi assim
que o teste HTTP desta implementação foi executado, sem interromper o serviço
existente. O processo temporário de teste foi encerrado ao final.

## Entrada

`investidor` reutiliza `InvestorProfile`; `startups` reutiliza `StartupProfile`,
ambos em `app/supervised/schemas.py`. Campos extras são proibidos. Datas, eventos,
labels, probabilidades latentes e features prontas não são aceitos. A inferência
reutiliza `build_features` e `flatten` do treinamento, sem reconstruir as regras.

| Campo | Contrato |
|---|---|
| `investidor` | Um perfil, com UUID do investidor obrigatório |
| `startups` | Lista de 1 a 10.000 perfis; UUIDs únicos obrigatórios |
| `limite` | Inteiro estrito de 1 a 1.000; padrão 24 |

Números financeiros, enums e contagens respeitam os validadores existentes.
Perfis incompletos são aceitos com avisos; tratamento de ausências é exatamente
o ajustado no treino. Categorias novas são ignoradas pelos encoders e sinalizadas.
Valores que eram constantes e foram removidos no treino não passam a influenciar
o modelo por estarem ausentes/agora variarem.

Elegibilidade reutiliza a avaliação operacional do 1A: usuário explicitamente
inativo, ID de perfil igual ao ID de usuário ou startup não aprovada são excluídos.
Sem informação operacional suficiente, há aviso de elegibilidade indeterminada;
a inferência de perfil incompleto continua disponível para comparação offline.
Isso não constitui autenticação ou autorização de investidores. O serviço permanece
uma API interna experimental, como as rotas existentes.

Exemplo de uma startup (IDs fictícios, sem banco):

```json
{
  "investidor": {
    "id": "11111111-1111-4111-8111-111111111111",
    "tipoInvestidor": "anjo_mentor",
    "usuario": {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "ativo": true},
    "segmentosInteresse": ["agtech"],
    "estagiosInteresse": ["mvp"],
    "regioesInteresse": ["nordeste"],
    "modelosInteresse": ["b2b"],
    "areasAjuda": ["mentoria"]
  },
  "startups": [{
    "id": "22222222-2222-4222-8222-222222222222",
    "usuario": {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "ativo": true},
    "statusModeracao": "aprovado",
    "segmento": "agtech",
    "segmentosSecundarios": [],
    "estagio": "mvp",
    "regioesAtuacao": ["nordeste"],
    "modeloNegocio": "b2b",
    "necessidadesAdicionais": ["mentoria"]
  }],
  "limite": 24
}
```

Pode-se enviar o exemplo já existente sem copiar JSON para um comando de shell:

```powershell
@'
import json, urllib.request
payload = json.load(open('tests/fixtures/matchmaking-contract.json', encoding='utf-8'))['request']
request = urllib.request.Request('http://127.0.0.1:8000/match/supervised', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request) as response:
    print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
'@ | python
```

## Saída e erros

O corpo inclui `investidorId`, identidade do modelo, versões de contrato/features/
target, `experimental=true`, `origemTreinamento="sintetica"`, janela de 30 dias,
`recomendacoes`, `excluidas` e avisos gerais. Cada recomendação também contém a
identidade/versões, UUID, probabilidade, posição e avisos individuais.

Trecho da resposta **real** do exemplo:

```json
{
  "modelo": "xgboost",
  "versaoModelo": "xgboost-level2-seed42-temporal-v1",
  "versaoContrato": "supervised-v1",
  "versaoFeatures": "profiles-rules-v1",
  "versaoTarget": "first-interest-v1",
  "experimental": true,
  "origemTreinamento": "sintetica",
  "recomendacoes": [{
    "startupId": "22222222-2222-4222-8222-222222222222",
    "posicao": 1,
    "probabilidadeInteresse": 0.1604514718055725
  }]
}
```

O trecho omite metadados repetidos e avisos por brevidade. A resposta completa do
exemplo sinaliza 20 entradas selecionadas ausentes e seis categorias/itens novos.
Não existe campo `score` na recomendação supervisionada. Probabilidades são
ordenadas de forma decrescente; empates usam UUID crescente. O limite é aplicado
depois da avaliação/ordenação. O resultado não usa o limiar F1 do experimento:
retorna probabilidades para ordenar, sem convertê-las em decisões binárias.

- Entrada inválida: HTTP 422, validação Pydantic.
- Artefato ausente/adulterado/incompatível ou dependência incompatível: HTTP 503
  com mensagem genérica, sem caminhos, hashes internos ou traceback na resposta.
- Previsão não finita, fora de `[0,1]`, shape inválido ou classes inconsistentes:
  HTTP 503; nenhuma probabilidade substituta é inventada.
- Todas as startups inelegíveis: resposta válida com recomendações vazias e
  respectivas exclusões; nenhuma candidata recebe probabilidade inventada.

Falhas de carga não são armazenadas como sucesso. Uma carga bem-sucedida mantém
o modelo autenticado em memória; mudanças de configuração/bundle requerem reinício.
Requisitos opcionais da inferência são importados só durante a carga; ausência do
modelo não impede os endpoints anteriores de funcionarem.

## Comparação real com 1A

Teste HTTP realizado em 8001 com os mesmos perfis do exemplo e uma segunda startup
idêntica nos demais campos, porém `fintech`/`escala`, UUID terminado em `3333`:

| Startup fictícia | Score 1A | Posição 1A | Probabilidade Nível 2 | Posição Nível 2 |
|---|---:|---:|---:|---:|
| `2222…2222` — agtech/mvp | 1,0000 | 1 | 0,16045147 | 1 |
| `3333…3333` — fintech/escala | 0,4500 | 2 | 0,09718776 | 2 |

Mesmo score 1A de 1 não implica interesse supervisionado de 100%. Os números
respondem a alvos distintos, não são combinados em fórmula híbrida e não se
substituem automaticamente no sistema. O endpoint de regras recebe apenas seu
contrato mínimo; campos supervisionados adicionais não são enviados para ele.

## Testes e limitações

```powershell
python -m pytest tests/test_supervised_inference.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Resultado: **24 testes novos aprovados**; suíte completa **205 aprovados e um
ignorado** (integração opcional de embeddings). O teste de artefato real não foi
ignorado nesta execução. Em um checkout sem o bundle local, os testes que exigem
o artefato o sinalizam como indisponível e não treinam substitutos.

Cobertura: uma/múltiplas startups, ranking, limite, empates reais com features
idênticas, ausência de efeito de IDs nas probabilidades, perfis incompletos,
categorias novas, entradas inválidas, inelegibilidade, modelo ausente, hashes
adulterados antes de unpickle, versão de dependência e ordem de features
incompatíveis, probabilidade inválida, carga concorrente única, comparação com 1A,
OpenAPI e Swagger. O teste compara a resposta ao `predict_proba` direto do pipeline
salvo, com tolerância absoluta de 1e-12, sem mockar a inferência do teste real.
Testes de falhas pontuais utilizam mocks explicitamente.

Um Uvicorn temporário confirmou HTTP 200 em `/match/supervised`, `/match/rules`,
`/docs` e `/openapi.json`. Nenhum modelo foi treinado novamente. O manifesto do
dataset e os artefatos de treinamento permaneceram intactos.

O XGBoost foi selecionado como candidato experimental, não definitivo. O teste
temporal sintético anterior teve ROC-AUC 0,6729 e AP 0,3440, com amostra pequena;
probabilidades não foram recalibradas em usuários reais. Perfis incompletos e
categorias novas podem estar fora da distribuição de treino. Snapshots de origem
não são reconstruções históricas. A resposta explicita essas limitações.

Integração Node.js, alteração do ranking principal, coleta de dados, deploy e
escolha definitiva de modelo continuam fora desta implementação.
