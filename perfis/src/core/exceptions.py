"""Erros de negócio compartilhados pelos módulos.

Os services levantam estas exceções e o `main.py` converte cada uma na
resposta HTTP certa, para que nenhum service precise lidar com HTTP.
"""


class PerfilNaoEncontrado(Exception):
    def __init__(self, mensagem: str = "Perfil não encontrado"):
        super().__init__(mensagem)
        self.mensagem = mensagem


class DadoDuplicado(Exception):
    def __init__(self, mensagem: str = "CPF/CNPJ, e-mail ou placa já cadastrado"):
        super().__init__(mensagem)
        self.mensagem = mensagem


class AcaoNaoPermitida(Exception):
    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class DadosInvalidos(Exception):
    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem
