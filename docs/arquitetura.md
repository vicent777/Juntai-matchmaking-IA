# Arquitetura do Juntaí!

```mermaid
flowchart LR
    U["Pessoa usuária"] --> F["Frontend React e TypeScript"]
    F -->|"HTTPS / API"| B["Backend Node.js e Express"]
    B -->|"TypeORM / SQL"| DB[("PostgreSQL")]
    B -->|"HTTP / JSON e chave de serviço"| M["Motor Python e FastAPI"]
    M -->|"ranking e justificativas"| B
    F -->|"localidades"| IBGE["API do IBGE"]
    F -->|"fontes"| GF["Google Fonts"]
    B -->|"arquivos"| C["Cloudinary"]
    subgraph Azure["Ambiente beta Azure"]
      F
      B
      DB
      M
    end
```

Os perfis e as interações são persistidos pelo backend no PostgreSQL. Nas
recomendações, a API seleciona dados necessários e envia uma projeção ao motor;
a lista resultante retorna à interface pela API. No beta, o método configurado
é o de regras. O serviço semântico e o supervisionado são caminhos distintos;
o supervisionado é experimental e depende de artefatos e configuração.

Os dados cadastrais, mensagens e reuniões são transacionais; exposições e
interações são comportamentais. Consultas e recomendações acontecem sob demanda;
a conclusão de reuniões é verificada periodicamente pelo backend. O serviço
utiliza dados para apoiar conexões; a pontuação não é garantia de investimento.

