# Juntaí — Serviço de recomendação

Nível 1A determinístico com dados estruturados e Nível 1B independente com
embeddings locais dos textos enviados pelo backend. Não acessa PostgreSQL,
dump ou arquivos de perfis. O modelo semântico pode baixar pesos públicos no
primeiro uso; a inferência é local. Não implementa ranking híbrido ou aprendizado
supervisionado.

## Arquitetura e execução

Frontend React → Backend Node.js → HTTP/JSON → FastAPI → regras puras.

- `app/main.py`: HTTP e endpoints existentes `/` e `/health` preservados.
- `app/schemas.py`: validação Pydantic de entrada e saída.
- `app/rules.py`: critérios isolados, pesos, explicações e ranking.
- `tests/test_rules.py`: únicos dados sintéticos operacionais do projeto.

Python 3.10 ou superior. A partir da raiz, no Python já disponibilizado:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em Windows, `py` pode substituir `python`. Não é necessário criar `.venv`.
Em execução, `/docs` e `/openapi.json` descrevem os contratos completos.

## Contrato HTTP v1

`POST /match/rules` recebe um objeto com:

| Campo | Tipo / regra |
| --- | --- |
| `investidor` | Objeto obrigatório; `id` UUID de **Investidor**, não de Usuario |
| `investidor.segmentosInteresse` | Lista de Segmento |
| `investidor.estagiosInteresse` | Lista de Estagio |
| `investidor.regioesInteresse` | Lista de Regiao |
| `investidor.modelosInteresse` | Lista de ModeloNegocio |
| `investidor.areasAjuda` | Lista de AreaAjuda |
| `startups` | Lista obrigatória, até 10.000 candidatas, IDs únicos |
| `startups[].id` | UUID de **Startup**, não de Usuario |
| `startups[].segmento` | Segmento ou null |
| `startups[].segmentosSecundarios` | Lista de Segmento |
| `startups[].estagio` | Estagio ou null |
| `startups[].regioesAtuacao` | Lista de Regiao |
| `startups[].modeloNegocio` | ModeloNegocio ou null |
| `startups[].necessidadesAdicionais` | Lista de NecessidadeAdicional |
| `limite` | Inteiro de 1 a 1.000, padrão 10; não aceita booleano/string |

Listas omitidas viram `[]`. Listas explicitamente null são inválidas; escalares
opcionais omitidos viram null. Listas vazias indicam informação insuficiente,
nunca preferência universal. Duplicatas dentro de listas não aumentam scores.
Campos extras são rejeitados, evitando envio de entidades completas.

Enums conferidos nas entidades TypeORM e `src/shared/enums/index.ts` do backend:

- Segmento: `fintech`, `healthtech`, `edtech`, `agtech`, `saas_b2b`,
  `marketplace`, `ecommerce`, `economia_criativa`.
- Estagio: `ideacao`, `validacao`, `mvp`, `tracao`, `crescimento`, `escala`.
- Regiao: `norte`, `nordeste`, `centro_oeste`, `sudeste`, `sul`.
- ModeloNegocio: `b2b`, `b2c`, `b2b2c`, `marketplace`, `assinatura_saas`.
- AreaAjuda: `mentoria`, `networking`, `operacoes`, `vendas_marketing`, `growth`,
  `financeiro_juridico`, `produto_tecnologia`, `rh_pessoas`.
- NecessidadeAdicional: `mentoria`, `conexoes_mercado`, `contratacao_talentos`,
  `parcerias_estrategicas`, `outro`.

As duas entidades têm relação OneToOne com Usuario e UUID próprio. A validação
de formato não prova que o UUID existe ou pertence à entidade correta: o backend
deve resolver essa identidade e aplicar autorização antes de chamar a IA.

Resposta: `investidorId`, `versaoAlgoritmo`, `pesos` e `recomendacoes` ordenadas.
Cada item contém `startupId`, `posicao` (a partir de 1), `score`, `scoreRanking`, `criterios`,
`cobertura`, `criteriosAvaliados`, `justificativas` e `avisos`.
Cada critério informa `estado`, `score`, `cobertura`, `avaliacaoParcial`, `evidencias` e `aviso`.
`avaliacaoParcial` distingue cobertura parcial de compatibilidade parcial:
necessidades conhecidas podem ser todas compatíveis (`estado=compativel`) mesmo
quando outras necessidades não puderam ser avaliadas (`avaliacaoParcial=true`).
Estados: `compativel`, `parcial`, `incompativel`, `insuficiente`.

Score e cobertura estão em [0, 1]. Score null significa que não há critério
avaliável. Não é substituído por zero: zero representa incompatibilidade
identificada. Lista vazia de candidatas retorna ranking vazio. Não há corte
automático por score; inclusive incompatíveis e não avaliáveis podem aparecer.
Erros de validação retornam HTTP 422 com detalhes Pydantic.

