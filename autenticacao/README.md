# Serviço de Autenticação

O Auth mantém credenciais, códigos de autorização e sessões de refresh no schema PostgreSQL `autenticacao`. A senha é guardada somente como hash Argon2id. O serviço consulta o status em Perfis e a associação de papel em Autorização/RBAC antes de autorizar uma sessão.

## OAuth 2.0 implementado

- `GET /v1/oauth/autorizar` inicia Authorization Code + PKCE e mostra a página de autenticação hospedada no Auth.
- `POST /v1/oauth/entrar` recebe o formulário dessa página. O aplicativo cliente não coleta nem envia senha ao Auth em seu próprio endpoint.
- `POST /v1/oauth/tokens` troca o código de uso único por tokens ou rotaciona um refresh token. O corpo é `application/x-www-form-urlencoded`.
- `POST /v1/oauth/revogar` segue o formato de formulário RFC 7009. Aceita um refresh token ou access token assinado e revoga a família inteira da sessão; sucesso idempotente não revela se o token era conhecido. Falha de persistência retorna `503`.
- `POST /v1/oauth/introspeccao` confirma estado de sessão e devolve `active`, `sub`, `jti` e `role`; exige credencial de serviço de Autorização/RBAC.
- O RBAC expõe `POST /v1/tokens/validar`: recebe o access token em `Authorization: Bearer`, confirma revogação online no Auth e confere o papel atual antes de devolver `ativo`, `conta_id` e `role`. Token inválido/revogado retorna `401`; dependência indisponível retorna `503`.
- `GET /.well-known/jwks.json` publica as chaves públicas RS256 atuais e anteriores.
- `GET /.well-known/oauth-authorization-server` publica os metadados e grants habilitados.

O access token usa `typ=at+jwt`, `kid`, `iss`, `sub` UUID, `aud`, `iat`, `exp`, `jti`, `client_id` e `role`, com validade de 25 minutos. O papel vem da consulta interna ao RBAC. Refresh tokens são opacos, armazenados somente como hash, rotacionados em uso e compartilhados pelo PostgreSQL para múltiplas instâncias.

O grant de senha (`password`) não é aceito no endpoint de tokens. A senha é submetida apenas ao formulário hospedado pelo Auth, no caminho separado `/v1/oauth/entrar`. Client Credentials ainda não está habilitado nos metadados nem no endpoint de tokens.

## Configuração

1. Copie `.env.example` para `.env` e configure `DATABASE_URL`, caminhos da chave privada RS256 e credenciais serviço a serviço.
2. A chave privada JWT deve ficar fora do Git. O `.env.example` contém somente placeholders.
3. `PERFIS_SERVICE_TOKEN` deve corresponder ao token usado por Perfis ao criar credenciais. `AUTORIZACAO_SERVICE_TOKEN` autentica a consulta de papel e introspecção.
4. Defina `PERFIS_URL`, `AUTORIZACAO_URL`, `OAUTH_CLIENT_ID`, `OAUTH_REDIRECT_URI`, `JWT_ISSUER` e `JWT_AUDIENCE` conforme o ambiente. No RBAC, configure `AUTHENTICACAO_URL` e `AUTHENTICACAO_SERVICE_TOKEN` para a introspecção online.

`PERFIS_STATUS_SERVICE_TOKEN` autentica Auth ao consultar status em Perfis. Ele deve corresponder a `INTERNAL_SERVICE_TOKEN` de Perfis. `PERFIS_SERVICE_TOKEN` autentica Perfis ao criar credenciais em Auth e deve corresponder a `AUTENTICACAO_SERVICE_TOKEN` de Perfis. Mantenha valores distintos para cada direção.

O procedimento de troca de chave está em [`docs/ROTACAO_CHAVES.md`](docs/ROTACAO_CHAVES.md).

## Migrações

Execute Alembic uma vez por implantação, de forma controlada, antes de iniciar ou escalar as instâncias:

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m alembic current
```

O Auth cria as tabelas de credenciais, sessões de refresh e códigos OAuth no schema `autenticacao`. A inicialização da API não executa migrações.

### Bancos compartilhados com perfis antigos

O histórico de versões do Auth fica em `autenticacao.alembic_version`. Perfis usa `public.alembic_version`.
Aplicar as migrações do Auth cria a estrutura para as credenciais. Os cadastros antigos de Perfis precisam de tratamento separado.

Antes da migração de Perfis que remove `public.perfis.senha`, use a consulta abaixo para contar os perfis que ainda precisam de credenciais no Auth.

```sql
SELECT count(*) AS perfis_sem_credencial
FROM public.perfis AS p
WHERE NOT EXISTS (
    SELECT 1 FROM autenticacao.credenciais AS c WHERE c.conta_id = p.id
);
```

Se houver pendências, combine com o responsável por Perfis quais contas precisam manter o acesso.
Para essas contas, provisione as credenciais com o mesmo UUID do perfil e valide o acesso antes da remoção da coluna.
Para cadastros de teste que possam perder as credenciais antigas, registre a decisão na issue.
O serviço Auth continua consultando apenas suas próprias tabelas em tempo de execução.

## Testes

Testes unitários e de rotas do Auth:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov
python -m pytest -q --cov=src --cov-report=term-missing --cov-fail-under=75
```

Para executar o fluxo real entre Auth, Perfis e RBAC, use apenas a pilha PostgreSQL isolada descrita em [`../docs/INTEGRACAO_LOCAL.md`](../docs/INTEGRACAO_LOCAL.md). Não use o Supabase compartilhado em testes que aplicam ou revertem migrações.
