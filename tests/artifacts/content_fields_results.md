# Experimento real: influência dos campos textuais

A: somente bio. B: somente descricaoExperiencia. C: concatenação atual.
Textos originais importados de evaluate_content_real.py, sem alterações. Modelo em CPU e rank_content de produção. Cache experimental reutiliza vetores por texto exato; mesma preparação, normalização e desempate nas três estratégias.

Referências de relevância são as definidas previamente no experimento anterior, não avaliações independentes. Delta = cosseno da relevante menos cosseno da primeira (zero quando a relevante lidera). Scores não são probabilidades.

## Comparativo

| Estratégia | Referência em primeiro | Posição média da relevante |
| --- | ---: | ---: |
| A | 4/4 | 1.00 |
| B | 3/4 | 2.00 |
| C | 3/4 | 1.25 |

## Agro — estratégia A

Relevante: CampoConecta; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CampoConecta | 0.520061 | 0.760030 |
| 2 | CaixaSimples | 0.389715 | 0.694857 |
| 3 | SolLocal | 0.290429 | 0.645215 |
| 4 | CuidadoPerto | 0.266827 | 0.633413 |
| 5 | OrbitaGames | 0.219874 | 0.609937 |
| 6 | AprenderJuntos | 0.077849 | 0.538925 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Quero apoiar soluções que aproximem produtores familiares do consumidor e melhorem a comercialização no campo.
```

## Agro — estratégia B

Relevante: CampoConecta; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CampoConecta | 0.518767 | 0.759384 |
| 2 | CaixaSimples | 0.300934 | 0.650467 |
| 3 | SolLocal | 0.253209 | 0.626604 |
| 4 | CuidadoPerto | 0.234920 | 0.617460 |
| 5 | OrbitaGames | 0.168753 | 0.584377 |
| 6 | AprenderJuntos | 0.049895 | 0.524947 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Atuei na distribuição de produtos agrícolas e na organização de cooperativas.
```

## Agro — estratégia C

Relevante: CampoConecta; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CampoConecta | 0.615484 | 0.807742 |
| 2 | CaixaSimples | 0.374839 | 0.687419 |
| 3 | CuidadoPerto | 0.311175 | 0.655587 |
| 4 | SolLocal | 0.305205 | 0.652602 |
| 5 | OrbitaGames | 0.182835 | 0.591418 |
| 6 | AprenderJuntos | 0.094091 | 0.547046 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Quero apoiar soluções que aproximem produtores familiares do consumidor e melhorem a comercialização no campo.
Atuei na distribuição de produtos agrícolas e na organização de cooperativas.
```

## Saúde — estratégia A

Relevante: CuidadoPerto; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CuidadoPerto | 0.595862 | 0.797931 |
| 2 | CaixaSimples | 0.347321 | 0.673661 |
| 3 | SolLocal | 0.296981 | 0.648491 |
| 4 | CampoConecta | 0.264526 | 0.632263 |
| 5 | OrbitaGames | 0.194304 | 0.597152 |
| 6 | AprenderJuntos | 0.105284 | 0.552642 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Busco negócios que previnam complicações de doenças crônicas e ampliem o acesso ao atendimento, especialmente longe dos grandes centros.
```

## Saúde — estratégia B

Relevante: CuidadoPerto; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CuidadoPerto | 0.463646 | 0.731823 |
| 2 | CaixaSimples | 0.235141 | 0.617570 |
| 3 | SolLocal | 0.177490 | 0.588745 |
| 4 | CampoConecta | 0.135818 | 0.567909 |
| 5 | OrbitaGames | 0.069527 | 0.534764 |
| 6 | AprenderJuntos | 0.061368 | 0.530684 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Trabalhei com gestão de hospitais e serviços de telemedicina.
```

## Saúde — estratégia C

Relevante: CuidadoPerto; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CuidadoPerto | 0.616769 | 0.808384 |
| 2 | CaixaSimples | 0.352929 | 0.676465 |
| 3 | SolLocal | 0.310697 | 0.655348 |
| 4 | CampoConecta | 0.257567 | 0.628784 |
| 5 | OrbitaGames | 0.180952 | 0.590476 |
| 6 | AprenderJuntos | 0.104017 | 0.552008 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Busco negócios que previnam complicações de doenças crônicas e ampliem o acesso ao atendimento, especialmente longe dos grandes centros.
Trabalhei com gestão de hospitais e serviços de telemedicina.
```

## Educação — estratégia A