## Regras e pesos iniciais

| Critério | Peso | Regra |
| --- | --- | --- |
| Segmento | 30 | Interseção entre interesses e segmento principal + secundários |
| Estágio | 25 | Estágio presente nas preferências |
| Região | 20 | Qualquer interseção entre preferências e regiões de atuação |
| Modelo | 15 | Modelo presente nas preferências |
| Ajuda | 10 | Fração de necessidades distintas atendidas |

Os quatro primeiros critérios são binários (1 ou 0), quando avaliáveis.
Segmentos principal e secundários têm o mesmo valor nesta versão; múltiplas
correspondências não acumulam pontos. Preferências são alternativas aceitáveis,
não requisitos cumulativos. Sem segmento principal e sem correspondência nos
secundários, não se conclui incompatibilidade; o critério fica indisponível.

Pesos centralizados em `WEIGHTS`, em `app/rules.py`. Segmento e estágio recebem
maior peso por descreverem a área e a maturidade procuradas; região e modelo
complementam esse alinhamento. Ajuda tem peso menor por exigir equivalências
de vocabulário. São hipóteses de negócio, **sem validação científica**.
A função `rank` aceita uma configuração alternativa completa no servidor;
o consumidor HTTP não escolhe pesos. Todos devem ser finitos e positivos.
Mudanças de regras ou pesos devem atualizar a versão do algoritmo.

Equivalências de ajuda, centralizadas em `HELP_MAP`:

| Necessidade | Área que pode atendê-la | Justificativa |
| --- | --- | --- |
| `mentoria` | `mentoria` | Mesmo conceito explícito |
| `conexoes_mercado` | `networking` | Oferta de rede de contatos |
| `contratacao_talentos` | `rh_pessoas` | Apoio de recursos humanos |

Essas correspondências são hipóteses a validar com o produto, não uma equivalência
entre os enums inteiros. Não se presume que growth atenda mentoria ou networking
atenda toda parceria estratégica. `parcerias_estrategicas` e `outro` não têm
mapeamento. Necessidades conhecidas são avaliadas normalmente: o score de ajuda
é a quantidade atendida dividida pela quantidade conhecida, usando conjuntos
sem duplicatas. Necessidades não mapeadas não contam como incompatibilidade e
são listadas no aviso. Em listas mistas, `avaliacaoParcial=true` e a cobertura de
ajuda é `quantidade conhecida / quantidade total de necessidades distintas`.
Sem necessidades conhecidas, ou sem áreas de ajuda informadas, o critério fica
insuficiente com score null e cobertura zero. As evidências e justificativas
contêm exclusivamente correspondências reais.

## Normalização, cobertura e ordenação

Para critérios avaliáveis A, com peso w e score c:

- `score = soma(w * c em A) / soma(w em A)`.
- `cobertura = soma(w * cobertura do critério) / soma(w de todos os critérios)`.
- `criteriosAvaliados = quantidade de critérios em A`.
- `scoreRanking = score * (0.5 + 0.5 * cobertura)`.

Nos critérios totalmente avaliáveis, a cobertura individual é 1; indisponíveis
têm cobertura 0. Ajuda pode ter cobertura fracionária. A afinidade preserva a
normalização por critérios com score disponível: a fração avaliável de ajuda
afeta a cobertura, sem reduzir seu peso na afinidade. `criteriosAvaliados` conta
também critérios parcialmente avaliados; para medir completude use cobertura.

Critérios indisponíveis não entram no numerador nem no denominador. Sem A,
score e scoreRanking são null e cobertura zero. A cobertura é ponderada, não uma estimativa
estatística de confiança. Score 1 com cobertura 0,30 pode usar somente setor;
score 1 com cobertura 1 usa todos os critérios. Sempre apresentar ambos.

Ordenação: scoreRanking decrescente (null ao final), cobertura decrescente e UUID
canônico crescente. Não depende da ordem de entrada. O limite é aplicado após
ordenar, e as posições são sequenciais. O campo `score` continua sendo afinidade;
`scoreRanking` incorpora cobertura sem modificar os pesos 30/25/20/15/10.
A fórmula é uma heurística experimental, não uma probabilidade estatística de
interesse. Ambos os scores ficam em [0, 1]. Na versão `1a-v2`, uma startup A com
afinidade 1 e cobertura 0,30 tem scoreRanking 0,65; uma startup B com afinidade
0,85 e cobertura 1 tem scoreRanking 0,85 e aparece primeiro.

Justificativas são emitidas somente para critérios com contribuição positiva,
com evidências extraídas das correspondências. Incompatibilidades ficam
explícitas no resultado individual; informações insuficientes geram avisos.
O score é afinidade por regras, não probabilidade de interesse ou investimento.

