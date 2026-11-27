# Contrato OAuth 2.0 e tokens — Identidade

**Estado:** Authorization Code + PKCE, refresh, revogação, introspecção e JWKS estão implementados. Client Credentials está implementado atrás de configuração desativada por padrão; os consumidores só devem utilizá-lo depois de aceitar o contrato e habilitá-lo explicitamente.

## Serviços e responsabilidades

- **Perfis** é responsável pelo cadastro dos quatro tipos de perfil: `CLIENTE`, `LOJA`, `ENTREGADOR` e `ADMIN`. O cadastro de cliente é feito em Perfis, não em Auth.
- **Perfis** valida CPF por formato e dígitos verificadores, sem comprovação externa. O perfil de cliente começa com status `PENDENTE_APROVACAO`; Perfis governa sua transição para `ATIVO`.
- **Auth** mantém credenciais e sessões. Recebe de Perfis a solicitação interna INT-02 com e-mail, senha e tipo de conta, grava somente hash de senha e devolve `conta_id`.
- `Perfil.id` e `Auth.conta_id` usam o mesmo UUID. O cadastro em Perfis só conclui o vínculo depois de obter esse identificador do Auth.
- **Autorização/RBAC** é a fonte autoritativa da associação entre `conta_id` e papel. Auth não concede nem deduz papel a partir de campos cadastrais.

O cadastro distribuído em Perfis exige `Idempotency-Key` (UUID) nas rotas de criação. Perfis persiste primeiro o perfil com `identidade_pronta=false`, sem persistir senha, e então provisiona Auth e RBAC. Se uma dependência falhar ou a resposta se perder, a mesma requisição pode ser repetida com a mesma chave, mesmos dados e senha: Auth confirma idempotentemente a credencial existente e RBAC faz upsert do papel. Só após ambos confirmarem Perfis marca a identidade como pronta. Enquanto pendente, a conta não autentica e a leitura M2M do perfil responde `503`. Uma chave repetida com outros dados cadastrais recebe `409`.

## Provisionamento interno (INT-02)

Perfis chama `POST /v1/interno/credenciais` por HTTP síncrono, com seu token
dedicado em `Authorization: Bearer`. O corpo contém `conta_id` (UUID gerado
por Perfis), `email`, `senha` e `tipo_conta` (`CLIENTE`, `LOJA`,
`ENTREGADOR` ou `ADMIN`). O Auth armazena o hash Argon2id da senha. O
RabbitMQ não participa da operação.

| Status | Resultado |
| --- | --- |
| 201 | Nova credencial. Corpo `{"conta_id": "<uuid>"}`. |
| 200 | Mesmo UUID, e-mail e senha já provisionados. Mesmo corpo de sucesso. |
| 400 | Tipo de conta inválido. |
| 401 | Bearer de Perfis ausente ou inválido. |
| 409 | E-mail vinculado a outra conta ou credencial divergente para o mesmo UUID. |
| 422 | Dados inválidos. Os detalhes identificam os campos sem ecoar valores. |

Para exclusão de conta, Perfis chama `DELETE /v1/interno/credenciais/{conta_id}` com o mesmo Bearer interno. A operação remove a credencial e revoga todas as sessões no Auth; chamadas repetidas são idempotentes.

## Fluxos OAuth 2.0

### Usuário interativo

Usar Authorization Code com PKCE. O aplicativo redireciona o usuário ao Authorization Server; o aplicativo não coleta a senha para repassá-la em um grant de senha. O grant Resource Owner Password Credentials não será usado.

No INT-01, `POST /v1/oauth/entrar` verifica e-mail e senha. Depois lê
`conta_id`, `status` e `identidade_pronta` de Perfis antes de consultar o
papel no RBAC. O sucesso devolve `303` com `code` e o `state` original
na URL de retorno. Credenciais inválidas devolvem `401` com a mesma mensagem,
conta inelegível devolve `403` e falha de comunicação ou resposta inválida
de Perfis devolve `503`.

Com `grant_type=authorization_code`, `POST /v1/oauth/tokens` valida código
e PKCE, reconsulta Perfis e RBAC e emite o access token e o refresh token.
Código ou PKCE inválido devolve `400`. Inelegibilidade ou falha de integração
devolve `403` ou `503`. Os erros HTTP dessas operações de usuário usam
`{"detail": "mensagem em português"}`. A validação dos campos obrigatórios
continua respondendo `422` com detalhes por campo.

### Bloqueio temporário de login

A quinta senha incorreta para uma conta em uma janela de 15 minutos inicia
um bloqueio de 15 minutos. O PostgreSQL de escrita mantém o histórico e o
prazo compartilhados entre as instâncias. Senha incorreta, e-mail inexistente
e bloqueio usam o mesmo `401`. Durante o bloqueio, até uma senha correta
ou a troca de um código emitido anteriormente recebe `401`.

