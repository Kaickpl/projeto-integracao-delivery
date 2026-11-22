"""Erros de negócio compartilhados pelos módulos.

Os services levantam estas exceções e o `main.py` converte cada uma na
resposta HTTP certa, para que nenhum service precise lidar com HTTP. Cada
erro diz o próprio código HTTP e tem uma mensagem padrão.
"""


class ErroDeNegocio(Exception):
    status_code: int = 400
    mensagem_padrao: str = "Requisição inválida"

    def __init__(self, mensagem: str | None = None):
        self.mensagem = mensagem or self.mensagem_padrao
        super().__init__(self.mensagem)


class PerfilNaoEncontrado(ErroDeNegocio):
    status_code = 404
    mensagem_padrao = "Perfil não encontrado"


class DadoDuplicado(ErroDeNegocio):
    status_code = 409
    mensagem_padrao = "CPF/CNPJ, e-mail ou placa já cadastrado"


class AcaoNaoPermitida(ErroDeNegocio):
    status_code = 409
    mensagem_padrao = "Ação não permitida"


class DadosInvalidos(ErroDeNegocio):
    status_code = 422
    mensagem_padrao = "Dados inválidos"


class CepNaoEncontrado(ErroDeNegocio):
    status_code = 404
    mensagem_padrao = "CEP não encontrado"


class ServicoIndisponivel(ErroDeNegocio):
    status_code = 503
    mensagem_padrao = "Serviço indisponível no momento"