## Exemplo verificável e testes

Para manter dados sintéticos exclusivamente em testes, a fixture `payload` em
`tests/test_rules.py` é o exemplo de entrada: investidor e startup com todos os
cinco critérios alinhados. `test_complete` e `test_http` verificam a saída com
score 1, cobertura 1 e cinco justificativas, preservando os UUIDs de entrada.
`test_partial_weighted_score` altera apenas estágio e verifica score 0,75;
`test_no_evaluable_criteria` verifica score null e cobertura zero.

A suíte cobre compatibilidade total/parcial/nula, ausências, listas vazias,
enums e limites inválidos, equivalências, secundários, duplicatas, configuração
de pesos, explicações, limites dos scores e HTTP. O teste de ranking verifica
as 120 permutações de cinco candidatas, incluindo desempates e score null.

## Integração futura e limites

- Backend consulta PostgreSQL e envia apenas a projeção do contrato acima.
- Backend autentica, autoriza e filtra perfis ativos/aprovados; este serviço
  não verifica elegibilidade, existência dos IDs ou consentimentos no banco.
- **O endpoint não tem autenticação própria: protegê-lo contra acesso público
  por rede privada ou gateway na integração.** Não publicar diretamente.
- Backend deve definir timeout, tratamento de falha e validação da resposta;
  associar IDs retornados aos perfis públicos e preservar a ordem do ranking.
- Frontend deve substituir compatibilidade ilustrativa e mostrar cobertura,
  justificativas e ausência de score sem converter null em percentual zero.
- Não há integração Node.js, leitura do banco, cache de perfis ou
  persistência de recomendações. Payload limitado por quantidade de candidatas;
  limites de bytes e taxa deverão ser definidos no gateway.
- Dependências usam faixas de versões; ainda não há lockfile reprodutível.
- Campos opcionais no contrato permitem projeções incompletas; isso não altera
  os campos obrigatórios do esquema TypeORM.

## Nível 1B — conteúdo semântico independente

`POST /match/content` compara textos usando o modelo
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, localmente em CPU.
O Nível 1A compara atributos estruturados e fornece evidências de regras. O
Nível 1B compara vetores textuais; não utiliza os pesos, cobertura ou scoreRanking
do 1A, nem combina seus resultados nesta etapa.

### Dependências e ciclo de vida

Instale apenas se for executar inferência real:

```sh
python -m pip install -r requirements-content.txt
```

Isso adiciona `sentence-transformers` e dependências transitivas como PyTorch,
Transformers e NumPy. Sem GPU, API paga ou credenciais externas. O download inicial
dos pesos públicos exige internet e espaço em disco, além do espaço das bibliotecas.
O cache padrão do Hugging Face é utilizado; depois de provisionado completamente,
a inferência pode operar offline (por exemplo, `HF_HUB_OFFLINE=1`).

Nenhum modelo é importado/carregado durante a importação da API ou coleta dos
testes. O primeiro encode real carrega o modelo e mantém uma instância por
processo. Workers diferentes mantêm cópias próprias. Um lock protege a carga e
serializa inferências para limitar concorrência de CPU/memória. Falhas de carga
ou inferência retornam HTTP 503, sem expor detalhes internos. Não há fallback
silencioso para dados ou embeddings fictícios.

### Campos e preparação

Campos conferidos em `Investidor.ts` e `Startup.ts` do backend:

- Investidor: `bio`, seguida de `descricaoExperiencia`.
- Startup: `descricaoCurta`, `descricaoPitch`, `mercadoAlvo` e, nessa ordem,
  `canvasJson.problema`, `solucao`, `value`, `customers`.

`canvasJson` é um JSONB livre na entidade; suas chaves não constituem colunas
TypeORM nem são obrigatórias. A lista acima é uma seleção explícita do serviço:
problema, solução, proposta de valor e clientes. Outras chaves são ignoradas;
valores selecionados que não sejam strings também são ignorados. Não se inferem
textos de objetos, listas, nomes, URLs ou atributos financeiros.

A preparação normaliza Unicode NFC e espaços, ignora null/vazio e elimina campos
inteiros repetidos por comparação sem diferença de caixa. Preserva pontuação,
acentos e o texto original restante. Não remove stopwords, não faz stemming e
não elimina automaticamente trechos parcialmente sobrepostos.

Conteúdo suficiente significa, operacionalmente, pelo menos três palavras
alfabéticas no documento combinado. Esse limiar não comprova qualidade. Perfis
abaixo dele recebem similaridade e score null, com avisos. Se o investidor não
tiver conteúdo ou nenhuma startup tiver texto suficiente, o encoder não é chamado.

