# Rascunhos de issues — Auth (escopo do Marcelo)

Os textos abaixo usam a proposta escolhida por Marcelo como contrato-base, para circular e validar com as equipes consumidoras. Ainda não foram publicados: não há integração de issues do GitHub nem GitHub CLI autenticado nesta sessão.

## Issue 1 — [Auth] Alinhar contrato OAuth 2.0 e contrato de tokens com os consumidores

**Responsável sugerido:** Marcelo, com Vitor e responsáveis por Perfis, Autorização/RBAC, Catálogo e Financeiro.

### Objetivo

Registrar e publicar o fluxo OAuth 2.0 e os contratos escolhidos para emissão, renovação, validação e revogação, antes de conectar o login e os serviços consumidores.

### Tarefas

- Usar Authorization Code com PKCE para usuários interativos e Client Credentials para consumidores máquina a máquina, com credenciais de serviço separadas por consumidor. Não usar Resource Owner Password Credentials nem tratar a emissão isolada de JWT como implementação OAuth 2.0.
- Registrar endpoints, método de autenticação do cliente, corpos de requisição/resposta, erros e convenção de rotas/idioma.
- Assinar access tokens JWT com RS256 e publicar chaves públicas em `/.well-known/jwks.json`, alinhando a validação com Autorização/RBAC e consumidores.
- Fixar claims e seus nomes: `sub` como UUID `conta_id`, `role` com os valores `CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`, além de `iss`, `aud`, `iat`, `exp` e `jti`. O papel vem da associação autoritativa do serviço de Autorização/RBAC, não é inferido apenas do cadastro de Perfil.
- Definir access token com validade de 25 minutos, refresh token rotativo, revogação/logout e comportamento para conta não ativa; acordar ainda a duração do refresh token.
- Definir o papel do RabbitMQ: quais eventos assíncronos serão publicados/consumidos e como lidar com repetição/indisponibilidade. O contrato HTTP OAuth precisa devolver a resposta e os tokens de forma síncrona; a mensagem não pode ser a única fonte de verdade para autorizar, renovar ou confirmar revogação.
- Documentar o contrato acordado no OpenAPI/README e comunicá-lo às equipes consumidoras.
- Registrar a divisão de responsabilidades no cadastro: Perfis implementa o cadastro de todos os tipos, inclusive `CLIENTE`, e valida o CPF quanto a formato/dígitos verificadores sem comprovação externa; Auth recebe somente a solicitação interna de criação de credenciais (INT-02), devolve `conta_id` e não guarda dados cadastrais do cliente.
- Para o tipo `CLIENTE`, usar inicialmente os campos cadastrais comuns já definidos para Perfis (`nome`, `cpf`, `email`, `telefone`) e endereço opcional. O perfil nasce `PENDENTE_APROVACAO`; a transição para `ATIVO` é responsabilidade de Perfis e sua regra de aprovação precisa ficar documentada por aquela equipe.

### Critérios de aceite

- O contrato documenta Authorization Code + PKCE para usuários, Client Credentials para serviços, endpoints, integração com o login de Vitor e erros HTTP.
- Catálogo, Financeiro e Autorização/RBAC têm contrato documentado para RS256/JWKS, `sub`, `role` e valores dos papéis.
- Estão definidos duração/rotação de refresh, revogação e o que ocorre durante indisponibilidade de Perfis ou RabbitMQ.
- O contrato especifica que tokens/segredos não aparecem em logs e que eventos não carregam senha, hash de senha, access token ou refresh token.

### Dependências