Relevante: AprenderJuntos; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | AprenderJuntos | 0.566362 | 0.783181 |
| 2 | CampoConecta | 0.263204 | 0.631602 |
| 3 | CuidadoPerto | 0.244543 | 0.622271 |
| 4 | CaixaSimples | 0.219277 | 0.609639 |
| 5 | OrbitaGames | 0.218744 | 0.609372 |
| 6 | SolLocal | 0.068812 | 0.534406 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Procuro ferramentas que ajudem crianças a aprender melhor, respeitando ritmos diferentes e apoiando o trabalho docente.
```

## Educação — estratégia B

Relevante: AprenderJuntos; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | AprenderJuntos | 0.526082 | 0.763041 |
| 2 | CuidadoPerto | 0.202113 | 0.601057 |
| 3 | CampoConecta | 0.193389 | 0.596695 |
| 4 | CaixaSimples | 0.146042 | 0.573021 |
| 5 | OrbitaGames | 0.098066 | 0.549033 |
| 6 | SolLocal | 0.007635 | 0.503817 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Tenho experiência em formação de educadores e avaliação pedagógica.
```

## Educação — estratégia C

Relevante: AprenderJuntos; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | AprenderJuntos | 0.568358 | 0.784179 |
| 2 | CampoConecta | 0.269291 | 0.634646 |
| 3 | CuidadoPerto | 0.238921 | 0.619461 |
| 4 | CaixaSimples | 0.212233 | 0.606117 |
| 5 | OrbitaGames | 0.188080 | 0.594040 |
| 6 | SolLocal | 0.057837 | 0.528919 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Procuro ferramentas que ajudem crianças a aprender melhor, respeitando ritmos diferentes e apoiando o trabalho docente.
Tenho experiência em formação de educadores e avaliação pedagógica.
```

## Mudança de setor — estratégia A

Relevante: CuidadoPerto; posição 1; delta 0.000000.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CuidadoPerto | 0.461929 | 0.730965 |
| 2 | CaixaSimples | 0.310169 | 0.655084 |
| 3 | SolLocal | 0.307630 | 0.653815 |
| 4 | CampoConecta | 0.178507 | 0.589253 |
| 5 | OrbitaGames | 0.110718 | 0.555359 |
| 6 | AprenderJuntos | 0.021302 | 0.510651 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Hoje quero investir em prevenção de doenças e cuidado de pacientes em casa.
```

## Mudança de setor — estratégia B

Relevante: CuidadoPerto; posição 5; delta -0.309622.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CaixaSimples | 0.490097 | 0.745049 |
| 2 | CampoConecta | 0.316120 | 0.658060 |
| 3 | OrbitaGames | 0.230095 | 0.615048 |
| 4 | SolLocal | 0.228962 | 0.614481 |
| 5 | CuidadoPerto | 0.180475 | 0.590238 |
| 6 | AprenderJuntos | 0.104525 | 0.552263 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Passei vinte anos em bancos, desenvolvendo crédito, pagamentos, conciliação financeira, antecipação de recebíveis e análise de risco para microempresas. Liderei produtos de capital de giro e serviços financeiros digitais para pequenos comerciantes.
```

## Mudança de setor — estratégia C

Relevante: CuidadoPerto; posição 2; delta -0.065941.

| Posição | Startup | Cosseno bruto | Score normalizado |
| ---: | --- | ---: | ---: |
| 1 | CaixaSimples | 0.512963 | 0.756482 |
| 2 | CuidadoPerto | 0.447022 | 0.723511 |
| 3 | CampoConecta | 0.324814 | 0.662407 |
| 4 | SolLocal | 0.309142 | 0.654571 |
| 5 | OrbitaGames | 0.216069 | 0.608034 |
| 6 | AprenderJuntos | 0.068789 | 0.534395 |
| 7 | PerfilVazio | null | null |

Texto efetivamente enviado ao encoder:

```text
Hoje quero investir em prevenção de doenças e cuidado de pacientes em casa.
Passei vinte anos em bancos, desenvolvendo crédito, pagamentos, conciliação financeira, antecipação de recebíveis e análise de risco para microempresas. Liderei produtos de capital de giro e serviços financeiros digitais para pequenos comerciantes.
```

## Execução

Documentos únicos codificados: 18. Modelo mantido em uma instância LocalEncoder. Tempo total com carga: 30.706 s; não é benchmark de latência da API devido ao cache experimental.

```powershell
py -X utf8 -c "import runpy; runpy.run_path('tests/evaluate_content_fields.py', run_name='__main__')"
```

As execuções sobrescrevem apenas os resultados deste experimento. O JSON registra textos, UUIDs, versões, hash da fonte e scores completos. A revisão remota do modelo não está fixada; ambiente e pequenas diferenças numéricas podem variar.
