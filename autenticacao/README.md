# Serviço de Autenticação

O Auth mantém credenciais, códigos de autorização e sessões de refresh no schema PostgreSQL `autenticacao`. A senha é guardada somente como hash Argon2id. O serviço consulta o status em Perfis e a associação de papel em Autorização/RBAC antes de autorizar uma sessão.

## OAuth 2.0 implementado

- `GET /v1/oauth/autorizar` inicia Authorization Code + PKCE e mostra a página de autenticação hospedada no Auth.
- `POST /v1/oauth/entrar` recebe o formulário dessa página. O aplicativo cliente não coleta nem envia senha ao Auth em seu próprio endpoint.
- `POST /v1/oauth/tokens` troca o código de uso único por tokens ou rotaciona um refresh token. O corpo é `application/x-www-form-urlencoded`.
- `POST /v1/oauth/revogar` recebe `token` como formulário e revoga a família correspondente quando for um refresh token válido. A resposta `200` não revela se o token era conhecido.
- `POST /v1/oauth/introspeccao` confirma estado de sessão e exige credencial de serviço de Autorização/RBAC.
- `GET /.well-known/jwks.json` publica as chaves públicas RS256 atuais e anteriores.
- `GET /.well-known/oauth-authorization-server` publica os metadados e grants habilitados.

O access token usa `typ=at+jwt`, `kid`, `iss`, `sub` UUID, `aud`, `iat`, `exp`, `jti`, `client_id` e `role`, com validade de 25 minutos. O papel vem da consulta interna ao RBAC. Refresh tokens são opacos, armazenados somente como hash, rotacionados em uso e compartilhados pelo PostgreSQL para múltiplas instâncias.

O grant de senha (`password`) não é aceito no endpoint de tokens. A senha é submetida apenas ao formulário hospedado pelo Auth, no caminho separado `/v1/oauth/entrar`. Client Credentials ainda não está habilitado nos metadados nem no endpoint de tokens.

## Configuração

1. Copie `.env.example` para `.env` e configure `DATABASE_URL`, caminhos da chave privada RS256 e credenciais serviço a serviço.
2. A chave privada JWT deve ficar fora do Git. O `.env.example` contém somente placeholders.
3. `PERFIS_SERVICE_TOKEN` deve corresponder ao token usado por Perfis ao criar credenciais. `AUTORIZACAO_SERVICE_TOKEN` autentica a consulta de papel e introspecção.
4. Defina `PERFIS_URL`, `AUTORIZACAO_URL`, `OAUTH_CLIENT_ID`, `OAUTH_REDIRECT_URI`, `JWT_ISSUER` e `JWT_AUDIENCE` conforme o ambiente.

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

## Testes

Testes unitários e de rotas do Auth:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov
python -m pytest -q --cov=src --cov-report=term-missing --cov-fail-under=75
```

Para executar o fluxo real entre Auth, Perfis e RBAC, use apenas a pilha PostgreSQL isolada descrita em [`../docs/INTEGRACAO_LOCAL.md`](../docs/INTEGRACAO_LOCAL.md). Não use o Supabase compartilhado em testes que aplicam ou revertem migrações.
