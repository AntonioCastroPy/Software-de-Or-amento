# Software-de-Or-amento

Implementação MVP da aba **Planejamento** com persistência em SQLite, API REST e frontend ERP-like em páginas limpas com tabelas, ações e modais.

## Como rodar

```bash
python app.py
```

Acesse `http://localhost:3000`.

## Navegação

- `/planejamentos` — lista, criação e cópia de planejamento
- `/planejamentos/:id` — detalhe com modelos
- `/planejamentos/:id/modelos/:modeloId/editar` — editor de estrutura do modelo
- `/planejamentos/:id/modelos/:modeloId/preencher` — preenchimento mensal
- `/parametros` — placeholder sem CRUD

## Entidades e regras implementadas

- Planejamento (`draft|aberto|fechado`)
- Modelo por planejamento
- Linhas do modelo (`input|formula|header`) com fórmula simples por código (`L001` etc.)
- Valores mensais por linha, mês e centro de custo
- Seeds fixas:
  - 3 centros de custo (Administração, Armazém, Comercial)
  - 10 contas contábeis mock

### Fórmulas (MVP)

- Operadores: `+ - * /`
- Parênteses
- Alias `SOMA(a,b,c)` e `SOMAR(a,b,c)`
- Referência por **código da linha** (`L001`)
- Validações:
  - auto-referência bloqueada
  - referência inválida bloqueada
  - ciclo entre fórmulas bloqueado

## Endpoints REST

### Planejamentos

- `GET /api/planejamentos?page&pageSize`
- `POST /api/planejamentos`
- `GET /api/planejamentos/:id`
- `POST /api/planejamentos/:id/copy` (copia modelos + linhas, sem valores)

### Modelos

- `GET /api/planejamentos/:id/modelos?page&pageSize`
- `POST /api/planejamentos/:id/modelos`
- `PUT /api/modelos/:modeloId`
- `DELETE /api/modelos/:modeloId`

### Linhas de modelo

- `GET /api/modelos/:modeloId/linhas?page&pageSize`
- `POST /api/modelos/:modeloId/linhas`
- `PUT /api/linhas/:id`
- `POST /api/modelos/:modeloId/linhas/reorder`
- `DELETE /api/linhas/:id`

### Valores mensais

- `GET /api/modelos/:modeloId/valores?centroCustoId=...&ano=YYYY`
- `POST /api/modelos/:modeloId/valores/upsert` (requer `ano`; salva inputs manuais, recalcula fórmulas em ordem topológica e persiste calculados)

### Mocks de parâmetros

- `GET /api/centros-custo`
- `GET /api/contas-contabeis`

## Passo a passo de teste manual

1. Criar planejamento em `/planejamentos` via **Novo Planejamento**.
2. Entrar no planejamento e criar modelo em **Novo Modelo**.
3. Abrir **Editar Estrutura**:
   - criar `L001` (input), `L002` (input), `L003` (formula `L001 + L002`)
   - mover linhas para validar reorder
4. Abrir **Preencher**:
   - informar Jan/Fev nas linhas input
   - conferir cálculo automático na linha fórmula
   - clicar com botão direito em célula input e usar **Replicar para os meses à frente** até Dez
5. Voltar à lista e usar **Copiar de...** para gerar novo planejamento
   - conferir que modelos/linhas foram copiados
   - conferir que não há valores mensais copiados
6. Trocar Centro de Custo no preenchimento e validar contexto de valores por CC.
