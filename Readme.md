# 🔐 Equipe 1 — Identidade

Conjunto de **3 microsserviços** responsáveis pela base de identidade do sistema: autenticação, cadastro de perfis e autorização. Todos os demais serviços da turma (15 microsserviços no total) consultam esta equipe para **validar acesso**.

Desenvolvido em **Python** com **FastAPI**.

---

## 👥 Integrantes

| Nome |
|------|
| Marcelo Arthur dos Santos Moura |
| João Vitor dos Santos Marques |
| Vinicius Gabriel Santos Bezerra |
| Kaick José Pita de Mendonça Lopes |

---

## 🧩 Serviços

| Serviço | Responsabilidade | Porta (sugestão) |
|---------|------------------|------------------|
| **Autenticação** | Login e geração/validação de tokens JWT | `8001` |
| **Perfis** | Cadastro (CRUD) de clientes e lojas | `8002` |
| **Autorização** | Gestão de papéis e permissões (RBAC) | `8003` |

### Papel na integração

```
           ┌──────────────────────┐
           │  Serviços das demais │
           │       equipes        │
           └──────────┬───────────┘
                      │  "Este token é válido?"
                      │  "Este usuário pode fazer X?"
                      ▼
 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
 │ Autenticação │◄─┤    Perfis    │  │ Autorização  │
 │    (JWT)     │  │(clientes/    │  │   (RBAC)     │
 │              │  │   lojas)     │  │              │
 └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Arquitetura

Cada serviço segue a mesma estrutura, organizada **por domínio** (módulos):

```
projeto/
├── src/
│   ├── core/              # Configurações globais, segurança e banco de dados
│   │   ├── config.py      # Variáveis de ambiente (Pydantic BaseSettings)
│   │   ├── database.py    # Conexão com o banco (SQLAlchemy / SQLModel / MongoDB)
│   │   └── security.py    # Funções de JWT, hash de senha, etc.
│   │
│   ├── modules/           # Organização por domínio/recurso (ex: users, items)
│   │   └── users/
│   │       ├── router.py  # Endpoints específicos do FastAPI (APIRouter)
│   │       ├── schemas.py # Validação e serialização de dados (Pydantic)
│   │       ├── models.py  # Modelos/Tabelas do Banco de Dados (ORM)
│   │       └── service.py # Regras de negócio do domínio
│   │
│   ├── api/               # Centralizador de rotas
│   │   └── router.py      # Agrupa os routers dos módulos
│   │
│   └── main.py            # Inicialização da aplicação FastAPI
│
├── tests/                 # Testes unitários e de integração (Pytest)
├── Dockerfile             # Configuração de container
└── requirements.txt       # Dependências do projeto
```

### Responsabilidade de cada camada

| Camada | Arquivo | O que faz | O que **não** faz |
|--------|---------|-----------|-------------------|
| Rota | `router.py` | Recebe a requisição e devolve a resposta | Regra de negócio |
| Contrato | `schemas.py` | Valida entrada e formata saída (Pydantic) | Acessar o banco |
| Persistência | `models.py` | Define tabelas/coleções | Validar regras |
| Negócio | `service.py` | Aplica as regras do domínio | Lidar com HTTP |

Fluxo de uma requisição:

```
Requisição → router.py → schemas.py (validação) → service.py → models.py → Banco
```

---

## Convenções da turma (obrigatórias)

Essas regras garantem que as APIs de todas as equipes conversem sem quebrar.

### 1. Idioma do código e das rotas
Definido em reunião de alinhamento: **`[ PORTUGUÊS | INGLÊS ]`** ← *preencher após a reunião*.
Nunca misturar idiomas (ex: um serviço envia `user_id` e outro espera `id_usuario`).

### 2. Padrão de resposta de erro
Todas as APIs devolvem o mesmo formato, com o **código HTTP correto** (400, 401, 403, 404, 500...):

```json
{
  "erro": true,
  "mensagem": "Detalhes da falha"
}
```

Exemplo de implementação no FastAPI (`main.py`):

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"erro": True, "mensagem": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"erro": True, "mensagem": "Dados inválidos na requisição"},
    )
```

### 3. Data e hora
Exclusivamente **ISO 8601** em UTC:

```
✅ "2026-08-24T14:30:00Z"
❌ "24/08/2026"
```

### 4. Valores financeiros
Sempre **inteiros em centavos** — nunca ponto flutuante:

```
R$ 25,90  →  2590
```

---

## Como executar

### Pré-requisitos
- [Docker](https://www.docker.com/) e Docker Compose

Nenhuma outra dependência precisa ser instalada localmente.

### Subindo os serviços

```bash
docker compose up --build
```

### Documentação (Swagger / OpenAPI)

Com os serviços rodando, acesse:

| Serviço | Swagger | ReDoc |
|---------|---------|-------|
| Autenticação | http://localhost:8001/docs | http://localhost:8001/redoc |
| Perfis | http://localhost:8002/docs | http://localhost:8002/redoc |
| Autorização | http://localhost:8003/docs | http://localhost:8003/redoc |

Todos os contratos devem estar documentados com `response_model`, exemplos e códigos de status, para que outras equipes consigam trabalhar com **mocks** antes da API real ficar pronta.

### Rodando sem Docker (desenvolvimento)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

---

## Variáveis de ambiente

Crie um arquivo `.env` na raiz de cada serviço (nunca versionar):

```env
DATABASE_URL=postgresql://usuario:senha@db:5432/identidade
JWT_SECRET_KEY=troque-esta-chave
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
```

---

## Testes

Exigência da disciplina: **cobertura mínima de 75%** (testes unitários e de integração com Pytest).

```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=75
```

Dentro do container:

```bash
docker compose exec autenticacao pytest --cov=src --cov-fail-under=75
```

---
 
## Tecnologias
 
- **Python** 3.12+
- **FastAPI** `0.142.2` — framework web
- **Starlette** `1.7.0` — base ASGI do FastAPI (rotas, requisições e respostas)
- **Pydantic** `2.13.5` — validação e serialização de dados
- **Uvicorn** `0.54.0` — servidor ASGI que executa a aplicação
- **OpenTelemetry API** `1.45.0` — instrumentação para rastreamento e observabilidade
- **Docker / Docker Compose** — conteinerização
### Dependências (`requirements.txt`)
 
```txt
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
click==8.5.0
fastapi==0.142.2
h11==0.16.0
idna==3.20
opentelemetry-api==1.45.0
pydantic==2.13.5
pydantic_core==2.46.5
starlette==1.7.0
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.54.0
```
 
> As bibliotecas `anyio`, `h11`, `idna`, `click`, `annotated-types`, `pydantic_core`, `typing-inspection` e `typing_extensions` são dependências internas do FastAPI, Pydantic e Uvicorn — não são usadas diretamente no código.
 
---
