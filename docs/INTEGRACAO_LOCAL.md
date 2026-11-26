# Integração local Auth, Perfis e RBAC

Este ambiente existe para aplicar as migrações e testar o fluxo real dos três serviços sem conectar ao Supabase compartilhado. O PostgreSQL de teste usa o banco isolado `delivery_teste`; seus dados ficam no container local.

## Iniciar PostgreSQL isolado

Na raiz do repositório, no PowerShell:

```powershell
docker compose -f Docker-compose.integracao.yml up -d banco_integracao
```

## Aplicar migrações uma vez

Rode cada migração como etapa controlada, antes das APIs:

```powershell
docker compose -f Docker-compose.integracao.yml run --build --rm autenticacao alembic upgrade head
docker compose -f Docker-compose.integracao.yml run --build --rm perfis alembic upgrade e5a9b3c7f1d2
docker compose -f Docker-compose.integracao.yml run --build --rm perfis alembic upgrade head
docker compose -f Docker-compose.integracao.yml run --build --rm autorizacao python -m alembic upgrade head
docker compose -f Docker-compose.integracao.yml run --build --rm preparar_cliente_m2m
docker compose -f Docker-compose.integracao.yml run --build --rm preparar_cliente_m2m_perfis
```

Confira as versões registradas:

```powershell
docker compose -f Docker-compose.integracao.yml run --rm autenticacao alembic current
docker compose -f Docker-compose.integracao.yml run --rm perfis alembic current
docker compose -f Docker-compose.integracao.yml run --rm autorizacao python -m alembic current
```

## Iniciar APIs

```powershell
docker compose -f Docker-compose.integracao.yml up -d autenticacao autenticacao_replica perfis autorizacao
```

## Criar o primeiro ADMIN

As rotas `/admin/*` de Perfis exigem um token de ADMIN. Com as APIs no ar, crie o administrador usado pelo teste:

```powershell
docker compose -f Docker-compose.integracao.yml run --build --rm preparar_admin_inicial
```

O comando é idempotente: se já existir um ADMIN ativo, nada é criado. O teste usa `admin-integracao@example.com` e a senha de teste definida no Compose; para usar outro, defina `INTEGRATION_ADMIN_EMAIL` e `INTEGRATION_ADMIN_SENHA`.

## Executar o teste ponta a ponta

Use o ambiente virtual de `autenticacao`. Esses valores são exclusivos da pilha de teste e não são segredos de produção:

```powershell
cd autenticacao
$env:RUN_CROSS_SERVICE_INTEGRATION = "1"
$env:INTEGRATION_DATABASE_NAME = "delivery_teste"
$env:INTEGRATION_AUTH_URL = "http://127.0.0.1:18001"
$env:INTEGRATION_AUTH_REPLICA_URL = "http://127.0.0.1:18004"
$env:INTEGRATION_PERFIS_URL = "http://127.0.0.1:18002"
$env:INTEGRATION_RBAC_URL = "http://127.0.0.1:18003"
$env:INTEGRATION_PERFIS_TOKEN = "teste-auth-perfis"
$env:INTEGRATION_RBAC_TOKEN = "teste-auth-rbac"
$env:INTEGRATION_M2M_CLIENT_ID = "teste-worker-financeiro"
$env:INTEGRATION_M2M_CLIENT_SECRET = "segredo-m2m-apenas-teste-local"
$env:INTEGRATION_M2M_AUDIENCE = "https://financeiro.example.test"
python -m pytest tests/test_integracao_servicos.py -q
```

Para incluir o teste de persistência após reiniciar uma instância Auth, antes do `pytest` defina `$env:INTEGRATION_RESTART_AUTH_REPLICA = "1"`. O teste reinicia somente `autenticacao_replica`, espera o health check e verifica que o refresh revogado segue inválido e que o RBAC continua retornando `401`.

O teste cria um cliente com CPF válido aleatório, envia `Idempotency-Key` UUID, verifica que o status pendente impede a autorização, confirma que a ativação sem token recebe `401`, ativa a conta com o token do ADMIN, consulta o papel no RBAC, conclui Authorization Code + PKCE, valida assinatura e claims via JWKS, verifica o access token no endpoint RBAC, renova e revoga em outra instância Auth com a mesma persistência, tenta reutilizar o refresh anterior e confirma que o RBAC retorna `401` após a revogação. Também testa logout com access token e confirma que o refresh da família deixa de funcionar.

O mesmo arquivo de teste inclui Client Credentials para permissões de pagamento e leitura de perfil, usando clientes temporários criados pelas fixtures somente no banco local. Ele solicita tokens com Basic, valida assinatura/claims via JWKS e consulta `GET /v1/perfis/{id}` com `perfis:ler`. As fixtures gravam a partir do container Auth e recusam qualquer banco que não esteja no host `banco_integracao`, com usuário `integracao_teste` e nome iniciado por `delivery_teste`. Com `INTEGRATION_RESTART_AUTH_REPLICA=1`, também reinicia a réplica e confirma que ela continua autenticando o cliente pelo estado persistido no banco.

Todas as rotas de criação de perfil (`POST /clientes`, `/lojas`, `/entregadores` e `/admin/admins`) exigem `Idempotency-Key` UUID. O cliente deve gerar uma chave por cadastro e reutilizá-la em qualquer repetição do mesmo pedido. Perfis grava o perfil como identidade pendente antes de chamar Auth e RBAC; uma falha retorna `503`, preserva a chave e permite retomar o provisionamento com a mesma requisição. Uma nova chave não retoma o cadastro anterior.

## Encerrar e descartar o banco local

```powershell
docker compose -f Docker-compose.integracao.yml down --volumes --remove-orphans
```

Não substitua a configuração deste arquivo pelos `.env` da turma. As migrações e o teste criam/alteram dados e são destinados somente ao PostgreSQL local isolado.
