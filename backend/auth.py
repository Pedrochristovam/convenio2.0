"""
Acesso por usuário e senha.

Os usuários vêm de APP_USERS ("ana:senha1,joao:senha2"). Sem APP_USERS o login
fica desligado (uso local). O token é assinado com APP_SECRET; se ele mudar ou
não estiver definido, os tokens emitidos deixam de valer quando o servidor reinicia.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, Optional

_segredo_volatil = secrets.token_hex(32)


def usuarios() -> Dict[str, str]:
    out = {}
    for par in (os.getenv("APP_USERS") or "").split(","):
        nome, _, senha = par.strip().partition(":")
        if nome.strip() and senha:
            out[nome.strip().lower()] = senha
    return out


def ativo() -> bool:
    return bool(usuarios())


def _segredo() -> bytes:
    return (os.getenv("APP_SECRET") or _segredo_volatil).encode()


def _assinar(dados: str) -> str:
    return hmac.new(_segredo(), dados.encode(), hashlib.sha256).hexdigest()


def gerar_token(usuario: str) -> str:
    validade = int(time.time()) + int(os.getenv("APP_TOKEN_HORAS", "12")) * 3600
    dados = f"{usuario}:{validade}"
    return base64.urlsafe_b64encode(dados.encode()).decode().rstrip("=") + "." + _assinar(dados)


def validar(token: Optional[str]) -> Optional[str]:
    """Usuário dono do token, ou None se inválido/expirado."""
    if not token or "." not in token:
        return None
    corpo, assinatura = token.rsplit(".", 1)
    try:
        dados = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)).decode()
        usuario, validade = dados.rsplit(":", 1)
        if int(validade) < time.time():
            return None
    except Exception:
        return None
    if not hmac.compare_digest(assinatura, _assinar(dados)) or usuario not in usuarios():
        return None
    return usuario


def autenticar(usuario: str, senha: str) -> Optional[str]:
    nome = (usuario or "").strip().lower()
    esperada = usuarios().get(nome)
    if esperada is None or not hmac.compare_digest(esperada.encode(), (senha or "").encode()):
        return None
    return gerar_token(nome)


def em_producao() -> bool:
    return bool(os.getenv("RENDER"))


def pode_limpar_banco() -> bool:
    return not em_producao() or os.getenv("PERMITIR_LIMPAR_BANCO") == "1"
