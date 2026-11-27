# Equipe 1 — Identidade

Este repositório contém três serviços da plataforma de delivery, desenvolvidos em Python e FastAPI:

| Serviço | Responsabilidade | Porta local |
|---|---|---:|
| Autenticação (`autenticacao`) | Credenciais, login OAuth 2.0, emissão e revogação de tokens | 8001 |
| Perfis (`perfis`) | Cadastro de clientes, lojas, entregadores e administradores | 8002 |
| Autorização/RBAC (`autorizacao`) | Papéis, permissões de cada papel, decisões de autorização e permissões de serviços | 8003 |

## Fluxos principais

### Cadastro e login de pessoas

Perfis recebe os cadastros dos quatro tipos de conta. As credenciais são enviadas ao Auth, que guarda o hash da senha; o papel é associado no RBAC. Clientes, lojas e entregadores começam com o status `PENDENTE_APROVACAO`. O status da conta é separado do estado operacional da loja ou do entregador.

O login usa Authorization Code com PKCE. O usuário autentica-se na página do Auth; depois, o aplicativo troca o código e o verificador PKCE por tokens. Antes de emitir ou renovar tokens, Auth consulta o status em Perfis e o papel no RBAC. Só contas `ATIVO` recebem tokens.

Os access tokens de usuário são JWT assinados com RS256 e têm validade de 25 minutos. Claims importantes:

- `sub`: UUID `conta_id`;
- `role`: `CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`;
- `iss`, `aud`, `iat`, `exp` e `jti`.

O Auth publica as chaves públicas em `/.well-known/jwks.json`. Refresh tokens são rotativos e persistidos; o logout revoga a família da sessão. O RBAC oferece `POST /v1/tokens/validar` para conferir o token, a revogação e o papel atual.

### Autorização das rotas (RBAC)

Cada papel tem um conjunto de permissões no formato `recurso:acao` (por exemplo `perfis:alterar_status` ou `loja:operar`), mantido no RBAC. Os quatro papéis são fixos; o ADMIN pode conceder ou remover permissões de cada papel pela API do RBAC, e cada mudança fica registrada na auditoria.

As rotas protegidas de Perfis enviam o token do usuário a `POST /v1/tokens/validar`, que devolve o papel e as permissões atuais. Perfis libera a rota quando o papel tem a permissão; nas permissões `*_proprio`, também confere se o recurso é da própria conta. Sem token: `401`; sem permissão ou recurso de outra conta: `403`; RBAC ou Auth fora: `503`. Não há cache, então uma permissão removida vale na próxima requisição.

Continuam públicos o cadastro (`POST /clientes`, `/lojas`, `/entregadores`), a consulta de CEP e a vitrine de lojas (`GET /lojas`, `GET /lojas/{id}`, `GET /lojas/{id}/horarios`), que não devolve CNPJ, e-mail nem telefone. O cadastro de cliente aceita endereço opcional. Clientes autenticados podem consultar, editar nome/telefone/endereço e excluir a própria conta em `GET`, `PATCH` e `DELETE /clientes/{id}`. A tabela completa de permissões está em [Autorização/RBAC](autorizacao/README.md).

### Tokens para serviços (Client Credentials)

O Auth também implementa `grant_type=client_credentials`, com segredo individual por serviço, escopos e audiência. O RBAC mantém a política de permissões; os tokens M2M não têm `role` de usuário nem refresh token. A validade padrão é 10 minutos.

Este fluxo está **desativado por padrão** com `OAUTH_CLIENT_CREDENTIALS_ENABLED=false`. O Financeiro aceitou tokens M2M de 10 minutos validados localmente por JWKS para leitura de perfil, sem consultar RBAC a cada chamada; o RBAC continua autorizando escopos na emissão pelo Auth. Perfis oferece `GET /v1/perfis/{id}`, protegida pelo escopo `perfis:ler` e audiência local `http://perfis:8002`. O valor da audiência publicada e o provisionamento do cliente real ficam para quando o ambiente compartilhado estiver disponível. RabbitMQ não participa da emissão nem da decisão de autorização. Mais detalhes estão em [Alinhamento Client Credentials](autenticacao/docs/ALINHAMENTO_CLIENT_CREDENTIALS.md).

## Endpoints de referência

