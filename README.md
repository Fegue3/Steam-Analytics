# Branch de dados

Esta branch órfã contém apenas os dados brutos e os logs gerados
automaticamente pelos GitHub Actions durante a recolha do projeto
Steam Analytics.

## Estrutura

```text
raw/
├── players/AAAA-MM-DD.jsonl
├── store/AAAA-MM-DD.jsonl
├── reviews/AAAA-MM-DD.jsonl
└── steamspy/AAAA-MM-DD.jsonl

logs/
├── players/AAAA-MM-DD.log
├── store/AAAA-MM-DD.log
└── daily/AAAA-MM-DD.log
```

Os ficheiros JSONL contêm uma linha JSON por execução de cada coletor.
O formato e o significado dos campos estão documentados em
`docs/recolha.md` na branch `main`.

Esta branch é gerida pelos GitHub Actions e não deve ser editada
manualmente.
