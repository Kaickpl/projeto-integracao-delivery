# Serviço de Autorização e RBAC

O papel de cada conta é a associação autoritativa usada pelo Auth ao emitir ou renovar tokens. As tabelas e o histórico Alembic ficam no schema `autorizacao`, separado dos dados de Perfis e do schema reservado `auth` do Supabase.

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

Em um banco de testes isolado, `upgrade head` cria `autorizacao.papeis_conta`, `autorizacao.permissoes_clientes_servico` e `autorizacao.alembic_version`. A migração inicial impede valores de papel fora de `CLIENTE`, `LOJA`, `ENTREGADOR` e `ADMIN`, além da validação feita pela API.

## Rotas internas

- `GET /v1/interno/contas/{conta_id}/papel`: consulta autenticada pelo token de serviço do Auth.
- `PUT /v1/interno/contas/{conta_id}/papel`: associação/atualização autenticada pelo token de serviço de Perfis.
- `POST /v1/tokens/validar`: valida o access token recebido em `Authorization: Bearer` por introspecção online no Auth e confere se o papel continua igual ao vínculo atual no RBAC. Tokens inválidos, expirados, revogados ou com papel desatualizado retornam `401` no formato `{"erro": true, "mensagem": "..."}`. Indisponibilidade do Auth ou do PostgreSQL retorna `503`.
- `GET /v1/interno/clientes/{client_id}/permissoes?audiencia=...`: consulta autenticada pelo token de serviço do Auth; devolve somente os escopos concedidos ao consumidor e recurso.
- Para o worker de Notificações do Financeiro, conceder no ambiente local `http://perfis:8002` + `perfis:ler`. Auth consulta essa política ao emitir; Perfis valida o token por JWKS localmente. A audiência publicada deve ser ajustada quando a URL real de Perfis for definida.
- `POST /v1/tokens/servico/validar`: valida assinatura/claims por JWKS e compara escopos requeridos com o token e a política atual. É a opção para operações que exigem decisão online do RBAC; o Financeiro aceitou validação local por JWKS para seu fluxo M2M de leitura de perfil, sem chamada ao RBAC por requisição e com janela de até 10 minutos para efeito de revogação/remoção de escopo. Token inválido retorna `401`; escopo não permitido retorna `403`; indisponibilidade de JWKS/PostgreSQL retorna `503`.
- `python -m src.gerenciar_permissoes_servico conceder <client_id> <audiencia> <escopo...>` e `remover ...`: altera a política por operação administrativa local. Não há endpoint público para conceder permissões.
- `GET /health`: verificação simples de disponibilidade.

O endpoint de validação falha fechado: o Auth precisa confirmar a sessão no PostgreSQL compartilhado antes de o RBAC aceitar o token. A credencial de serviço do RBAC para chamar Auth deve corresponder a `AUTORIZACAO_SERVICE_TOKEN` no Auth.

## Testes

As verificações ponta a ponta estão em `autenticacao/tests/test_integracao_servicos.py`. Execute-as apenas contra a pilha de integração e banco local isolado descritos em `docs/INTEGRACAO_LOCAL.md`; nunca use o Supabase compartilhado para esses testes.
