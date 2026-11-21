# Persistência de credenciais do Auth

O Auth usa o PostgreSQL do Supabase com SQLAlchemy e Psycopg 3. A autenticação permanece neste serviço. A tabela `autenticacao.credenciais` e o histórico `autenticacao.alembic_version` ficam no schema `autenticacao`, separado das tabelas de Perfis e do schema reservado `auth` do Supabase. Mantenha `autenticacao` fora dos schemas expostos pela Data API.

## Configuração

1. Na pasta `autenticacao`, copie `.env.example` para `.env`. Guarde o arquivo localmente e fora do Git, das issues e dos logs.
2. No painel do Supabase, abra **Connect** e copie o usuário, o host, a porta e o banco da modalidade escolhida. Troque o prefixo `postgresql://` por `postgresql+psycopg://` e aplique codificação de URL aos caracteres reservados da senha.
3. Use SSL com `sslmode=require`. Para também verificar a identidade do servidor, use `sslmode=verify-full` com `sslrootcert` apontando para o certificado raiz baixado no painel.

| Uso | Conexão |
| --- | --- |
| API persistente (Docker, por exemplo) | Direta na porta 5432 quando acessível, ou **Session pooler** na porta 5432 para redes só com IPv4. |
| Migrações | Preferir a conexão direta na porta 5432. Usar **Session pooler** na porta 5432 quando a direta estiver inacessível. |

Use os valores exibidos pelo painel. Usuário e host da conexão direta e do pooler são diferentes. O pooler compartilhado em modo transação, na porta 6543, tem restrições com *prepared statements* e fica fora desta configuração. Cada processo da API mantém seu próprio pool SQLAlchemy. Ao aumentar o número de réplicas da API, considere o total de conexões que o banco aceita. Veja a [documentação de conexões do Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Migrações

Execute uma vez por atualização, em uma etapa controlada antes de iniciar as réplicas. O processo de migração precisa criar o schema `autenticacao` na primeira execução e gerenciar suas tabelas. Se a equipe usar papéis separados no PostgreSQL, conceda ao papel da API apenas acesso ao schema e às operações necessárias na tabela de credenciais.

Com Python 3.12+ e o ambiente virtual ativo, rode dentro de `autenticacao`:

```bash
python -m pip install -r requirements.txt
alembic upgrade head
alembic current
```

Com Docker Compose, rode na raiz do projeto depois de preparar o `.env`:

```bash
docker compose -f Docker-compose.yml build autenticacao
docker compose -f Docker-compose.yml run --rm --no-deps autenticacao alembic upgrade head
```

## Uso dentro do Auth

Use `get_db` como dependência de sessão e passe a sessão para `RepositorioCredenciais`. O chamador controla o commit e o rollback. `criar` gera um hash Argon2id com um *salt* aleatório e grava apenas o hash completo. Para verificar uma senha, passe-a com o hash armazenado para `verificar_senha`. O banco compara e-mails sem distinguir maiúsculas de minúsculas. Seu índice único resolve disputas de cadastro mesmo entre processos diferentes. A duplicidade chega ao chamador como `IntegrityError` no `flush`. O cadastro e o login públicos serão implementados nas próximas entregas.

## Testes

Use um PostgreSQL local com um banco vazio e descartável cujo nome comece com `auth_teste`. A suíte aplica e reverte a migração e inclui duas conexões concorrentes. Em `autenticacao`, com o ambiente virtual ativo:

```bash
python -m pip install -r requirements-dev.txt
createdb auth_teste
TEST_DATABASE_URL='postgresql+psycopg://USUARIO:SENHA@127.0.0.1:5432/auth_teste' \
  python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=75
```

Substitua os dados da URL pela configuração do banco local de testes. Sem `TEST_DATABASE_URL`, os testes de integração são pulados.

## Transição de Perfis para Auth

O cadastro de administrador em Perfis ainda grava em `perfis.senha`. A coluna tem limite de 30 caracteres e um índice único, incompatíveis com o armazenamento de hashes completos no Auth.

A proposta para validar com o responsável por Perfis é usar o mesmo `conta_id` (UUID) nos dois serviços e mover a criação e a verificação de credenciais para o Auth. No corte, revisar as contas existentes e combinar com a equipe como invalidar as senhas legadas e emitir novas credenciais. Depois de retirar a escrita pela API de Perfis, criar uma **nova** migração de Perfis para remover a coluna e seu índice. Essa decisão de integração fica para a equipe antes de usar o fluxo de cadastro para contas reais.
