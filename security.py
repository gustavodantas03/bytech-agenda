"""Funções de hash e verificação de senha.

Isolado em módulo próprio (sem depender de core.py ou database.py) para
poder ser usado tanto nas rotas quanto no seed inicial do banco de dados
sem criar import circular.
"""

from werkzeug.security import check_password_hash, generate_password_hash


def eh_hash_de_senha(valor):
    """Identifica se o valor já é um hash gerado por este sistema
    (em vez de uma senha antiga salva em texto puro)."""

    return bool(valor) and str(valor).startswith(("pbkdf2:", "scrypt:", "argon2:"))


def gerar_hash_senha(senha_texto_plano):
    """Gera o hash seguro de uma senha para ser salvo no banco."""

    return generate_password_hash(senha_texto_plano, method="pbkdf2:sha256")


def senha_confere(senha_texto_plano, valor_armazenado):
    """Confere a senha digitada com o valor salvo no banco.

    Aceita tanto hashes gerados por este sistema quanto senhas antigas
    salvas em texto puro (compatibilidade com contas já cadastradas antes
    desta correção). Contas em texto puro são migradas automaticamente
    para hash no próximo login bem-sucedido, pela própria rota de login.
    """

    if not senha_texto_plano or not valor_armazenado:
        return False
    if eh_hash_de_senha(valor_armazenado):
        try:
            return check_password_hash(valor_armazenado, senha_texto_plano)
        except ValueError:
            return False
    return valor_armazenado == senha_texto_plano