Tentativas durante o bloqueio não prorrogam seu prazo. O login bem-sucedido
limpa o histórico. A decisão não altera o status cadastral em Perfis.
Aplicar a migração de Auth uma vez antes de atualizar as instâncias.

### Serviço para serviço

Client Credentials usa `client_secret_basic`, `resource` como URI absoluta (RFC 8707) e `scope` com escopos separados por espaço em `POST /v1/oauth/tokens`. Erros incluem `error` OAuth estável e a mensagem comum em português. O Auth armazena somente hash Argon2id de credenciais individuais. Antes de emitir, consulta a política autoritativa de audiência/escopos no RBAC. O grant fica desativado por padrão até o aceite dos consumidores e do RBAC; quando habilitado, é publicado nos metadados.

O access token M2M usa `sub=servico:<client_id>`, `client_id` e `scope`, além de `iss`, `aud`, `iat`, `exp` e `jti`. Não inclui `role`, `sid` ou claims pessoais; não há refresh token. Para o worker do Financeiro, a validade acordada é **10 minutos** (`OAUTH_SERVICE_TOKEN_MINUTES=10`). Rotacionar/desativar um cliente ou remover escopos impede novas emissões, mas tokens existentes validados localmente podem ser aceitos até `exp`, por no máximo 10 minutos. O Financeiro validará assinatura e claims localmente por JWKS nas chamadas M2M de leitura de perfil, sem consultar RBAC a cada requisição. O RBAC continua sendo a fonte autoritativa consultada pelo Auth na emissão; `POST /v1/tokens/servico/validar` permanece disponível para operações que precisem conferir a política atual online. Perfis oferece `GET /v1/perfis/{id}` com audiência local `http://perfis:8002` e escopo `perfis:ler`; no ambiente publicado, a audiência deve ser substituída pela URL real de Perfis.

Clientes são provisionados em operação administrativa local; o segredo aparece apenas uma vez. Permissões são concedidas/removidas no RBAC por operação administrativa local. Chamadas internas atuais entre Auth, Perfis e RBAC continuam com seus tokens dedicados até cada consumidor migrar. RabbitMQ não participa da emissão, da consulta de permissões nem da validação de tokens.

## Endpoints

| Endpoint | Uso |
| --- | --- |
| `GET /v1/oauth/autorizar` | Início do Authorization Code + PKCE; apresenta a página hospedada no Auth. |
| `POST /v1/oauth/entrar` | Submissão do formulário hospedado pelo Auth; não é um grant OAuth de senha. |
| `POST /v1/oauth/tokens` | Trocar código, renovar via refresh token ou, quando habilitado, emitir token M2M via Client Credentials. |
| `POST /v1/oauth/revogar` | Revogar a família de sessão pelo refresh token; resposta não revela se o token existe. |
| `POST /v1/oauth/introspeccao` | Consulta autenticada por serviço confiável (Autorização/RBAC) para confirmar `active`, `sub`, `jti` e `role`, inclusive estado de revogação. |
| `POST /v1/tokens/validar` (Autorização/RBAC) | Recebe o access token em `Authorization: Bearer`, confirma a sessão online no Auth e devolve o papel atualmente associado no RBAC e as permissões desse papel (`permissoes`). |
| `POST /v1/autorizacao/verificar` (Autorização/RBAC) | Com o mesmo token e `{"permissao": "recurso:acao"}`, responde `200` se o papel atual tem a permissão ou `403` se não tem. |
| `GET /v1/interno/clientes/{client_id}/permissoes?audiencia=...` (Autorização/RBAC) | Auth consulta, com credencial interna, os escopos autorizados ao cliente e recurso. |
| `POST /v1/tokens/servico/validar` (Autorização/RBAC) | Valida um token M2M por JWKS, compara os escopos requeridos com o token e com a política atual do RBAC. |
| `GET /.well-known/jwks.json` | Publicar chaves públicas para validar assinaturas. |
| `GET /.well-known/oauth-authorization-server` | Metadados do Authorization Server, incluindo issuer, endpoints, grant types e `jwks_uri`. |

Os caminhos da API são o contrato em português. Os caminhos `/.well-known/jwks.json` e `/.well-known/oauth-authorization-server` permanecem conforme os padrões de descoberta. Rotas de escrita usam HTTPS. Introspecção não é pública. O metadado `client_credentials` só aparece quando `OAUTH_CLIENT_CREDENTIALS_ENABLED=true`.

## Access token

