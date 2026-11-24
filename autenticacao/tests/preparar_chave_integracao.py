"""Gera uma chave efêmera exclusivamente para a pilha local de integração."""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

caminho = Path(os.environ["JWT_PRIVATE_KEY_PATH"])
caminho.parent.mkdir(parents=True, exist_ok=True)
if not caminho.exists():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    caminho.write_bytes(
        chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