### Embeddings e cálculo

Módulos: `content_schemas.py` (contratos), `content_text.py` (preparação),
`embeddings.py` (modelo lazy e interface substituível) e `content.py` (ranking).

Cada requisição deduplica documentos idênticos e gera o embedding do investidor
uma única vez, reutilizando-o para todas as comparações. Não há cache persistente
de embeddings dos perfis. Documentos longos são divididos conforme o limite de
tokens do modelo, reservando tokens especiais; os vetores dos blocos são
normalizados, combinados por média ponderada pelo número de tokens e novamente
normalizados. Isso evita simplesmente descartar o final do documento, mas a média
pode diluir assuntos específicos e perde contexto entre blocos.

- `similaridadeBruta = produto escalar dos vetores normalizados`, em [-1, 1].
- `score = (similaridadeBruta + 1) / 2`, em [0, 1].

Vetores nulos ou não finitos recebem score null e aviso. Dimensões inconsistentes
ou quantidade incorreta de vetores são erros do encoder. Os scores numéricos são
limitados para compensar pequenos desvios de ponto flutuante. Um cosseno zero
vira score 0,5: **isso não representa 50% de chance de interesse**.

Ordenação: score decrescente, null ao final, depois UUID canônico crescente.
O limite é aplicado após a ordenação e as posições começam em 1. Não há limiar
automático de relevância. A resposta não contém justificativas semânticas: cosseno
isolado não demonstra quais conceitos ou palavras causaram a correspondência.

### Contrato e exemplo HTTP

IDs são `Investidor.id` e `Startup.id`, não `Usuario.id`. Campos extras são
rejeitados. Textos são opcionais/null; o objeto investidor e a lista startups são
obrigatórios. Limite: inteiro estrito de 1 a 1.000, padrão 10. Até 1.000 candidatas,
sem UUIDs duplicados. `descricaoCurta` aceita até 300 caracteres, `mercadoAlvo`
até 200 e demais campos textuais escalares até 20.000. Erros retornam 422.

Após iniciar `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, abra
`http://127.0.0.1:8000/docs`, escolha `POST /match/content` e use este exemplo
fictício como corpo (não é fonte operacional de dados):

```json
{
  "investidor": {
    "id": "11111111-1111-4111-8111-111111111111",
    "bio": "Tecnologia para agricultura familiar"
  },
  "startups": [{
    "id": "22222222-2222-4222-8222-222222222222",
    "descricaoPitch": "Soluções digitais para produtores rurais"
  }],
  "limite": 5
}
```

Formato da resposta; os números abaixo são ilustrativos, não resultado aferido
do modelo real:

```json
{
  "investidorId": "11111111-1111-4111-8111-111111111111",
  "versaoAlgoritmo": "1b-v1",
  "modeloEmbeddings": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "recomendacoes": [{
    "startupId": "22222222-2222-4222-8222-222222222222",
    "posicao": 1,
    "similaridadeBruta": 0.8,
    "score": 0.9,
    "avisos": []
  }],
  "avisos": []
}
```

### Testes

A suíte padrão usa apenas vetores e modelos simulados, sem instalar
sentence-transformers ou baixar pesos:

```sh
python -m pytest -q -p no:cacheprovider
```

O teste real só roda mediante pedido explícito, com dependências de conteúdo
instaladas e acesso ao cache/pesos:

```sh
python -m pytest tests/test_content_integration.py --run-real-embeddings -q
```

Ele verifica se um perfil agrícola supera um de jogos no exemplo definido.
É um smoke test de integração, não avaliação estatística de qualidade. Os testes
unitários verificam o comportamento com relações semânticas simuladas; não
comprovam desempenho do modelo em português ou no domínio de investimentos.

### Limitações e integração futura

Experiência passada e bio não definem necessariamente interesses futuros. A
similaridade pode priorizar vocabulário genérico, refletir vieses do modelo ou
aproximar perfis incompatíveis nas regras estruturadas. Não estima risco,
retorno ou probabilidade de investimento. A média de blocos dá mais influência
a campos longos; não há pesos específicos por campo nesta versão.

O backend ainda deverá fornecer a projeção textual autorizada, tratar timeouts
(especialmente na primeira carga), falhas 503 e validar IDs. O endpoint deve ser
protegido contra acesso público na integração, assim como `/match/rules`.
Configurar limites de bytes/taxa no gateway, provisionar cache e memória, avaliar
latência em CPU e fixar revisão dos pesos do modelo para reprodutibilidade são
pendências de implantação. Não há filtros de elegibilidade ou acesso ao banco
no serviço Python. Não houve integração ou alteração nos outros repositórios.

Referências oficiais: [API SentenceTransformer](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
e [modelo](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
