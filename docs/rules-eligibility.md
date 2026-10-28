# Nível 1A v3 — elegibilidade separada da afinidade

## Contrato aditivo

`POST /match/rules` continua aceitando todos os payloads anteriores. Nenhum campo
foi removido. Novos campos opcionais, sem defaults operacionais:

| Campo | Origem real | Ausente/null |
| --- | --- | --- |
| `investidor.usuario.id` | Relação Investidor.usuario → Usuario.id | Distinção de IDs não verificável |
| `investidor.usuario.ativo` | Usuario.ativo | Atividade não verificável |
| `investidor.tipoInvestidor` | Investidor.tipoInvestidor | Cálculo de ajuda legado preservado |
| `startups[].usuario.id` | Relação Startup.usuario → Usuario.id | Distinção de IDs não verificável |
| `startups[].usuario.ativo` | Usuario.ativo | Atividade não verificável |
| `startups[].statusModeracao` | Startup.statusModeracao | Aprovação não verificável |

Os objetos `usuario` são projeções mínimas, não entidades completas. `ativo`
aceita somente booleano JSON, não strings ou números. UUIDs inválidos, enums
inválidos e campos extras continuam retornando 422. O envio de `usuarioId` na
raiz do perfil continua inválido; o ID do usuário pertence ao objeto `usuario`.

Enums reais de modalidade: `anjo`, `mentor`, `anjo_mentor`. Moderação:
`pendente`, `aprovado`, `rejeitado`, `suspenso`. Nenhum default de aprovação,
atividade ou modalidade é aplicado pelo Python.

Resposta preserva todos os campos anteriores e acrescenta:

- `recomendacoes[].elegibilidade`: estado, verificadas, impedimentos, pendencias.
- `excluidas[]`: startupId e elegibilidade, para impedimentos explícitos.
- `tipoInvestidor`: modalidade recebida, ou null; somente contexto.

Extensão aditiva não exige alterar requisições legadas. Consumidores que validem
respostas rejeitando qualquer chave nova precisarão atualizar seus schemas.
`versaoAlgoritmo` passa de `1a-v2` para `1a-v3`.

## Regras operacionais

`evaluate_eligibility`, em `app/eligibility.py`, é executada antes dos critérios.
Ela verifica somente as condições aprovadas nesta incrementação:

1. Formato UUID dos IDs de perfil, já validado pelo Pydantic.
2. Investidor.id distinto do respectivo Usuario.id, quando informado.
3. Startup.id distinto do respectivo Usuario.id, quando informado.
4. Usuários de ambos os perfis explicitamente ativos.
5. Startup explicitamente aprovada.

- `elegivel`: todas essas condições foram recebidas e verificadas.
- `inelegivel`: existe usuário explicitamente inativo, ID de perfil igual ao
  respectivo ID de usuário ou moderação diferente de aprovado, incluindo pendente.
- `indeterminado`: nenhuma condição bloqueadora conhecida, mas faltam dados.

Impedimentos conhecidos prevalecem sobre ausências, que continuam descritas nas
pendências. Somente inelegíveis são retiradas das recomendações e incluídas em
`excluidas`. O limite é aplicado após a exclusão e a ordenação; posições são
sequenciais. Excluídas são ordenadas por UUID e não são cortadas pelo limite.
Não recebem scores, pois a compatibilidade não é calculada para elas.

Indeterminadas continuam no ranking com os mesmos scores; o estado fica no
campo próprio, sem acrescentar avisos que alterem as listas legadas.
Não há bônus por elegibilidade nem desempate adicional por estado operacional.

`elegivel` significa apenas aprovação nas condições recebidas, não autorização
global. O serviço não verifica existência de IDs, integridade da relação,
autenticidade ou atualidade dos valores. Backend autentica, autoriza, consulta o
PostgreSQL e seleciona candidatos. A IA não acessa o banco. Moderação do investidor,
consentimentos e outras regras não foram acrescentados à lista de condições
obrigatórias desta etapa; continuam sob responsabilidade da política do backend.

## Modalidade, cobertura e critérios

