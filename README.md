# Software-de-Or-amento

Implementação da aba **Planejamento** com persistência SQLite, API REST e frontend ERP-like.

## Como rodar

```bash
python app.py
```

Acesse `http://localhost:3000`.

## Autenticação mock (para testes)

O frontend possui seletor de **Usuário ativo** na sidebar e envia `X-User-Id` em todas as requisições.

Seeds de usuários:
- Ana Diretoria (`diretoria@coop.local`) — acesso global
- Bruno Gestor (`gestor@coop.local`) — 2 centros de custo
- Carla Operadora (`operador@coop.local`) — 1 centro de custo

## Navegação

- `/planejamentos` — lista, criação e cópia de planejamento
- `/planejamentos/:id` — detalhe com modelos
- `/planejamentos/:id/modelos/:modeloId/editar` — editor de estrutura do modelo
- `/planejamentos/:id/modelos/:modeloId/preencher` — preenchimento mensal
- `/parametros (painel focado em Usuários via modal único)` — módulo Parâmetros (RBAC)

## Controle de Acesso (RBAC + escopo por CC)

### Tabelas
- `roles` (`OPERADOR|GESTOR|DIRETORIA`)
- `permissions` (ex.: `planning.read`, `planning.fill.write`)
- `role_permissions`
- `user_roles`
- `user_cost_centers` (`linkType`: `GESTOR_CC|OPERADOR_CC|LEITOR_CC`)
- `workflow_cc_status` (status por Planejamento x Centro de Custo)
- `audit_log` (trilha de auditoria)

### Regras
- Deny-by-default no backend (sem permissão explícita = 403)
- Rotas de Planejamento exigem permissões `planning.*`
- Rotas de Parâmetros exigem `parametros.*`
- Rotas com `centroCustoId` validam vínculo do usuário (`user_cost_centers`)
- Workflow por CC: `ABERTO -> EM_REVISAO -> APROVADO -> BLOQUEADO` com transições por perfil
- Edição de preenchimento bloqueada quando status != `ABERTO` (exceto usuários autorizados)
- Usuário com role `DIRETORIA` tem acesso global de CC

## Endpoints principais

### Sessão mock
- `GET /api/session/users`
- `GET /api/session/me`

### Planejamento
- `GET /api/planejamentos?page&pageSize`
- `POST /api/planejamentos`
- `GET /api/planejamentos/:id`
- `POST /api/planejamentos/:id/copy`
- `GET /api/planejamentos/:id/modelos?page&pageSize`
- `POST /api/planejamentos/:id/modelos`
- `PUT /api/modelos/:modeloId`
- `DELETE /api/modelos/:modeloId`
- `GET /api/modelos/:modeloId/linhas?page&pageSize`
- `POST /api/modelos/:modeloId/linhas`
- `PUT /api/linhas/:id`
- `POST /api/modelos/:modeloId/linhas/reorder`
- `DELETE /api/linhas/:id`
- `GET /api/my-cost-centers`
- `GET /api/modelos/:modeloId/valores?centroCustoId=...&ano=YYYY`
- `POST /api/modelos/:modeloId/valores/upsert`

### Parâmetros
- `GET/POST /api/parametros/usuarios`
- `PUT/DELETE /api/parametros/usuarios/:id` (`DELETE` = inativação lógica)
- `GET/POST /api/centros-custo`
- `PUT/DELETE /api/centros-custo/:id`
- `GET /api/parametros/roles`
- `GET /api/parametros/permissions`
- `GET/POST/DELETE /api/parametros/user-roles`
- `GET/POST/DELETE /api/parametros/role-permissions`
- `GET/POST/DELETE /api/parametros/user-cost-centers`

## Teste manual solicitado

1. Logar como **gestor** (Bruno Gestor) e abrir preenchimento:
   - deve listar apenas "Meus CCs" (2 CCs) e permitir alternar.
2. Logar como **operador** (Carla Operadora):
   - deve listar somente 1 CC.
3. Logar como **diretoria** (Ana Diretoria):
   - deve listar todos os 6 CCs.
4. Tentar acessar CC não vinculado:
   - backend deve responder `403`.

- `GET /api/parametros/usuarios/:id/cost-centers`
- `POST /api/parametros/usuarios/:id/cost-centers`
- `GET /api/planejamentos/:id/workflow?centroCustoId=...`
- `POST /api/planejamentos/:id/workflow/transition`
- `GET /api/audit-log?page&pageSize`

## Cenários manuais de validação (Governança + Workflow + Auditoria)

1. Gestor (Bruno) abre preenchimento e vê apenas seus CCs; muda CC ativo e dados recarregam.
2. Operador (Carla) visualiza somente 1 CC no seletor de CC ativo.
3. Diretoria (Ana) visualiza todos os CCs e consegue avançar `APROVADO -> BLOQUEADO`.
4. Gestor envia `ABERTO -> EM_REVISAO`; ao tentar editar lançamentos após isso, backend retorna `403`.
5. Usuário com CC não vinculado tenta acessar `/api/modelos/:id/valores?centroCustoId=...` e recebe `403`.
6. Criar/editar/inativar usuário, alterar vínculos CC e editar lançamentos/modelos/linhas; validar registros em `/api/audit-log`.


## Usuários (modal único)
- Todas as operações de usuário acontecem em **Parâmetros > Usuários** via modal `Gerenciar`/`Novo usuário`.
- Não existe exclusão física no fluxo de UI; a inativação é irreversível via `POST /api/users/:id/inactivate`.

### Endpoints MVP de Usuários
- `GET /api/users?query=&page=&pageSize=`
- `POST /api/users`
- `PUT /api/users/:id` (nome/cargo/CCs; email não altera no modal)
- `POST /api/users/:id/inactivate`
- `GET /api/cost-centers`
