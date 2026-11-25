# Proposta de contrato — Client Credentials

**Estado:** Client Credentials está implementado, mas desativado por padrão. Em 25/11/2026, o Financeiro aceitou validação local por JWKS para as chamadas M2M de leitura de perfil e validade de 10 minutos. Para a integração local, Identidade adotou `resource`/`aud=http://perfis:8002` e `scope=perfis:ler`. URLs de implantação e provisionamento do cliente real permanecem pendentes.

## Divisão de responsabilidades

- **Auth** registra cada cliente de serviço, autentica sua credencial, guarda somente o hash do segredo, controla ativação/rotação e emite access tokens.
- **Autorização/RBAC** é a fonte autoritativa das audiências e escopos que cada `client_id` pode usar. Auth consulta o RBAC antes de emitir um token e não mantém uma cópia independente dessas permissões.
- **Consumidores** validam assinatura e claims localmente com JWKS e aplicam os escopos nas rotas protegidas. Para o worker do Financeiro que lerá perfil, não é necessária consulta ao RBAC a cada requisição.
- Credenciais internas já configuradas entre Auth, Perfis e RBAC permanecem separadas. A migração para OAuth M2M é gradual e só acontece quando cada consumidor estiver pronto.

## Fluxo proposto

1. O consumidor envia `POST /v1/oauth/tokens` com `grant_type=client_credentials`, autenticação HTTP Basic (`client_secret_basic`) e os parâmetros de escopo/recurso acordados.
2. Auth valida o cliente, consulta o RBAC para autorizar a combinação pedida e emite somente um access token RS256.
3. O consumidor valida localmente assinatura, `kid`, `typ`, `iss`, `aud`, `exp` e escopo com o JWKS publicado pelo Auth. A API de recurso também deve exigir a audiência e o escopo correspondentes à operação.
4. O consumidor solicita outro access token quando o atual expirar. Client Credentials não emite refresh token.

## Claims propostas

- `iss`, `aud`, `iat`, `exp`, `jti`, `client_id`, `sub` e `scope`.
- `sub` identifica o cliente de serviço, sem dados pessoais: `servico:<client_id>`.
- `aud` identifica o serviço/recurso de destino autorizado pelo RBAC.
- `scope` usa a representação OAuth de escopos separados por espaço. Para leitura do perfil pelo worker do Financeiro, o escopo adotado é `perfis:ler`.
- Não incluir `role`, `sid`, dados cadastrais ou claims de usuário.
- Para o worker do Financeiro, validade acordada: **10 minutos** (`OAUTH_SERVICE_TOKEN_MINUTES=10` no ambiente). O cliente desativado ou a permissão removida impedem novas emissões, mas tokens já emitidos podem continuar aceitos localmente até `exp` — no máximo 10 minutos. JWKS valida assinatura e claims, não consulta o estado atual do RBAC.
- A validação online `POST /v1/tokens/servico/validar` continua disponível para consumidores ou operações que precisem aplicar imediatamente alterações de política. Ela não é obrigatória a cada chamada M2M do Financeiro no cenário acordado de leitura de perfil.

## Segredos e ciclo de vida

- Gerar um segredo forte e independente por consumidor; armazenar somente hash Argon2id no Auth.
- Mostrar o segredo apenas uma vez no provisionamento; nunca incluí-lo em respostas subsequentes, logs, eventos ou exemplos versionados.
- Provisionamento, rotação e desativação devem ser operações administrativas controladas, não uma rota pública de autoatendimento.
- Desativar um cliente bloqueia novas emissões. Rotação aceita um novo segredo sem compartilhar credenciais entre consumidores; a janela de sobreposição deve ser acordada.
- A persistência e o estado são compartilhados pelo PostgreSQL. RabbitMQ não participa do fluxo implementado: não autoriza, emite nem revoga tokens. Ainda não há evento ou contrato de mensageria definido; qualquer evento futuro será apenas complementar e não carregará segredo ou token.

## Decisões pendentes para aceite

- `client_secret_basic`, `resource` como audiência, `sub=servico:<client_id>` e validade de 10 minutos foram aceitos pelo Financeiro para seu worker; confirmar compatibilidade com os demais consumidores antes de habilitação geral.
- `perfis:ler` e `http://perfis:8002` estão configurados para a integração local. No ambiente publicado, o valor exato de `resource`/`aud` precisa ser definido a partir da URL real de Perfis e configurado de forma idêntica em Auth/RBAC e Perfis.
- Auth consulta o RBAC ao emitir o token. O worker do Financeiro valida chamadas localmente por JWKS e aceita a janela máxima de 10 minutos para efeito de desativação/remoção de permissão.
- RBAC mantém a consulta de escopos usada pelo Auth durante a emissão e o endpoint de validação online para casos que exijam aplicação imediata da política.
- Definir o procedimento operacional para provisionar, entregar, rotacionar e desativar cada segredo.
- Contratar um endpoint/rota de consumidor protegido por escopo para o teste de integração real; não criar exemplos de permissões como se já estivessem aprovados.

## Implementação disponível para validação isolada

- `OAUTH_CLIENT_CREDENTIALS_ENABLED=false` por padrão; ativado somente na composição local descartável para testes.
- Auth guarda hash Argon2id de segredo, permite criar/rotacionar/desativar por CLI e consulta os escopos no RBAC antes de emitir.
- RBAC guarda as permissões em sua própria migração e oferece consulta autenticada pelo Auth durante a emissão. O endpoint RBAC de validação online também compara escopos com a política atual; o Financeiro não o chamará por requisição no fluxo acordado.
- O teste ponta a ponta usa somente `delivery_teste`, em localhost, e não migra ou escreve no Supabase compartilhado.
- Para o worker do Financeiro, a validade de 10 minutos limita o uso de tokens já emitidos depois da rotação/desativação do cliente ou remoção de escopo. A validação local por JWKS só detecta expiração; para rejeição imediata, uma operação pode consultar a validação online do RBAC.

## Estado da integração com Financeiro

- Implementada em Perfis a rota `GET /v1/perfis/{id}`. Exige JWT M2M RS256 validado localmente por JWKS, emissor configurado, audiência `PERFIS_OAUTH_AUDIENCE` e escopo `PERFIS_READ_SCOPE`; retorna somente `id`, `nome` e `email`.
- Cadastro de usuário em Perfis agora requer `Idempotency-Key` e pode ser retomado com a mesma chave, evitando perfil sem credencial/papel após falha parcial; Perfis não persiste senha.
- Para integração local, `iss=http://127.0.0.1:18001`, `aud/resource=http://perfis:8002` e `scope=perfis:ler`. Publicar os valores equivalentes do ambiente compartilhado quando a implantação existir.
- O fluxo Authorization Code + PKCE de usuário foi testado localmente no Postman com conta ativa; o callback do Postman substituiu temporariamente o callback local e deve ser restaurado após o teste. Não há grant de senha.
- Provisionar o cliente M2M real e conceder a permissão no RBAC somente depois de definir a audiência publicada. Entregar o segredo gerado pelo Auth ao Financeiro por canal privado, nunca em arquivo versionado ou issue.

Para testes descartáveis, a composição cria `worker-notificacoes-financeiro` com um segredo fixo de teste local e a permissão `http://perfis:8002` + `perfis:ler`. Esse segredo não é válido fora da composição local e não deve ser reutilizado.

Metadados OAuth continuam anunciando apenas grants implementados. `client_credentials` só será publicado quando o contrato estiver aceito e o fluxo implementado/testado.
