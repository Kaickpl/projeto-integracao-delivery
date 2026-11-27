# Serviço de Autorização e RBAC

O papel de cada conta é a associação autoritativa usada pelo Auth ao emitir ou renovar tokens. O RBAC também define o que cada papel pode fazer (permissões) e responde às decisões de autorização dos outros serviços. As tabelas e o histórico Alembic ficam no schema `autorizacao`, separado dos dados de Perfis e do schema reservado `auth` do Supabase.

## Configuração

Copie `.env.example` para `.env` e configure `DATABASE_URL` com o PostgreSQL de desenvolvimento. Os tokens de serviço devem ser iguais aos configurados nos serviços que fazem as chamadas correspondentes. Não use segredos reais em arquivos versionados, issues ou logs.

## Migrações

Execute a migração uma vez, como etapa de implantação, antes de subir ou escalar as instâncias da API. A aplicação não cria tabelas ao iniciar.

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m alembic current
```

Para inspecionar o SQL sem conectar:

```powershell
python -m alembic upgrade head --sql
```

Em um banco de testes isolado, `upgrade head` cria no schema `autorizacao`:

| Tabela | Conteúdo |
|---|---|
| `papeis_conta` | Papel de cada conta (`CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`), gravado por Perfis no cadastro. |
| `permissoes_clientes_servico` | Escopos M2M por `client_id` e audiência. |
| `permissoes` | Catálogo fixo de permissões de usuário, semeado pela migração. |
| `papeis_permissoes` | Permissões de cada papel. O ADMIN pode conceder e remover pela API. |
| `auditoria_rbac` | Histórico de concessões, remoções e associações de papel. |
| `alembic_version` | Versão das migrações. |

## Papéis e permissões

Os quatro papéis são fixos: eles acompanham o tipo do perfil e fazem parte do contrato do token (claim `role`). O que pode mudar são as permissões de cada papel. Permissões seguem o formato `recurso:acao`. As terminadas em `_proprio` só valem quando o recurso é da própria conta; quem confere a posse é o serviço dono do recurso.

Permissões iniciais:

| Permissão | Papéis | Uso em Perfis |
|---|---|---|
| `perfis:listar` | ADMIN | `GET /admin/perfis`, `GET /admin/perfis/{id}` e `GET /lojas/{id}/perfil` de qualquer loja |
| `perfis:editar_qualquer` | ADMIN | `PATCH /admin/perfis/{id}` e edição de qualquer loja ou entregador |
| `perfis:alterar_status` | ADMIN | `PATCH /admin/perfis/{id}/status` |
| `perfis:remover_qualquer` | ADMIN | `DELETE /admin/perfis/{id}` e remoção de qualquer loja ou entregador |
| `admins:criar` | ADMIN | `POST /admin/admins` |
| `entregadores:listar` | ADMIN | `GET /entregadores`, `GET /entregadores/status/{status}`, `GET /entregadores/{id}` |
| `rbac:gerenciar` | ADMIN | Rotas de gestão deste serviço |
| `perfil:ler_proprio` | CLIENTE, LOJA, ENTREGADOR | `GET /clientes/{id}`, `GET /lojas/{id}/perfil` e `GET /entregadores/{id}` da própria conta |
| `perfil:editar_proprio` | CLIENTE, LOJA, ENTREGADOR | `PATCH /clientes/{id}` (nome, telefone e endereço), edição de loja e `PATCH /entregadores/{id}` |
| `perfil:remover_proprio` | CLIENTE, LOJA, ENTREGADOR | `DELETE /clientes/{id}`, `DELETE /lojas/{id}` e `DELETE /entregadores/{id}` |
| `loja:operar` | LOJA | `PATCH /lojas/{id}/status` (abrir/fechar) |
| `entregador:operar` | ENTREGADOR | `PATCH /entregadores/{id}/status` |

Não há cache de permissões: uma permissão removida vale na próxima requisição, sem esperar o token expirar. `rbac:gerenciar` não pode ser removida do papel ADMIN.

## Rotas para usuários e serviços

- `POST /v1/tokens/validar`: valida o access token recebido em `Authorization: Bearer` por introspecção online no Auth, confere se o papel continua igual ao vínculo atual no RBAC e devolve `conta_id`, `role`, `jti` e `permissoes`. Tokens inválidos, expirados, revogados ou com papel desatualizado retornam `401` no formato `{"erro": true, "mensagem": "..."}`. Indisponibilidade do Auth ou do PostgreSQL retorna `503`.
- `POST /v1/autorizacao/verificar`: mesmo token Bearer e corpo `{"permissao": "recurso:acao"}`. Responde `200` com `permitido: true`, `401` para token inválido, `403` quando o papel não tem a permissão e `503` em indisponibilidade. Serve aos serviços que só precisam da decisão.
- `POST /v1/tokens/servico/validar`: valida assinatura/claims de token M2M por JWKS e compara escopos requeridos com o token e a política atual. É a opção para operações que exigem decisão online do RBAC; o Financeiro aceitou validação local por JWKS para seu fluxo M2M de leitura de perfil, sem chamada ao RBAC por requisição e com janela de até 10 minutos para efeito de revogação/remoção de escopo. Token inválido retorna `401`; escopo não permitido retorna `403`; indisponibilidade de JWKS/PostgreSQL retorna `503`.

O endpoint de validação falha fechado: o Auth precisa confirmar a sessão no PostgreSQL compartilhado antes de o RBAC aceitar o token. A credencial de serviço do RBAC para chamar Auth deve corresponder a `AUTORIZACAO_SERVICE_TOKEN` no Auth.

## Rotas de gestão

Todas exigem token de usuário cujo papel tenha `rbac:gerenciar` (no Swagger, use o botão Authorize com o access token de um ADMIN).

- `GET /v1/permissoes`: catálogo de permissões.
- `GET /v1/papeis` e `GET /v1/papeis/{papel}/permissoes`: permissões de cada papel.
- `PUT /v1/papeis/{papel}/permissoes/{permissao}`: concede (idempotente). Permissão fora do catálogo retorna `404`.
- `DELETE /v1/papeis/{papel}/permissoes/{permissao}`: remove (idempotente). Tirar `rbac:gerenciar` do ADMIN retorna `409`.
- `GET /v1/contas/{conta_id}/papel`: papel de uma conta.
- `GET /v1/auditoria`: histórico paginado, mais recente primeiro, com filtros `papel`, `permissao` e `conta_id`.

## Rotas internas

- `GET /v1/interno/contas/{conta_id}/papel`: consulta autenticada pelo token de serviço do Auth.
- `PUT /v1/interno/contas/{conta_id}/papel`: associação/atualização autenticada pelo token de serviço de Perfis.
- `DELETE /v1/interno/contas/{conta_id}/papel`: remoção idempotente, autenticada pelo token de serviço de Perfis. Perfis chama antes de apagar um perfil; a partir daí os tokens da conta deixam de ser aceitos.
- `GET /v1/interno/clientes/{client_id}/permissoes?audiencia=...`: consulta autenticada pelo token de serviço do Auth; devolve somente os escopos concedidos ao consumidor e recurso.
- Para o worker de Notificações do Financeiro, conceder no ambiente local `http://perfis:8002` + `perfis:ler`. Auth consulta essa política ao emitir; Perfis valida o token por JWKS localmente. A audiência publicada deve ser ajustada quando a URL real de Perfis for definida.
- `python -m src.gerenciar_permissoes_servico conceder <client_id> <audiencia> <escopo...>` e `remover ...`: altera a política M2M por operação administrativa local. Não há endpoint público para conceder permissões M2M.
- `GET /health`: verificação simples de disponibilidade.

## Auditoria

Toda concessão ou remoção de permissão e toda associação ou remoção de papel gera um registro com quem fez (`conta_id` do ADMIN ou `servico:perfis`), quando, a ação e o alvo. Repetições idempotentes não geram registros novos. Tokens e dados pessoais não são gravados.

## Testes

As verificações ponta a ponta estão em `autenticacao/tests/test_integracao_servicos.py`. Execute-as apenas contra a pilha de integração e banco local isolado descritos em `docs/INTEGRACAO_LOCAL.md`; nunca use o Supabase compartilhado para esses testes.
