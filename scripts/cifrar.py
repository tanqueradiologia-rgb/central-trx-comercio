#!/usr/bin/env python3
"""Cifra site/dados_comercio.js em site/central.enc, lido pela página com a senha
da equipe do comércio (segredo CENTRAL_SENHA deste repositório, separado da senha
da Central de laudos). Mesmo formato da Central TRX: PBKDF2-SHA256 + AES-256-GCM.
O arquivo em claro é apagado para o Pages publicar só o pacote cifrado."""
import base64, json, os, sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(RAIZ, "site")
ITER = 150_000

senha = os.environ.get("CENTRAL_SENHA", "")
if len(senha) < 8:
    print("CENTRAL_SENHA ausente ou com menos de 8 caracteres: nada foi cifrado.", file=sys.stderr)
    sys.exit(1)

claro = open(os.path.join(SITE, "dados_comercio.js"), "rb").read()
salt, iv = os.urandom(16), os.urandom(12)
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER)
ct = AESGCM(kdf.derive(senha.encode())).encrypt(iv, claro, None)
b64 = lambda b: base64.b64encode(b).decode()
saida = {"v": 1, "kdf": "pbkdf2-sha256", "iter": ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}
open(os.path.join(SITE, "central.enc"), "w", encoding="utf-8").write(json.dumps(saida))
os.remove(os.path.join(SITE, "dados_comercio.js"))
print("central.enc gerado:", len(claro), "bytes em claro,", len(ct), "bytes cifrados.")