- JWT de acesso assinado com **RS256**, cabeçalho `typ: at+jwt` e `kid` para seleção da chave no JWKS.
- Duração: **25 minutos**, conforme RF001/RNF-02.
- Claims: `iss`, `sub` (UUID `conta_id`), `aud`, `exp`, `iat`, `jti`, `client_id` e `role`.
- `role` aceita `CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`, sempre obtido da associação autoritativa em Autorização/RBAC.
- Não incluir nome, e-mail, CPF, telefone, senha ou outro dado pessoal cadastral.
- Os serviços validam localmente assinatura, `typ`, `iss`, `aud` e `exp` por JWKS. Para tokens de usuário, o contrato INT-05 continua exigindo validação online no RBAC/Auth para detectar revogação e papel desatualizado. Para o token M2M do Financeiro na leitura de perfil, foi acordada validação local por JWKS e escopo, sem consulta ao RBAC por chamada, aceitando a janela de até 10 minutos para uma alteração de permissão/revogação surtir efeito. A API de recurso deve aplicar audiência e escopo localmente.

## Refresh, status e revogação

- Refresh token é opaco, aleatório, rotativo e de uso único; armazenar no banco apenas hash/identificador não reversível e estado da família de sessão.
- **Prazo provisório do refresh token:** 7 dias. A equipe pode alterar este prazo ao revisar a proposta.
- Reutilização de refresh token já rotacionado revoga a família de sessão e exige novo login.
- Logout revoga a família inteira da sessão, incluindo tokens de refresh anteriores, o refresh atual e o access token associado. O endpoint aceita `token` e um `token_type_hint` opcional em formulário RFC 7009; a indicação não altera a resposta idempotente.
- Login e refresh consultam o status atual no serviço Perfis por `conta_id` (INT-01). Só `ATIVO` recebe tokens. Conta pendente/suspensa recebe `403`; indisponibilidade de Perfis resulta em `503`, sem emissão/renovação.
- Logout revoga a sessão/família de refresh no PostgreSQL compartilhado antes de responder sucesso. A introspecção retorna `active: false` para tokens/sessões revogados. Se o banco falhar, Auth responde `503` e não confirma o logout.
- Antes de autorizar uma requisição protegida, consumidores consultam `POST /v1/tokens/validar` no RBAC com o access token do usuário. RBAC consulta a introspecção autenticada do Auth; token inválido, expirado, revogado ou com papel desatualizado resulta em `401`. Indisponibilidade do Auth ou do banco RBAC resulta em `503` (falha fechada).
- Se o estado persistido não puder ser atualizado, logout não pode ser confirmado como concluído. Revogação não depende de cache local nem de entrega de mensagem.

## Mensageria (RabbitMQ)

RabbitMQ não está implementado neste fluxo: Auth não publica nem consome eventos para login, Client Credentials, emissão, refresh, consulta de permissões ou logout. Essas operações usam HTTP síncrono e PostgreSQL; o Auth só emite o token depois de receber a decisão do RBAC. O RBAC mantém as permissões atuais, e a validação online compara os escopos do token com essa política.

Um evento de auditoria ou notificação de revogação poderá ser combinado futuramente. Ainda não há nome, payload, consumidores, política de repetição nem tratamento de falha acordados; por isso, este contrato não define evento de exemplo. Se a turma contratar eventos, eles serão complementares: não autorizam nem revogam por si só, não substituem o estado persistido e nunca incluem senha, hash, access token, refresh token ou segredo de cliente. A indisponibilidade do RabbitMQ não pode impedir a emissão síncrona nem desfazer uma revogação já persistida.

## Respostas de erro

- Usar os códigos HTTP do fluxo OAuth e um código OAuth `error` estável para clientes de máquina.
- Manter também o envelope comum da turma quando compatível: `{"erro": true, "mensagem": "..."}`. Mensagens em português, genéricas para falhas de credenciais, sem revelar se e-mail/conta existe.
- Sem tokens em respostas de falha. Nunca registrar senha, access token, refresh token, segredo de cliente ou CPF completo.

## Cobertura e entrega

- O projeto acompanha **80% de cobertura agregada**; cada serviço mantém o mínimo formal de **75%** indicado nos requisitos. A CI deve mostrar os dois valores.
- Contratos de sucesso/erro e claims devem ter exemplos em OpenAPI e testes de contrato/mocks compartilhados.
- Branch por issue a partir de `develop` atualizada e PR com destino a `develop`.

## Pendências de integração

1. Financeiro, Catálogo e Autorização/RBAC precisam aceitar o método de autenticação, formato de `sub`, `aud`/`resource`, nomes de escopos e validade dos tokens M2M antes de habilitar o grant em ambientes compartilhados.
2. Ainda falta integrar um consumidor real da turma; os testes locais usam um fluxo simulado.
3. Qualquer uso de RabbitMQ precisa de contrato acordado com os serviços participantes. Não é dependência para emitir ou validar tokens neste contrato.

O código de Client Credentials, as migrações, os comandos de gestão e os testes locais já estão implementados. A configuração permanece `OAUTH_CLIENT_CREDENTIALS_ENABLED=false` por padrão até os aceites acima.
