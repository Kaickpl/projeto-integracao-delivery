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
docker compose -f Docker-compose.integracao.yml run --rm autenticacao alembic upgrade head
docker compose -f Docker-compose.integracao.yml run --rm perfis alembic upgrade head
docker compose -f Docker-compose.integracao.yml run --rm autorizacao python -m alembic upgrade head
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
python -m pytest tests/test_integracao_servicos.py -q
```

O teste cria um cliente com CPF válido aleatório, verifica que o status pendente impede a autorização, ativa a conta no ambiente descartável, consulta o papel no RBAC, conclui Authorization Code + PKCE, valida assinatura e claims via JWKS, emite a sessão em uma instância Auth e renova/revoga em outra com a mesma persistência, tenta reutilizar o refresh anterior e verifica introspecção. O endpoint de perfil administrativo usado para ativar a conta não deve ser exposto sem autorização fora deste ambiente.

## Encerrar e descartar o banco local

```powershell
docker compose -f Docker-compose.integracao.yml down --volumes --remove-orphans
```

Não substitua a configuração deste arquivo pelos `.env` da turma. As migrações e o teste criam/alteram dados e são destinados somente ao PostgreSQL local isolado.
