# Contrato OAuth 2.0 e tokens — Identidade

**Estado:** proposta-base interna, pronta para revisão pelas equipes consumidoras. Valores descritos como provisórios precisam ser confirmados antes da integração externa.

## Serviços e responsabilidades

- **Perfis** é responsável pelo cadastro dos quatro tipos de perfil: `CLIENTE`, `LOJA`, `ENTREGADOR` e `ADMIN`. O cadastro de cliente é feito em Perfis, não em Auth.
- **Perfis** valida CPF por formato e dígitos verificadores, sem comprovação externa. O perfil de cliente começa com status `PENDENTE_APROVACAO`; Perfis governa sua transição para `ATIVO`.
- **Auth** mantém credenciais e sessões. Recebe de Perfis a solicitação interna INT-02 com e-mail, senha e tipo de conta, grava somente hash de senha e devolve `conta_id`.
- `Perfil.id` e `Auth.conta_id` usam o mesmo UUID. O cadastro em Perfis só conclui o vínculo depois de obter esse identificador do Auth.
- **Autorização/RBAC** é a fonte autoritativa da associação entre `conta_id` e papel. Auth não concede nem deduz papel a partir de campos cadastrais.

## Fluxos OAuth 2.0

### Usuário interativo

Usar Authorization Code com PKCE. O aplicativo redireciona o usuário ao Authorization Server; o aplicativo não coleta a senha para repassá-la em um grant de senha. O grant Resource Owner Password Credentials não será usado.

### Serviço para serviço

Usar Client Credentials com credencial distinta por serviço consumidor. Segredos de serviço ficam em configuração secreta e nunca são incluídos em tokens de usuário, eventos ou logs.

## Endpoints planejados

| Endpoint | Uso |
| --- | --- |
| `GET /v1/oauth/autorizar` | Início do Authorization Code + PKCE para usuário interativo. |
| `POST /v1/oauth/tokens` | Trocar código por tokens; renovar via refresh token; ou emitir token de serviço com Client Credentials. |
| `POST /v1/oauth/revogar` | Revogar refresh token/sessão; sucesso só depois da persistência da revogação. |
| `POST /v1/oauth/introspeccao` | Consulta autenticada por serviço confiável (Autorização/RBAC) para confirmar `active`, `sub` e `jti`, inclusive estado de revogação. |
| `GET /.well-known/jwks.json` | Publicar chaves públicas para validar assinaturas. |
| `GET /.well-known/oauth-authorization-server` | Metadados do Authorization Server, incluindo issuer, endpoints, grant types e `jwks_uri`. |

Os caminhos da API são a proposta de contrato em português. Os caminhos `/.well-known/jwks.json` e `/.well-known/oauth-authorization-server` permanecem conforme os padrões de descoberta. Rotas de escrita usam HTTPS. Clientes OAuth de serviço são autenticados; introspecção não é pública.

## Access token

- JWT de acesso assinado com **RS256**, cabeçalho `typ: at+jwt` e `kid` para seleção da chave no JWKS.
- Duração: **25 minutos**, conforme RF001/RNF-02.
- Claims: `iss`, `sub` (UUID `conta_id`), `aud`, `exp`, `iat`, `jti`, `client_id` e `role`.
- `role` aceita `CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`, sempre obtido da associação autoritativa em Autorização/RBAC.
- Não incluir nome, e-mail, CPF, telefone, senha ou outro dado pessoal cadastral.
- Os serviços validam localmente assinatura, `typ`, `iss`, `aud` e `exp` por JWKS. Autorização/RBAC consulta também o endpoint de introspecção antes de autorizar a operação, para detectar revogações e cumprir INT-05. Serviços de recurso devem passar pela decisão do RBAC para operações protegidas.

## Refresh, status e revogação

- Refresh token é opaco, aleatório, rotativo e de uso único; armazenar no banco apenas hash/identificador não reversível e estado da família de sessão.
- **Prazo provisório do refresh token:** 7 dias. A equipe pode alterar este prazo ao revisar a proposta.
- Reutilização de refresh token já rotacionado revoga a família de sessão e exige novo login.
- Login e refresh consultam o status atual no serviço Perfis por `conta_id` (INT-01). Só `ATIVO` recebe tokens. Conta pendente/suspensa recebe `403`; indisponibilidade de Perfis resulta em `503`, sem emissão/renovação.
- Logout revoga a sessão/família de refresh no PostgreSQL compartilhado antes de responder sucesso. A introspecção retorna `active: false` para tokens/sessões revogados.
- Se o estado persistido não puder ser atualizado, logout não pode ser confirmado como concluído. Revogação não depende de cache local nem de entrega de mensagem.

## RabbitMQ

Requisições de autorização, token, refresh, revogação e introspecção são síncronas por HTTP, pois o chamador precisa do resultado antes de continuar. RabbitMQ é usado somente para notificações/eventos assíncronos, por exemplo `identity.session.revoked`, depois da persistência autoritativa.

Evento proposto:

```json
{
  "event_id": "uuid",
  "event_type": "identity.session.revoked",
  "occurred_at": "2026-11-23T12:00:00Z",
  "conta_id": "uuid",
  "session_id": "uuid"
}
```

Consumidores tratam duplicatas de forma idempotente. Evento não contém senha, hash de senha, token, segredo OAuth ou CPF. A indisponibilidade do broker pode atrasar notificações, mas não desfaz nem ignora revogação registrada no banco.

## Respostas de erro

- Usar os códigos HTTP do fluxo OAuth e um código OAuth `error` estável para clientes de máquina.
- Manter também o envelope comum da turma quando compatível: `{"erro": true, "mensagem": "..."}`. Mensagens em português, genéricas para falhas de credenciais, sem revelar se e-mail/conta existe.
- Sem tokens em respostas de falha. Nunca registrar senha, access token, refresh token, segredo de cliente ou CPF completo.

## Cobertura e entrega

- O projeto acompanha **80% de cobertura agregada**; cada serviço mantém o mínimo formal de **75%** indicado nos requisitos. A CI deve mostrar os dois valores.
- Contratos de sucesso/erro e claims devem ter exemplos em OpenAPI e testes de contrato/mocks compartilhados.
- Branch por issue a partir de `develop` atualizada e PR com destino a `develop`.

## Dependências ainda não implementadas/confirmadas

1. Vitor: login #8 precisa chamar o emissor sem assumir um contrato diferente.
2. Perfis: endpoint interno INT-01 de consulta de status por `conta_id`; o modelo e as rotas administrativas existem, mas o contrato Auth–Perfis não está exposto.
3. Perfis: INT-02 precisa usar o UUID comum e parar de persistir senha em `perfis.senha`; o cadastro de cliente também deve ser criado em Perfis.
4. Autorização/RBAC: INT-03 fornece papel por `conta_id`; INT-05 usa introspecção/validação de revogação antes da decisão de acesso.
5. Infraestrutura: RabbitMQ, credenciais de serviço, banco compartilhado para sessões e gestão/rotação segura da chave privada RS256.
6. Equipes consumidoras: confirmar `role`, `aud`, JWKS, endpoint de introspecção e formato de erro antes de depender do contrato em produção.