- Alinhamento com Vitor sobre a chamada do emissor de tokens a partir da issue **[Auth] Implementar login com validação de credenciais e status da conta (#8)**.
- Equipe de Autorização/RBAC: fornecer a associação autoritativa de papel por `conta_id` via INT-03; API/contrato ainda não está implementado neste checkout.
- Aceite dos consumidores externos sobre o contrato de validação JWT/JWKS.

### Testes e qualidade

- Como issue de contrato, validar os exemplos de sucesso/erro com testes de contrato ou mocks compartilhados pelos consumidores.
- Meta do projeto: cobertura agregada mínima de **80%** no relatório/CI do conjunto dos serviços. O documento de requisitos também estabelece pelo menos **75% por serviço**; manter ambos os indicadores explícitos no pipeline.

### Entrega

Criar branch a partir de `develop` atualizada e abrir PR para `develop`, com contrato e exemplos documentados.

---

## Issue 2 — [Auth] Emitir, assinar e renovar tokens OAuth 2.0/JWT

**Responsável sugerido:** Marcelo.

### Objetivo

Implementar a emissão de access tokens assinados e o refresh de sessão, integrado ao login de Auth e ao status cadastral de Perfis.

### Tarefas

- Implementar o endpoint/fluxo OAuth 2.0 acordado na issue de contrato, consumindo o resultado de validação de credenciais de Vitor (#8) para emitir tokens somente após sucesso.
- Assinar access tokens com RS256 e publicar as chaves públicas em JWKS, incluindo `kid` e procedimento de rotação de chaves.
- Incluir claims acordadas, no mínimo `sub` com o `conta_id` UUID, papel emitido a partir da fonte definida com RBAC, `iss`, `aud`, `iat`, `exp` e `jti`.
- Emitir `role` somente com um dos valores atuais de Perfis: `CLIENTE`, `LOJA`, `ENTREGADOR` ou `ADMIN`; validar o papel contra a associação do usuário em Autorização/RBAC.
- Aplicar validade de **25 minutos** ao access token, conforme RF001/RNF-02 do documento de requisitos.
- Implementar refresh conforme a política acordada, incluindo validação, rotação/uso único e persistência segura do estado necessário para múltiplas instâncias.
- Consultar o status da conta em Perfis também no refresh (INT-01). Se não estiver `ATIVO`, revogar a sessão e responder `403`; se Perfis estiver indisponível, responder `503` sem emitir tokens.
- Retornar os tokens e erros no contrato acordado; nunca emitir token em falha de credenciais, status, refresh ou dependência.
- Não registrar senhas, hashes, access tokens ou refresh tokens em logs. Persistir refresh tokens de forma segura para possibilitar rotação, uso único e revogação entre instâncias.

### Critérios de aceite

- Login com credenciais válidas e conta `ATIVO` retorna tokens conforme o contrato e access token com validade de 25 minutos.
- Conta pendente/suspensa não recebe tokens; os erros seguem o contrato e não expõem se o e-mail existe.
- Refresh válido emite novo access token e aplica rotação/reutilização conforme contrato.
- Refresh de conta suspensa retorna `403` e revoga a sessão; status pendente também não gera tokens.
- Timeout/indisponibilidade de Perfis retorna `503` sem emitir ou renovar tokens.
- A chave pública/JWKS valida tokens assinados e consumidores conseguem validar `iss`, `aud`, assinatura, tipo do token e expiração localmente.
- Duas instâncias do Auth conseguem renovar a mesma sessão com estado compartilhado, sem depender de memória local ou afinidade de sessão.
- OpenAPI e documentação descrevem fluxo, claims, erros, chaves e configuração sem segredos reais.

### Dependências

- Issue 1 deste conjunto: contrato OAuth 2.0, claims, chaves e política de refresh aprovados.
- **[Auth] Implementar login com validação de credenciais e status da conta (#8)**, de Vitor: deve expor resultado confiável de autenticação para o emissor.
- INT-01: Perfis já armazena `status` e possui consulta administrativa de perfil, mas a operação interna de consulta por `conta_id`, com contrato e autenticação serviço a serviço, ainda precisa ser alinhada/implementada para login e refresh.
- INT-03/serviço de Autorização para fonte do papel; hoje a implementação/contrato ainda não está demonstrado neste checkout.
- Perfis precisa alinhar o vínculo da identidade: hoje `Perfil.id` é gerado por Perfis e a credencial Auth usa `conta_id`; INT-02 deve garantir o mesmo UUID ou definir o mapeamento entre eles.
- O cadastro de cliente e seu schema pertencem ao serviço Perfis, junto aos cadastros de loja, entregador e admin; não fazem parte do módulo Auth. Auth mantém apenas credenciais e a emissão/validação de tokens.
- O código atual tem criação separada para loja (`POST /lojas`), entregador (`POST /entregadores`) e admin (`POST /admin/admins`); não encontrei rota de criação de cliente registrada no router. Os schemas de loja e entregador recebem senha, e Perfis ainda persiste `perfis.senha`. A migração para Auth deve cobrir os quatro tipos e remover a senha da persistência de Perfis em coordenação com Vitor/Perfis.
- Persistência compartilhada PostgreSQL/Supabase disponível para estado de refresh e múltiplas instâncias. O Auth já tem banco/migração de credenciais, mas ainda não há tabela/estratégia de sessões ou refresh tokens.
- Decisão de infraestrutura/contrato RabbitMQ. A emissão e a renovação síncronas não podem depender de confirmação assíncrona para devolver tokens.

### Testes e qualidade

- Testar emissão, assinatura, claims, validade/expiração com relógio controlado, renovação, rotação/reuso, conta não ativa, timeout/503 e ausência de emissão em falhas.
- Testar duas instâncias usando estado compartilhado e validar token/JWKS com consumidor simulado.
- Meta do projeto: cobertura agregada mínima de **80%** no CI. A cobertura de Auth deve permanecer ao menos **75% por serviço**, conforme o PDF (preferencialmente configurar o pipeline para reportar os dois números).

### Entrega

Branch por issue a partir de `develop` atualizada, PR para `develop`, testes e documentação. Recuperação de senha fica fora deste escopo.

---

## Issue 3 — [Auth] Implementar logout e revogação persistente de sessões

**Responsável sugerido:** Marcelo.

### Objetivo

Permitir logout/revogação de sessão e garantir que tokens revogados deixem de ser aceitos por Autorização/RBAC e pelos consumidores, inclusive entre instâncias.

### Tarefas

- Implementar endpoint OAuth de revogação para o logout, conforme RFC 7009, revogando o refresh token e a sessão associada segundo a política definida.
- Definir se logout revoga a sessão atual ou toda a família de refresh tokens e aplicar a política definida.
- Persistir revogações/estado da família de refresh tokens em PostgreSQL compartilhado, com escrita atômica e sobrevivência a reinícios; não depender de blacklist em memória.
- Garantir que refresh token revogado/reutilizado não gere nova sessão ou tokens.
- Atender INT-05: token inválido, expirado ou revogado deve resultar em `401` na validação usada por Autorização/RBAC. Disponibilizar a verificação online ou contrato de validação compatível com a estratégia de tokens e revogação aprovada.
- Se RabbitMQ for usado para notificar revogações ou invalidar caches, publicar evento sem tokens/segredos e manter a persistência síncrona como fonte autoritativa; definir idempotência, repetição e comportamento em falha do broker.
- Padronizar sucesso/erros em português e formato comum `{"erro": true, "mensagem": "..."}`; não registrar tokens.

### Critérios de aceite

- Logout bem-sucedido revoga a sessão conforme a política documentada; repetir a operação tem comportamento idempotente ou erro definido pelo contrato.
- Refresh token revogado não pode renovar sessão, inclusive após reinício e em outra instância do Auth.
- Validação de token revogado retorna `401` para INT-05/Autorização.
- Falha de persistência não é reportada como logout concluído; falha de RabbitMQ não permite revalidar uma sessão que o estado persistido já revogou.
- Teste de integração comprova revogação observada por duas instâncias, sem afinidade de sessão.
- Logs e respostas não incluem tokens, segredos ou dados pessoais desnecessários.

### Dependências

- Issue 1 deste conjunto: contrato OAuth 2.0, semântica de logout, validação e eventos acordados.
- Issue 2 deste conjunto: emissão/refresh e identificador/estado de sessão definidos e persistidos.
- Equipe de Perfis: INT-01 precisa expor consulta de status apropriada para login e refresh; hoje o status existe no modelo e há rota administrativa, mas não foi encontrado contrato de integração Auth↔Perfis.
- Equipe de Autorização/RBAC: integração INT-05 precisa consumir a validação/revogação (ou JWKS mais mecanismo definido para revogação); o serviço local está apenas como esqueleto neste checkout.
- Infraestrutura e contrato RabbitMQ, caso a equipe exija notificação assíncrona de revogação. Não é necessário para a autoridade síncrona se consumidores consultarem o estado persistido/endpoint definido.

### Testes e qualidade

- Testar logout, idempotência, refresh após logout, invalidação após reinício, concorrência, duas instâncias e indisponibilidade de PostgreSQL/RabbitMQ.
- Usar relógio controlado para limites temporais e cobrir os fluxos de integração com substitutos controlados e ao menos uma execução entre serviços reais antes de encerrar a issue.
- Meta do projeto: cobertura agregada mínima de **80%** no CI. A cobertura de Auth deve permanecer ao menos **75% por serviço**, conforme o PDF, com relatórios que identifiquem ambos os limites.

### Entrega

Branch por issue a partir de `develop` atualizada, PR para `develop`, testes de integração e documentação OpenAPI/README.

