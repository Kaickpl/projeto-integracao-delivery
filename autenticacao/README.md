# Serviço de Autenticação

O Auth mantém credenciais, códigos de autorização e sessões de refresh no schema PostgreSQL `autenticacao`. A senha é guardada somente como hash Argon2id. O serviço consulta o status em Perfis e a associação de papel em Autorização/RBAC antes de autorizar uma sessão.

## OAuth 2.0 implementado

- `GET /v1/oauth/autorizar` inicia Authorization Code + PKCE e mostra a página de autenticação hospedada no Auth.
- `POST /v1/oauth/entrar` recebe o formulário dessa página. O aplicativo cliente não coleta nem envia senha ao Auth em seu próprio endpoint.
- `POST /v1/oauth/tokens` troca o código de uso único por tokens ou rotaciona um refresh token. O corpo é `application/x-www-form-urlencoded`.
- `POST /v1/oauth/revogar` segue o formato de formulário RFC 7009. Aceita um refresh token ou access token assinado e revoga a família inteira da sessão; sucesso idempotente não revela se o token era conhecido. Falha de persistência retorna `503`.
- `POST /v1/oauth/introspeccao` confirma estado de sessão e devolve `active`, `sub`, `jti` e `role`; exige credencial de serviço de Autorização/RBAC.
- `POST /v1/oauth/tokens` também implementa `grant_type=client_credentials` quando `OAUTH_CLIENT_CREDENTIALS_ENABLED=true`. Exige `client_secret_basic`, `resource` (URI absoluta) e `scope`; emite somente access token RS256, sem refresh.
- `python -m src.gerenciar_clientes_servico criar <client_id>` cria um cliente e exibe o segredo uma vez. Os comandos `rotacionar <client_id>` e `desativar <client_id>` trocam o segredo ou impedem novas emissões. A rotação substitui imediatamente o segredo anterior e não reativa um cliente desativado.
- O RBAC expõe `POST /v1/tokens/validar`: recebe o access token em `Authorization: Bearer`, confirma revogação online no Auth e confere o papel atual antes de devolver `ativo`, `conta_id` e `role`. Token inválido/revogado retorna `401`; dependência indisponível retorna `503`.
- `GET /.well-known/jwks.json` publica as chaves públicas RS256 atuais e anteriores.
- `GET /.well-known/oauth-authorization-server` publica os metadados e grants habilitados.

O access token de usuário usa `typ=at+jwt`, `kid`, `iss`, `sub` UUID, `aud`, `iat`, `exp`, `jti`, `client_id` e `role`, com validade de 25 minutos. O papel vem da consulta interna ao RBAC. Refresh tokens são opacos, armazenados somente como hash, rotacionados em uso e compartilhados pelo PostgreSQL para múltiplas instâncias.

O access token M2M tem validade configurável de 1 a 15 minutos (10 por padrão), `sub=servico:<client_id>`, `client_id` e `scope`; não contém `role`, `sid`, claims pessoais nem refresh token. A validade curta limita o tempo de uso de tokens já emitidos: desativar ou rotacionar um cliente impede novas emissões, mas tokens existentes podem ser aceitos até expirar. Consumidores que exijam revogação imediata devem consultar a decisão de escopos no RBAC em cada operação protegida. O RBAC valida assinatura por JWKS e compara os escopos com a política atual em `POST /v1/tokens/servico/validar`.

O grant de senha (`password`) não é aceito no endpoint de tokens. A senha é submetida apenas ao formulário hospedado pelo Auth, no caminho separado `/v1/oauth/entrar`. Client Credentials fica desativado por padrão até o aceite do contrato pelos consumidores. Quando habilitado, aparece nos metadados OAuth.

## Configuração

1. Copie `.env.example` para `.env` e configure `DATABASE_URL`, caminhos da chave privada RS256 e credenciais serviço a serviço.
2. A chave privada JWT deve ficar fora do Git. O `.env.example` contém somente placeholders.
3. `PERFIS_SERVICE_TOKEN` deve corresponder ao token usado por Perfis ao criar credenciais. `AUTORIZACAO_SERVICE_TOKEN` autentica a consulta de papel e introspecção.
4. Defina `PERFIS_URL`, `AUTORIZACAO_URL`, `OAUTH_CLIENT_ID`, `OAUTH_REDIRECT_URI`, `OAUTH_REDIRECT_URIS`, `CORS_ORIGENS_PERMITIDAS`, `JWT_ISSUER` e `JWT_AUDIENCE` conforme o ambiente. As listas de callbacks e origens usam valores separados por vírgula e devem conter URLs exatas, sem curingas. No RBAC, configure `AUTHENTICACAO_URL` e `AUTHENTICACAO_SERVICE_TOKEN` para a introspecção online.

O CORS do Auth atende os frontends que fazem `fetch` para os metadados OAuth, troca/renovação de tokens e logout. A navegação para `/v1/oauth/autorizar` e o formulário `/v1/oauth/entrar` não dependem de CORS. Em desenvolvimento, o `.env.example` permite as origens `localhost:3000` e `localhost:5173`; no deploy, substitua pelas origens HTTPS publicadas. Registre todos os callbacks de cada aplicativo OAuth em `OAUTH_REDIRECT_URI` e `OAUTH_REDIRECT_URIS`.
5. Mantenha `OAUTH_CLIENT_CREDENTIALS_ENABLED=false` até Financeiro, Catálogo e RBAC aprovarem o método Basic, os nomes de `resource`/escopos, `sub` e validade. `OAUTH_SERVICE_TOKEN_MINUTES` limita os tokens de serviço a no máximo 15 minutos.

`PERFIS_STATUS_SERVICE_TOKEN` autentica Auth ao consultar status em Perfis. Ele deve corresponder a `INTERNAL_SERVICE_TOKEN` de Perfis. `PERFIS_SERVICE_TOKEN` autentica Perfis ao criar credenciais em Auth e deve corresponder a `AUTENTICACAO_SERVICE_TOKEN` de Perfis. Mantenha valores distintos para cada direção.

O procedimento de troca de chave está em [`docs/ROTACAO_CHAVES.md`](docs/ROTACAO_CHAVES.md).

## Migrações

Execute Alembic uma vez por implantação, de forma controlada, antes de iniciar ou escalar as instâncias:

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m alembic current
```

O Auth cria as tabelas de credenciais, sessões de refresh, códigos OAuth e clientes de serviço no schema `autenticacao`. A inicialização da API não executa migrações.

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
