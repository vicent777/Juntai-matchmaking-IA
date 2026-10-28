# Avaliação exploratória real do Nível 1B

Modelo: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, CPU.
Os textos foram fixados antes da execução, sem ajuste posterior. As entradas
completas, UUIDs, scores não arredondados e medições estão em
`content_real_results.json`. O script é `tests/evaluate_content_real.py`.
Não foram alteradas regras, contratos ou os outros repositórios.

## Ambiente e método

Python 3.13.11; sentence-transformers 5.7.0; torch 2.15.0;
transformers 5.21.0; huggingface-hub 2.3.0. CPU Intel Family 6 Model 170,
14 processadores lógicos; PyTorch com 12 threads.

Quatro investidores; seis startups com texto (agricultura, saúde, educação,
finanças, jogos e energia), mais um perfil vazio. Referências humanas de top 1
definidas no script antes da execução. Não são rótulos externos independentes.
Os casos contêm variações como produtores familiares/lavradores,
trabalho docente/professores e doenças crônicas/diabetes e hipertensão.

Teste opcional inicial: 1 aprovado em 402,43 s (402,16 s na chamada do teste).
Esse tempo inclui download e inicialização; não é latência de recomendação.
Após a instalação, a suíte completa com `--run-real-embeddings` retornou
**77 testes aprovados em 27,52 s**, incluindo o Nível 1A e o teste real.
Carga separada em processo novo, com pesos em cache: **24,1582 s**. Inclui
imports de bibliotecas e resolução do modelo, que pode consultar o Hub; não é
uma medição isolada de leitura de disco nem um benchmark estritamente offline.
Um loader foi usado pelo encoder para todas as avaliações do processo.

Processamento inclui preparação, tokenização, embeddings, cosseno e ranking;
não inclui HTTP. Todos os embeddings são recalculados em cada requisição.
Três repetições após a primeira inferência, com ordem estável em todas elas:

| Investidor | Primeira inferência (ms) | Mediana de 3 repetições (ms) |
| --- | ---: | ---: |
| Agro | 162,54 | 198,42 |
| Saúde | 212,49 | 163,65 |
| Educação | 174,83 | 170,93 |
| Mudança de setor | 178,93 | 181,61 |

## Rankings reais

Score normalizado = (cosseno + 1) / 2. Valores arredondados a quatro casas.

| Investidor | Posição | Startup | Cosseno bruto | Score |
| --- | ---: | --- | ---: | ---: |
| Agro | 1 | CampoConecta | 0,6155 | 0,8077 |
| Agro | 2 | CaixaSimples | 0,3748 | 0,6874 |
| Agro | 3 | CuidadoPerto | 0,3112 | 0,6556 |
| Agro | 4 | SolLocal | 0,3052 | 0,6526 |
| Agro | 5 | OrbitaGames | 0,1828 | 0,5914 |
| Agro | 6 | AprenderJuntos | 0,0941 | 0,5470 |
| Saúde | 1 | CuidadoPerto | 0,6168 | 0,8084 |
| Saúde | 2 | CaixaSimples | 0,3529 | 0,6765 |
| Saúde | 3 | SolLocal | 0,3107 | 0,6553 |
| Saúde | 4 | CampoConecta | 0,2576 | 0,6288 |
| Saúde | 5 | OrbitaGames | 0,1810 | 0,5905 |
| Saúde | 6 | AprenderJuntos | 0,1040 | 0,5520 |
| Educação | 1 | AprenderJuntos | 0,5684 | 0,7842 |
| Educação | 2 | CampoConecta | 0,2693 | 0,6346 |
| Educação | 3 | CuidadoPerto | 0,2389 | 0,6195 |
| Educação | 4 | CaixaSimples | 0,2122 | 0,6061 |
| Educação | 5 | OrbitaGames | 0,1881 | 0,5940 |
| Educação | 6 | SolLocal | 0,0578 | 0,5289 |
| Mudança de setor | 1 | CaixaSimples | 0,5130 | 0,7565 |
| Mudança de setor | 2 | CuidadoPerto | 0,4470 | 0,7235 |
| Mudança de setor | 3 | CampoConecta | 0,3248 | 0,6624 |
| Mudança de setor | 4 | SolLocal | 0,3091 | 0,6546 |
| Mudança de setor | 5 | OrbitaGames | 0,2161 | 0,6080 |
| Mudança de setor | 6 | AprenderJuntos | 0,0688 | 0,5344 |

PerfilVazio ficou na posição 7 para todos, com similaridade e score null,
acompanhado do aviso de conteúdo insuficiente.

## Interpretação e limitações observadas

- Os três perfis com foco consistente colocaram o setor de referência no topo,
  apesar de diferenças de palavras. Isso é evidência exploratória favorável,
  sem demonstrar generalização ou isolar causalmente o efeito de cada termo.
- O perfil de mudança de setor declarou interesse atual em saúde, mas descreveu
  uma experiência financeira longa. Finanças superou saúde (0,7565 contra
  0,7235). O resultado contraria a referência previamente definida e é
  consistente com a limitação de misturar preferência atual e experiência
  passada em um único documento; esta execução não prova a causa isoladamente.
- Finanças ficou em segundo até para Agro e Saúde. Pode refletir linguagem
  genérica de negócios; não se deve interpretar isso como interesse financeiro
  real ou como explicação demonstrada pelo embedding.
- Mesmo jogos, pouco relacionados aos interesses, recebeu scores próximos de
  0,59–0,61. A normalização desloca cosseno zero para 0,5; percentuais não são
  probabilidades nem permitem definir limiares de relevância sem avaliação.
- As primeiras posições foram estáveis nas repetições, mas esta estabilidade
  não comprova qualidade nem reprodutibilidade entre hardwares e revisões.
- Amostra pequena, sintética, sem avaliações independentes ou teste de carga.
  Medianas de três medições não fornecem p95/p99. Não foram avaliados outros
  idiomas, documentos extensos, concorrência ou catálogo grande nesta rodada.
- A referência esperada apareceu em primeiro em 3 dos 4 perfis; essa contagem
  não deve ser apresentada como acurácia estimada em produção.

Conclusão: o mecanismo real funciona e reconhece proximidade temática nestes
casos, mas o tratamento de experiência versus intenção atual requer avaliação
adicional antes de usar o ranking como representação confiável de interesse.
Nenhum peso, exemplo ou contrato foi ajustado para melhorar o resultado.

## Reprodução

Na raiz do repositório, com dependências de conteúdo instaladas:

```powershell
py -X utf8 -m pytest tests/test_content_integration.py --run-real-embeddings -q --durations=3
py -X utf8 -c "import runpy; runpy.run_path('tests/evaluate_content_real.py', run_name='__main__')"
```

O segundo comando sobrescreve apenas o JSON de resultados desta avaliação.
Tempos e pequenos detalhes numéricos podem variar. Nenhuma revisão imutável do
modelo foi fixada pelo serviço; isso continua sendo uma limitação de reprodução.