Os cinco critérios e pesos permanecem 30/25/20/15/10. Segmentos principal e
secundários mantêm equivalência de peso. Região continua usando atuação, nunca
expansão. Ajuda conserva apenas as três equivalências de HELP_MAP; desconhecidas
não viram incompatibilidade, e sua cobertura parcial permanece preservada.

Quando `tipoInvestidor=anjo`, ajuda fica insuficiente: score null, cobertura zero
e aviso. Mesmo `areasAjuda` preenchida não comprova oferta ativa de apoio nessa
modalidade. Não exclui a startup nem cria pontuação de modalidade. Para mentor
ou anjo_mentor, áreas declaradas são comparadas normalmente, sem exigir ticket.
Sem modalidade, mantém-se a interpretação legada para não mudar scores antigos.
Isso é uma limitação de compatibilidade retroativa, não confirmação de oferta de
mentoria. O backend deverá enviar modalidade para aplicar a nova distinção.

Afinidade mantém a média ponderada apenas dos critérios avaliáveis; cobertura
mantém a fração ponderada de avaliação. A fórmula de ranking permanece:

`scoreRanking = score * (0.5 + 0.5 * cobertura)`.

Para anjo, retirar ajuda da avaliação pode alterar afinidade e cobertura, mas
nenhum peso configurado muda. Exemplo com outros quatro critérios compatíveis:
score=1, cobertura=0,9 e scoreRanking=0,95. Modalidade não é um sexto critério.
Nenhum score é probabilidade de interesse, aporte ou investimento.

## Finanças e texto

Não foram adicionados tickets, capital, bio ou experiência ao contrato de regras.
A ausência de dados financeiros não exclui candidatos nem altera os scores.
Não há como concluir incompatibilidade financeira: ticket habitual não equivale
à captação total. Faltam aporte individual aceito e condições de coinvestimento.
`necessidadesAdicionais` não prova desejo exclusivo de mentoria; `buscaInvestimento`
não é usado para presumir que toda conexão exige aporte.

Bio, setores históricos e experiência não alimentam nenhum critério estruturado;
se enviados fora do contrato, são rejeitados. Nível 1B e seus contratos não foram
alterados. Nenhuma combinação híbrida foi implementada.

## Exemplos

Entrada mínima com os novos dados operacionais e modalidade:

```json
{
  "investidor": {
    "id": "11111111-1111-4111-8111-111111111111",
    "usuario": {"id": "33333333-3333-4333-8333-333333333333", "ativo": true},
    "tipoInvestidor": "mentor",
    "areasAjuda": ["mentoria"]
  },
  "startups": [{
    "id": "22222222-2222-4222-8222-222222222222",
    "usuario": {"id": "44444444-4444-4444-8444-444444444444", "ativo": true},
    "statusModeracao": "aprovado",
    "necessidadesAdicionais": ["mentoria"]
  }]
}
```

Recorte da resposta: `elegibilidade.estado=elegivel`, `score=1`,
`cobertura=0.1`, `scoreRanking=0.55`, uma justificativa de ajuda e `excluidas=[]`.
Os quatro critérios sem informação permanecem insuficientes. Aprovação não
implica afinidade completa nem cobertura completa.

Se omitir ambos os objetos usuario e statusModeracao, o recorte passa a
`elegibilidade.estado=indeterminado`, preservando os mesmos scores e a candidata.
Se enviar statusModeracao=rejeitado, `recomendacoes=[]` e a candidata aparece em
`excluidas` com estado inelegivel e motivo de moderação. Nenhum score é inventado.

## Validação

```powershell
py -X utf8 -m pytest -q -p no:cacheprovider
```

Resultado desta incrementação: **102 aprovados e 1 ignorado em 1,06 s**.
O ignorado é o teste opcional de embeddings reais. Nenhuma instalação foi feita.
Os testes anteriores de regras permaneceram intactos e passaram; os novos cobrem
modalidades, moderação, atividade, colisão de IDs, ausência operacional, HTTP,
validação estrita, limite após exclusão e preservação de scores/ranking legados.

Pendências: backend enviar as projeções, proteger o endpoint e validar as relações
com usuários; produto definir modalidades bilaterais e futuros dados financeiros.
`preferences`, `offers` e `openInvestment` permanecem sem alterações.
