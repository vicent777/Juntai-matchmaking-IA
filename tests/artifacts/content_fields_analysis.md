# Análise exploratória do experimento de campos

## Execução e controles

Comando executado na raiz:

```powershell
py -X utf8 -c "import runpy; runpy.run_path('tests/evaluate_content_fields.py',run_name='__main__')"
```

Execução real concluída com código 0, em CPU, usando o modelo previamente instalado.
Nenhuma dependência nova. Quatro investidores × três estratégias × sete startups:
84 posições, incluindo os controles vazios. Um LocalEncoder e cache por texto
exato codificaram 18 documentos únicos: seis startups e doze representações de
investidor. Tempo total com carga: 30,706 s, não comparável à latência de produção
por utilizar cache experimental. Não é uma nova execução da suíte de 77 testes;
é uma execução adicional do experimento real.

Textos foram importados do script anterior sem alterações; JSON registra hash
da fonte, versões, UUIDs, textos preparados e scores. A estratégia C foi comparada
ao content_real_results.json: diferença máxima de cosseno igual a zero em todos
os quatro investidores. As três estratégias usam a função de ranking de produção.

## Comparação por referência previamente definida

| Estratégia | Agro | Saúde | Educação | Mudança de setor | Top 1 | Posição média |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A: bio | 1 | 1 | 1 | 1 | 4/4 | 1,00 |
| B: experiência | 1 | 1 | 1 | 5 | 3/4 | 2,00 |
| C: ambos | 1 | 1 | 1 | 2 | 3/4 | 1,25 |

As posições são da startup considerada relevante no experimento anterior. Não
há métrica de acurácia em produção nem julgamento independente de todas as posições.
Os rankings completos, cossenos, scores e deltas estão em content_fields_results.md
e content_fields_results.json. O perfil vazio fica em sétimo, com scores null,
nas doze combinações.

## Verificação da interpretação das bios

Todas as quatro bios sintéticas contêm declaração prospectiva: "Quero apoiar",
"Busco negócios", "Procuro ferramentas" e "Hoje quero investir". Portanto, a
interpretação de intenção atual é sustentada pelos textos desta amostra. A última
é particularmente explícita sobre mudança de foco. Isso não garante que bios
reais sejam declarações de tese: podem ser biografias genéricas ou desatualizadas.

## Investidor com mudança de finanças para saúde

| Estratégia | Posição de CuidadoPerto | Cosseno saúde | Score saúde | Posição de CaixaSimples | Cosseno finanças | Score finanças | Delta relevante menos líder |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 1 | 0,461929 | 0,730965 | 2 | 0,310169 | 0,655084 | 0 |
| B | 5 | 0,180475 | 0,590238 | 1 | 0,490097 | 0,745049 | -0,309622 |
| C | 2 | 0,447022 | 0,723511 | 1 | 0,512963 | 0,756482 | -0,065941 |

Removendo experiência, saúde supera finanças por 0,151761 de cosseno. Com ambos,
saúde perde por 0,065941. O contraste controlado mostra influência prejudicial
da inclusão do histórico para representar a intenção atual deste perfil.
Não permite atribuir o efeito exclusivamente ao comprimento: conteúdo e extensão
do campo removido mudam juntos. O teste não estabelece pesos ideais.

## Avaliação das seis questões

1. A apresentou a melhor posição da relevante nesta amostra (4/4 no topo), mas
   sua vantagem de posição concentra-se no único perfil com conflito. Nos outros
   três há empate entre estratégias no primeiro lugar. Não há base para declarar
   superioridade geral de A.
2. A experiência prejudicou o alinhamento com a intenção atual no caso de mudança
   de setor. Nos demais ela é compatível com o interesse declarado e não prejudicou
   o primeiro lugar. História profissional não é uma preferência futura universal.
3. Bio isolada foi suficiente para colocar as quatro referências no topo, e todos
   os textos passaram o mínimo operacional de três palavras. Isso não valida
   suficiência em bios vagas, vazias, ambíguas ou reais.
4. C elevou o cosseno da referência em Agro (A: 0,520061; C: 0,615484), Saúde
   (0,595862 → 0,616769) e Educação (0,566362 → 0,568358), sem mudar o primeiro
   lugar. Elevar cosseno não é, por si só, melhorar ranking. No conflito C é pior
   que A e melhor que B em posição da relevante.
5. É justificável testar influência distinta por campo: representar intenção e
   experiência separadamente, combinando similaridades com pesos explícitos,
   evita que a extensão de um campo determine implicitamente sua influência.
   Não há evidência para escolher um peso numérico definitivo nesta amostra.
6. Reduzir ou excluir experiência pode perder expertise, contexto setorial,
   diferenciação entre perfis e sinal útil quando a bio é fraca ou ausente.
   Um fallback deve ser distinguido de intenção explicitamente declarada,
   evitando apresentar histórico como tese atual.

## Recomendação técnica

Manter produção inalterada por enquanto. Na próxima avaliação autorizada,
comparar representações separadas por campo e pesos pré-definidos em um conjunto
maior, com interesse atual explicitamente anotado por avaliadores independentes.
Incluir perfis alinhados, conflitantes e bios insuficientes. Comparar ranking,
recuperação e estabilidade, sem otimizar pesos nos mesmos quatro exemplos.
Priorizar intenção explícita é uma hipótese fundamentada para investigar, não
uma regra universal de que toda bio tem maior valor que experiência.

A amostra contém apenas uma referência por investidor e candidatas de setores
bem distintos. Não avalia relevância fina dentro de um setor, negação, qualidade
econômica, dados reais, generalização ou desempenho em produção. Scores são
similaridade normalizada, nunca probabilidades de interesse.
