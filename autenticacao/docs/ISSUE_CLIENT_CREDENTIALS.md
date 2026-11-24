# [Auth] Implementar OAuth 2.0 Client Credentials para serviços consumidores

**Status:** rascunho para publicar como nova issue.
**Responsável sugerido:** Marcelo.

## Objetivo

Permitir que serviços consumidores, como workers do Financeiro, obtenham tokens OAuth 2.0 próprios sem usuário interativo, com credencial individual, escopos e validação local por JWKS.

## Tarefas

- Implementar `grant_type=client_credentials` em `POST /v1/oauth/tokens`, mantendo Authorization Code + PKCE para usuários.
- Registrar clientes de serviço com `client_id`, segredo armazenado como hash, estado ativo/revogado e escopos permitidos. Nunca retornar ou registrar segredos depois da criação.
- Autenticar clientes conforme contrato (preferencialmente `client_secret_basic`; avaliar `client_secret_post` apenas se consumidores exigirem).
- Emitir access token RS256 de curta duração, sem refresh token, com `iss`, `aud`, `iat`, `exp`, `jti`, `client_id`, `sub` de serviço e `scope`; não emitir `role` de usuário.
- Validar audiência/escopos pedidos contra as permissões do cliente e negar escopo não concedido.
- Definir como tokens de serviço serão revogados/limitados e como RBAC/serviços consumidores autorizam cada escopo.
- Atualizar `/.well-known/oauth-authorization-server`, OpenAPI e README para anunciar o grant somente quando disponível.
- Manter credenciais de serviço existentes entre Auth, Perfis e RBAC separadas e com permissões mínimas; planejar migração sem indisponibilidade.
- Garantir que RabbitMQ não seja autoridade para emitir ou revogar tokens de serviço; eventos, se definidos, não carregam segredo ou token.

## Critérios de aceite

- Cliente ativo com segredo válido recebe token de serviço conforme contrato; segredo incorreto, cliente desativado e escopo não autorizado não recebem token.
- Token de serviço é validável por RS256/JWKS e possui audiência, validade, `client_id`, `sub` de serviço e escopos esperados; não contém claims pessoais nem `role` de usuário.
- Não é emitido refresh token para Client Credentials.
- Segredos persistidos somente como hash e ausentes de logs/respostas subsequentes.
- Credenciais e permissões são isoladas por consumidor; revogar um cliente não afeta os demais.
- Teste real demonstra chamada do worker do Financeiro (ou consumidor simulado) usando o token para uma rota autorizada e rejeição em rota/escopo não autorizado.
- Metadados OAuth passam a listar `client_credentials` somente após a implementação e o contrato estarem aprovados.

## Dependências

- Contrato OAuth da issue #19 e aceite do Financeiro, Catálogo e Autorização/RBAC para método de autenticação, `aud`, escopos e `sub` de serviço.
- Serviço de Autorização/RBAC: política autoritativa de escopos/permissões de máquina a máquina; hoje o RBAC deste checkout associa somente papéis de conta.
- Persistência PostgreSQL e migração controlada para clientes, hashes de segredo e escopos.
- Definição de processo seguro para criar, distribuir, rotacionar e revogar segredos por consumidor.

## Testes e qualidade

- Testar credencial correta/incorreta, cliente inativo, escopos válidos/negados, audiência, validade, assinatura/JWKS e ausência de refresh token.
- Testar hash de segredo, rotação/revogação de credenciais, concorrência e persistência após reinício.
- Fazer teste de contrato com consumidor simulado e integração real com pelo menos um serviço da turma.
- Cobertura mínima de 75% no Auth e contribuição para a cobertura agregada mínima de 80% do projeto, conforme CI e requisitos.

## Entrega

Branch da issue a partir de `develop` atualizada; PR destinado a `develop`, com migração, testes, OpenAPI e documentação.