| Serviço | Endpoint | Uso |
|---|---|---|
| Auth | `GET /v1/oauth/autorizar` | Inicia o login Authorization Code + PKCE |
| Auth | `POST /v1/oauth/tokens` | Troca código, renova sessão ou, se habilitado, emite token M2M |
| Auth | `POST /v1/oauth/revogar` | Revoga uma sessão de usuário |
| Auth | `GET /.well-known/jwks.json` | Publica as chaves para validar assinaturas JWT |
| Perfis | `GET /v1/perfis/{id}` | Devolve `id`, `nome` e `email` a um serviço M2M autorizado com `perfis:ler` |
| Perfis | `POST /clientes`, `/lojas`, `/entregadores` | Cria perfil com provisionamento recuperável; exige `Idempotency-Key` UUID |
| Perfis | `GET`, `PATCH`, `DELETE /clientes/{id}` | Consulta, edita ou exclui a própria conta; exige token e permissão do RBAC |
| Perfis | `/admin/*`, `PATCH`/`DELETE` em `/lojas/{id}` e `/entregadores/{id}` | Exigem token de usuário com a permissão da rota |
| RBAC | `POST /v1/tokens/validar` | Valida token de usuário, confere papel/revogação e devolve as permissões do papel |
| RBAC | `POST /v1/autorizacao/verificar` | Responde se o usuário tem uma permissão |
| RBAC | `/v1/permissoes`, `/v1/papeis`, `/v1/auditoria` | Gestão de permissões por papel e auditoria (exige `rbac:gerenciar`) |
| RBAC | `POST /v1/tokens/servico/validar` | Valida token M2M e os escopos solicitados |

As rotas internas de consulta de status e permissões são destinadas à comunicação entre serviços. Consulte o Swagger de cada serviço para os schemas e respostas completos.

## Executar localmente

Pré-requisitos: Docker e Docker Compose. O Compose principal lê um `.env` em cada serviço. Copie os exemplos e preencha os valores locais; não coloque segredos reais no Git:

```powershell
Copy-Item autenticacao/.env.example autenticacao/.env
Copy-Item perfis/.env.example perfis/.env
Copy-Item autorizacao/.env.example autorizacao/.env
```

Configure os três arquivos com a mesma URL de banco apropriada ao ambiente e alinhe os tokens de serviço entre quem envia e quem recebe cada chamada. Mantenha as chaves JWT fora do repositório. Não use o banco compartilhado para testes destrutivos.

Antes de iniciar as APIs, aplique as migrações uma vez em cada serviço, usando a configuração do ambiente correspondente. Para a pilha local isolada e os comandos exatos, siga [Integração local](docs/INTEGRACAO_LOCAL.md). Não rode migrações de teste no banco compartilhado.

```powershell
docker compose run --rm autenticacao alembic upgrade head
docker compose run --rm perfis alembic upgrade head
docker compose run --rm autorizacao python -m alembic upgrade head
```

Depois, inicie os serviços:

```powershell
docker compose up --build
```

As rotas `/admin/*` de Perfis exigem um ADMIN autenticado. Com os três serviços no ar, crie o primeiro ADMIN uma única vez; a senha é pedida no terminal:

```powershell
docker compose run --rm perfis python -m src.criar_admin_inicial --nome "Nome do Admin" --email admin@exemplo.com --cpf SEU_CPF --telefone 81999990000 --data-nascimento 1990-01-31
```

Os demais administradores são criados por `POST /admin/admins`, com o token desse ADMIN.

Swagger/OpenAPI:

- Auth: <http://localhost:8001/docs>
- Perfis: <http://localhost:8002/docs>
- Autorização/RBAC: <http://localhost:8003/docs>

As migrações são uma etapa controlada e não são executadas automaticamente ao iniciar as instâncias.

## Testes

Para os testes unitários do Auth, a partir da pasta `autenticacao`:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov
python -m pytest -q --cov=src --cov-report=term-missing --cov-fail-under=75
```

Os testes de integração entre Auth, Perfis e RBAC usam um PostgreSQL local descartável. Siga [Integração local](docs/INTEGRACAO_LOCAL.md); não aponte essa composição para o Supabase compartilhado.

A meta do projeto é 80% de cobertura agregada, com mínimo de 75% por serviço conforme os requisitos. A cobertura agregada e sua execução automática em CI ainda precisam ser confirmadas/configuradas.

## Documentação por serviço

- [Auth: configuração, migrações e testes](autenticacao/README.md)
- [Contrato OAuth e tokens](autenticacao/docs/CONTRATO_OAUTH.md)
- [Rotação das chaves JWT](autenticacao/docs/ROTACAO_CHAVES.md)
- [Código e Swagger de Perfis](perfis/src/api/router.py)
- [Autorização/RBAC](autorizacao/README.md)
- [Integração local dos três serviços](docs/INTEGRACAO_LOCAL.md)

## Pendências conhecidas

- Fazer a suspensão de conta valer na hora: a introspecção do Auth não confere o status, então uma conta suspensa mantém acesso até o access token expirar (até 25 minutos).
- Definir recuperação/idempotência para falhas parciais no cadastro, que atualmente chama Perfis, Auth e RBAC sem uma transação distribuída.
- Obter o aceite de Vitor e dos consumidores para os contratos de login, validação JWT/JWKS, audiência, escopos e claims.
- Testar Client Credentials com um consumidor real da turma; os testes atuais usam um consumidor simulado.
- Confirmar as migrações e configurações no ambiente compartilhado por procedimento controlado.
