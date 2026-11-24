# Rotação das chaves RS256

Cada instância Auth de um mesmo ambiente deve assinar com a mesma chave privada ativa, o mesmo `JWT_KEY_ID` e a mesma lista de chaves públicas anteriores. A chave privada deve ficar em um gerenciador de segredos ou volume protegido e nunca entrar no Git.

## Procedimento

1. Gere um novo par RSA de pelo menos 2048 bits fora do repositório. Exemplo com OpenSSL:

   ```powershell
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out chave-privada-nova.pem
   openssl pkey -in chave-privada-nova.pem -pubout -out chave-publica-nova.pem
   ```

2. Copie somente a chave pública atualmente ativa para `JWT_OLD_PUBLIC_KEYS_DIR`, usando o `kid` atual como nome, por exemplo `anteriores/identidade-producao-1.pem`. Não copie a chave privada antiga para esse diretório.
3. Instale a nova chave privada em todas as instâncias Auth e configure o mesmo `JWT_PRIVATE_KEY_PATH` e `JWT_KEY_ID` novo em cada uma.
4. Publique a nova chave pública e confira `GET /.well-known/jwks.json`: a resposta deve conter o novo `kid` ativo e o `kid` anterior.
5. Reinicie as instâncias Auth de modo coordenado e confirme que tokens novos usam o novo `kid`. Valide assinatura e `iss`/`aud` com o JWKS publicado.
6. Mantenha as chaves públicas antigas no JWKS por pelo menos o maior prazo de access token (25 minutos), mais a tolerância de relógio e o tempo de cache JWKS dos consumidores. Remova uma chave antiga somente depois desse período.
7. Repita o processo na próxima rotação, mantendo cada chave pública antiga em arquivo separado pelo respectivo `kid`.

O cache da chave privada do processo é invalidado quando o arquivo muda, mas trocar configuração exige reiniciar todas as instâncias para evitar emissores divergentes. Se uma chave privada for comprometida, remova sua chave pública do JWKS imediatamente; consumidores que atualizarem o JWKS rejeitarão access tokens assinados por ela. Revise as sessões afetadas e revogue-as conforme o procedimento de resposta a incidente.

O teste `test_jwks_publica_chave_atual_e_chave_anterior` verifica que a chave atual e as anteriores são publicadas sem material privado. A troca operacional em produção deve ser coordenada com os consumidores e com a distribuição segura das chaves.
