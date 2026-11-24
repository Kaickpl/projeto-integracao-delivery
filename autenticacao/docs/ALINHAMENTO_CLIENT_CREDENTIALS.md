# Proposta de contrato — Client Credentials

**Estado:** o fluxo foi implementado atrás de configuração desativada por padrão. Os parâmetros abaixo continuam sendo uma proposta para aceite do Financeiro, Catálogo e Autorização/RBAC; não habilitar em ambientes compartilhados nem anunciar a consumidores antes desse aceite.

## Divisão de responsabilidades

- **Auth** registra cada cliente de serviço, autentica sua credencial, guarda somente o hash do segredo, controla ativação/rotação e emite access tokens.
- **Autorização/RBAC** é a fonte autoritativa das audiências e escopos que cada `client_id` pode usar. Auth consulta o RBAC antes de emitir um token e não mantém uma cópia independente dessas permissões.
- **Consumidores** validam assinatura e claims localmente com JWKS e aplicam os escopos nas rotas protegidas.
- Credenciais internas já configuradas entre Auth, Perfis e RBAC permanecem separadas. A migração para OAuth M2M é gradual e só acontece quando cada consumidor estiver pronto.

## Fluxo proposto

1. O consumidor envia `POST /v1/oauth/tokens` com `grant_type=client_credentials`, autenticação HTTP Basic (`client_secret_basic`) e os parâmetros de escopo/recurso acordados.
2. Auth valida o cliente, consulta o RBAC para autorizar a combinação pedida e emite somente um access token RS256.
3. O consumidor valida localmente assinatura, `kid`, `typ`, `iss`, `aud`, `exp` e escopo com o JWKS publicado pelo Auth.
4. O consumidor solicita outro access token quando o atual expirar. Client Credentials não emite refresh token.

## Claims propostas

- `iss`, `aud`, `iat`, `exp`, `jti`, `client_id`, `sub` e `scope`.
- `sub` identifica o cliente de serviço, sem dados pessoais. Proposta de formato: `servico:<client_id>`; confirmar com RBAC e consumidores.
- `aud` identifica o serviço/recurso de destino autorizado pelo RBAC.
- `scope` usa a representação OAuth de escopos separados por espaço; nomes concretos serão definidos por consumidor com RBAC.
- Não incluir `role`, `sid`, dados cadastrais ou claims de usuário.
- Validade proposta: **10 minutos**. O cliente desativado não pode obter novos tokens; tokens já emitidos permanecem válidos até `exp`. Se o grupo exigir revogação imediata, consumidores precisam consultar validação online, pois JWKS sozinho só valida assinatura.

## Segredos e ciclo de vida

- Gerar um segredo forte e independente por consumidor; armazenar somente hash Argon2id no Auth.
- Mostrar o segredo apenas uma vez no provisionamento; nunca incluí-lo em respostas subsequentes, logs, eventos ou exemplos versionados.
- Provisionamento, rotação e desativação devem ser operações administrativas controladas, não uma rota pública de autoatendimento.
- Desativar um cliente bloqueia novas emissões. Rotação aceita um novo segredo sem compartilhar credenciais entre consumidores; a janela de sobreposição deve ser acordada.
- A persistência e o estado são compartilhados pelo PostgreSQL. RabbitMQ não autoriza nem revoga tokens; eventos de auditoria, se contratados, não incluem segredo ou token.

## Decisões pendentes para aceite

- Confirmar `client_secret_basic` com Financeiro, Catálogo e Autorização/RBAC.
- Escolher o parâmetro de destino: `resource` conforme RFC 8707 ou outro contrato já usado pelos consumidores.
- Confirmar o formato de `sub`, validade de 10 minutos, semântica de desativação e se a validade curta atende à revogação desejada.
- RBAC definir nomes de escopo, audiências e a operação autenticada que Auth consulta durante a emissão.
- Definir o procedimento operacional para provisionar, entregar, rotacionar e desativar cada segredo.
- Contratar um endpoint/rota de consumidor protegido por escopo para o teste de integração real; não criar exemplos de permissões como se já estivessem aprovados.

## Implementação disponível para validação isolada

- `OAUTH_CLIENT_CREDENTIALS_ENABLED=false` por padrão; ativado somente na composição local descartável para testes.
- Auth guarda hash Argon2id de segredo, permite criar/rotacionar/desativar por CLI e consulta os escopos no RBAC antes de emitir.
- RBAC guarda as permissões em sua própria migração e oferece consulta autenticada pelo Auth. A validação de consumidor usa JWKS e confirma os escopos pedidos com o token e com a política atual.
- O teste ponta a ponta usa somente `delivery_teste`, em localhost, e não migra ou escreve no Supabase compartilhado.
- A validade de 10 minutos limita o uso de tokens já emitidos depois da rotação/desativação do cliente; consumidores locais por JWKS só os rejeitarão ao expirar. Para rejeição imediata, usar a validação de escopos no RBAC por operação protegida.

Metadados OAuth continuam anunciando apenas grants implementados. `client_credentials` só será publicado quando o contrato estiver aceito e o fluxo implementado/testado.
