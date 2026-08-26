# Schemas canônicos (pydantic v2) — contrato estável que os consumidores usam.
#
# O mesmo shape serve qualquer provider (C6, Sicoob, offline/pyCobrança). Cada
# provider traduz para o seu banco; a resposta volta normalizada.
from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.url_webhook import validar_url_webhook


class Provider(str, Enum):
    """**Caminho** da cobrança — e só isso. Qual banco é o campo `banco`.

    - `on`  — **ON-line**: a API do banco (OAuth2 + mTLS). Exige credencial.
    - `off` — **OFF-line**: a engine [pyCobrança](https://github.com/Maxwbh/pyCobranca)
      no próprio processo. Sem rede, sem convênio.

    Os dois eixos eram um campo só, e o preço aparecia na borda: "qual banco"
    vivia no `provider` quando online e dentro do `account_config` quando
    offline. Separados, trocar de mundo é trocar `provider` — o `banco` fica.

    Os nomes de banco continuam aceitos como **apelido legado** (`c6` = `on` +
    `banco=c6`), para não quebrar quem já integrou. Saem na 3.0.0.
    """

    on = "on"
    off = "off"

    # --- apelidos legados: nome do BANCO no lugar do caminho ----------------
    pycobranca = "pycobranca"   # = off
    c6 = "c6"
    sicoob = "sicoob"
    inter = "inter"
    itau = "itau"


class Banco(str, Enum):
    """Instituição — as 19 tratadas, independente do caminho.

    Os quatro primeiros têm caminho ON (API REST implementada); todos, menos o
    Inter, têm caminho OFF (layout na engine). `GET /bancos` responde a matriz
    exata por introspecção, e a combinação impossível (`on` + banco sem API,
    `off` + Inter) responde `422` dizendo quais existem.
    """

    c6 = "c6"
    sicoob = "sicoob"
    inter = "inter"
    itau = "itau"
    banco_brasil = "banco_brasil"
    bradesco = "bradesco"
    caixa = "caixa"
    santander = "santander"
    sicredi = "sicredi"
    banrisul = "banrisul"
    unicred = "unicred"
    ailos = "ailos"
    banco_brasilia = "banco_brasilia"
    banco_nordeste = "banco_nordeste"
    banestes = "banestes"
    citibank = "citibank"
    credisis = "credisis"
    hsbc = "hsbc"
    safra = "safra"


# Apelido legado (nome do banco no `provider`) → o banco que ele nomeia.
PROVIDER_LEGADO_BANCO: dict[Provider, Banco] = {
    Provider.c6: Banco.c6,
    Provider.sicoob: Banco.sicoob,
    Provider.inter: Banco.inter,
    Provider.itau: Banco.itau,
}


def campo_banco(descricao: str | None = None) -> Any:
    """O eixo `banco` nos corpos de request.

    Existe como fábrica, e não como constante, porque o eixo é o MESMO em toda a
    API: descrito uma vez, ele não diverge modelo a modelo — que é como o
    `provider` acabou significando duas coisas diferentes conforme a rota.
    """
    return Field(
        default=None,
        description=descricao or (
            "**Instituição**: `c6`, `sicoob`, `inter`, `itau`… Use com "
            "`provider=on`. Omitido, o `provider` legado (nome do banco) resolve."
        ),
        examples=["c6"],
    )


def eh_offline(provider: Provider) -> bool:
    """True quando o caminho é a engine offline (pyCobrança)."""
    return provider in (Provider.off, Provider.pycobranca)


class Status(str, Enum):
    """Status normalizado da cobrança (igual para qualquer banco)."""

    registrado = "registrado"
    pendente = "pendente"
    liquidado = "liquidado"
    baixado = "baixado"
    expirado = "expirado"
    erro = "erro"


class Pagador(BaseModel):
    nome: str = Field(description="Nome do pagador", examples=["Fulano de Tal"])
    documento: str = Field(description="CPF ou CNPJ (só dígitos)", examples=["12345678901"])
    endereco: dict[str, Any] | None = Field(default=None, description="Endereço do pagador (opcional)")


class Cobranca(BaseModel):
    valor: Decimal = Field(description="Valor da cobrança", examples=["1000.00"])
    vencimento: date = Field(description="Data de vencimento (ISO)", examples=["2026-07-10"])
    nosso_numero: str | None = Field(
        default=None, description="Nosso número (opcional; o banco pode atribuir)",
        examples=["12345678"])
    seu_numero: str | None = Field(
        default=None, description="Seu número / identificador do emissor (opcional)",
        examples=["PED-2027-0042"])
    pagador: Pagador
    # Encargos da cobranca REGISTRADA (online): repassados a API do banco no
    # formato dela (cada banco define a forma). Para o caminho OFFLINE/CNAB, os
    # encargos vao no `pagamento` da remessa (ver docs/api/encargos.md).
    multa: dict[str, Any] | None = Field(
        default=None,
        description="Multa — repassada à API do banco (forma do banco). "
                    "Ex.: {\"tipo\": \"PERCENTUAL\", \"valor\": 2.0}. "
                    "No CNAB use o `pagamento` da remessa (guia: docs/api/encargos.md).",
        examples=[{"tipo": "PERCENTUAL", "valor": 2.0}])
    juros: dict[str, Any] | None = Field(
        default=None,
        description="Juros/mora — repassado à API do banco (forma do banco).",
        examples=[{"tipo": "MENSAL_PERCENTUAL", "valor": 1.0}])
    desconto: dict[str, Any] | None = Field(
        default=None,
        description="Desconto — repassado à API do banco (forma do banco).",
        examples=[{"tipo": "FIXO", "valor": 50.0, "data_limite": "2027-12-20"}])


class CobrancaIn(BaseModel):
    tenant_id: str = Field(description="Identificador do tenant (resolve credenciais no cofre)", examples=["empresa_123"])
    provider: Provider = Field(
        default=Provider.off,
        description=(
            "**Caminho**: `on` = API do banco · `off` = engine pyCobrança "
            "(default). Nome de banco aqui é apelido legado (`c6` = `on` + "
            "`banco=c6`) e sai na 3.0.0."
        ),
    )
    banco: Banco | None = Field(
        default=None,
        description=(
            "**Instituição**: `c6`, `sicoob`, `inter`, `itau`, `banco_brasil`… "
            "Obrigatório com `provider=on|off`; no caminho `off` ainda é aceito "
            "em `account_config.bank`. Combinação inexistente responde `422` "
            "dizendo quais existem."
        ),
        examples=["c6"],
    )
    account_config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Blob por provider (não unificado de propósito). "
            "c6: {agencia, conta, convenio}; "
            "sicoob: {cooperativa, conta, numeroCliente, codigoModalidade}."
        ),
    )
    cobranca: Cobranca
    credentials: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Credenciais do banco enviadas NO REQUEST (client_id, client_secret, "
            "pfx_base64, pfx_password). Usadas só em memória, nunca persistidas. "
            "Se omitidas, caem no cofre do servidor (VAULT__*)."
        ),
    )

    @field_validator("provider", mode="before")
    @classmethod
    def _provider_vazio_vira_offline(cls, v: Any) -> Any:
        # Contrato: provider vazio/None/omitido roteia para o caminho offline.
        return Provider.off if v in (None, "") else v


class CobrancaOut(BaseModel):
    """Resposta normalizada — mesmo shape para qualquer provider."""

    id: str | None = Field(default=None, description="Id da cobrança no banco (nosso número/txid)")
    status: Status
    linha_digitavel: str | None = None
    codigo_barras: str | None = None
    pix_copia_cola: str | None = Field(default=None, description="PIX copia-e-cola (EMV), quando híbrido")
    pix_vinculado: bool | None = Field(
        default=None,
        description=(
            "O QR **liquida o título**? `true` = Bolepix: QR dinâmico registrado "
            "no banco, e pagar por ele dá baixa. `false` = QR **avulso**, montado "
            "a partir de `chave_pix`: credita a chave e deixa o título **em "
            "aberto** — risco de segunda cobrança ou de protesto de boleto já "
            "pago. `null` = boleto sem PIX. O caminho `on` sempre devolve `true`; "
            "no `off` depende de você mandar `pix_copia_cola` (do banco) ou "
            "`chave_pix`."),
        examples=[True])
    pdf_base64: str | None = Field(default=None, description="PDF do boleto em base64, quando disponível")
    raw: dict[str, Any] | None = Field(default=None, description="Resposta crua do banco (debug)")


# --- PIX dinâmico (só providers REST; o caminho offline não emite cobrança Pix) -


class PixCobranca(BaseModel):
    """Cobrança Pix dinâmica (padrão BACEN: cob imediata ou cobv com vencimento)."""

    valor: Decimal = Field(description="Valor original da cobrança", examples=["10.00"])
    chave: str | None = Field(
        default=None, examples=["7d9f1a52-0c3b-4e21-9f88-1a2b3c4d5e6f"],
        description="Chave Pix do recebedor. Se omitida, usa `account_config.chave_pix`.",
    )
    # O formato é do BACEN e a mensagem da cobv já o CITAVA — sem aplicá-lo:
    # `txid="abc"` e txid com hífen chegavam ao banco e voltavam como `400` dele,
    # traduzido em `422` com `upstream`. Validar aqui recusa antes da ida à rede,
    # com mensagem própria, e vale para cob, cobv e itens de lote de uma vez.
    # Mesmo movimento do `POST /bolepix` na 2.1.1: "recusa com 422 dizendo qual
    # campo falta, antes de chamar o banco".
    txid: str | None = Field(
        default=None,
        pattern=r"^[a-zA-Z0-9]{26,35}$",
        examples=["PEDIDO2027000000000000004242"],
        description="Txid do BACEN: 26 a 35 caracteres, só letras e dígitos. "
                    "Obrigatório na cobv. Na cob é opcional — enviado, é o "
                    "identificador da cobrança (`PUT`); omitido, o banco gera um.",
    )
    expiracao_segundos: int = Field(
        default=3600, description="Validade da cob imediata, em segundos (ignorado na cobv)."
    )
    data_vencimento: date | None = Field(
        default=None, examples=["2027-12-10"],
        description="Se presente, emite cobv (cobrança com vencimento) em vez de cob imediata.",
    )
    validade_apos_vencimento: int = Field(
        default=30, description="Dias corridos em que a cobv ainda pode ser paga após o vencimento."
    )
    devedor: Pagador | None = Field(default=None, description="Devedor (obrigatório na cobv)")
    descricao: str | None = Field(default=None, examples=["Mensalidade 12/2027"],
                                  description="solicitacaoPagador (texto ao pagador)")


class PixCobrancaIn(BaseModel):
    tenant_id: str = Field(description="Identificador do tenant", examples=["empresa_123"])
    provider: Provider = Field(
        default=Provider.c6,
        description="**Caminho**: só `on` (API do banco) — Pix dinâmico não existe "
                    "offline, e `off` responde `422`. Nome de banco aqui é apelido "
                    "legado (`c6` = `on` + `banco=c6`).",
    )
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(
        default_factory=dict, description="Blob por provider. c6: {chave_pix, ...}"
    )
    pix: PixCobranca
    credentials: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Credenciais do banco enviadas NO REQUEST (client_id, client_secret, "
            "pfx_base64, pfx_password). Só em memória; fallback: cofre VAULT__*."
        ),
    )


class PixCobrancaOut(BaseModel):
    """Resposta normalizada da cobrança Pix."""

    txid: str | None = None
    status: Status
    valor: Decimal | None = Field(
        default=None, description="Valor original da cobrança, como o banco devolveu"
    )
    pix_copia_cola: str | None = Field(default=None, description="Payload EMV (copia-e-cola)")
    location: str | None = Field(default=None, description="URL do payload (loc.location)")
    expira_em: datetime | None = Field(
        default=None,
        description="Instante em que a cobrança deixa de ser pagável. Na cob imediata é "
                    "criação + expiração; na cobv é o vencimento + a validade após ele.",
    )
    raw: dict[str, Any] | None = None


# --- Bolepix (boleto híbrido online com Pix EVP — C6 /v2/bank_slips) ----------


#: Formato do identificador no /v2 do C6. Estava escrito em três lugares
#: (comentário do módulo, docstring da rota, descrição do campo) e não valia em
#: nenhum: `abc` e id de 40 caracteres iam para o banco e voltavam como 400 dele.
EXTERNAL_REFERENCE_ID = r"^[A-Z0-9]{26}$"


class BolepixCobranca(BaseModel):
    valor: Decimal = Field(gt=0, description="Valor da cobrança — maior que zero",
                           examples=["99.90"])
    vencimento: date = Field(examples=["2027-12-30"])
    descricao: str = Field(description="Descrição da cobrança (obrigatória no Bolepix)",
                           examples=["Assinatura 12/2027"])
    pagador: Pagador = Field(
        description="endereco OBRIGATORIO: {address|logradouro+numero, neighborhood|bairro, "
                    "city|cidade, state|uf, zip_code|cep} — os 3 ultimos sao exigidos pelo C6 /v2"
    )
    external_reference_id: str | None = Field(
        default=None, pattern=EXTERNAL_REFERENCE_ID,
        description="`^[A-Z0-9]{26}$` — 26 caracteres, só maiúsculas e dígitos. Gerado "
                    "automaticamente se omitido, e devolvido em `id`. **É por ele que se "
                    "consulta o Bolepix**, e reenviar o mesmo devolve a cobrança existente "
                    "em vez de criar outra — mande o seu se houver botão humano na frente. "
                    "String vazia vale como omitido: template que substitui variável não "
                    "preenchida produz `\"\"`, e isso sempre significou \"gere um\".",
        examples=["PEDIDO00000000000000004242"],
    )

    @field_validator("external_reference_id", mode="before")
    @classmethod
    def _vazio_e_ausente(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v
    chave_pix: str | None = Field(
        default=None, examples=["7d9f1a52-0c3b-4e21-9f88-1a2b3c4d5e6f"],
        description="Chave EVP do recebedor. Sem ela (aqui ou em `account_config.chave_pix`) "
                    "não há segmento Pix, e o resultado é um boleto comum — que é `/cobranca`, "
                    "não Bolepix. Por isso a ausência responde 422.")
    nosso_numero: str | None = Field(default=None, examples=["12345678"])
    instrucoes: list[str] | None = None
    dias_apos_vencimento: int | None = Field(
        default=None, ge=0,
        description="days_after_due_date — dias de tolerância APÓS o vencimento; negativo não "
                    "existe (o boleto não vence antes de vencer)")


class BolepixIn(BaseModel):
    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    bolepix: BolepixCobranca
    credentials: dict[str, Any] | None = None


# --- Checkout (link de pagamento com cartão) ------------------------------------
#
# MODO LINK, e só ele. O pagador digita o cartão no domínio do banco; o PAN não
# passa por aqui e o escopo PCI-DSS fica com o banco. Isso é decisão de produto,
# e ela **só é real se o campo não existir** — documentar não segura. Daí o
# `extra="forbid"`
# abaixo: `save_card`, `capture` e companhia são recusados com 422 em vez de
# repassados ao banco. Checkout transparente (`/authorize`,
# `/generate/public-key`) não é implementado.


class TipoCartao(str, Enum):
    credito = "credito"
    debito = "debito"


class JurosPor(str, Enum):
    """Quem paga o juro do parcelamento. Default `loja` = BY_SELLER (decisão 1)."""

    loja = "loja"
    emissor = "emissor"


class Autenticacao(str, Enum):
    obrigatoria = "obrigatoria"
    opcional = "opcional"
    nao_exigida = "nao_exigida"


class CheckoutCobranca(BaseModel):
    """Corpo do link de pagamento. Tudo aqui é do CONSUMIDOR da API: varia de
    cliente para cliente e viaja na requisição — esta API não guarda regra
    comercial de ninguém.

    Isso vale em particular para **política de parcelamento**: teto de parcelas e
    valor mínimo de parcela são da loja, e a aplicação que consome resolve os
    dois ANTES de chamar. Replicá-los aqui criaria uma segunda fonte de verdade
    que envelhece — e recusaria como inválido um parcelamento que o banco
    aceita."""

    model_config = {"extra": "forbid"}

    valor: Decimal = Field(
        gt=0, description="Valor total do checkout — maior que zero", examples=["150.00"])
    tipo: TipoCartao = Field(default=TipoCartao.credito, description="credito | debito")
    parcelas: int = Field(
        default=1, ge=1,
        description="Máximo de parcelas oferecido ao pagador (ele escolhe abaixo disso, "
                    "salvo `parcelas_fixas`). Repassado ao banco COMO VEIO: não há teto "
                    "aqui, e **valor mínimo de parcela não existe nesta API** — é regra "
                    "comercial de quem chama, que calcula o número antes de enviar "
                    "(ex.: `min(3, valor // 100)`). Se o banco recusar o número enviado, "
                    "a resposta é `422` com o motivo dele em `upstream`, e o ajuste é "
                    "reenviar com outra configuração.",
    )
    juros_por: JurosPor | None = Field(
        default=JurosPor.loja,
        description="Quem paga o juro do parcelamento: loja (BY_SELLER) ou emissor (BY_ISSUER)",
    )
    parcelas_fixas: bool | None = Field(
        default=None, description="Se o pagador NÃO pode escolher a quantidade de parcelas"
    )
    autenticacao: Autenticacao | None = Field(
        default=None, description="Autenticação pelo emissor — apetite de risco do chamador"
    )
    recorrente: bool | None = Field(default=None, description="Sinaliza cobrança recorrente")
    pix: bool = Field(default=False, description="Oferece Pix no mesmo link (QR gerado pelo banco)")
    descricao: str | None = Field(default=None, examples=["Pedido 4242"])
    expira_em: datetime | None = Field(default=None, description="Default do banco: 7 dias",
                                       examples=["2027-12-30T23:59:59-03:00"])
    redirect_url: str | None = Field(
        default=None, description="Para onde o pagador volta após pagar — http(s) apenas",
        examples=["https://sua-loja.com.br/pedido/4242/retorno"])
    external_reference_id: str | None = Field(default=None, description="Seu identificador",
                                              examples=["PED-2027-0042"])
    pagador: Pagador | None = Field(
        default=None,
        description="Se enviado com endereço, exige street|logradouro, number|numero (numérico), "
                    "city|cidade, state|uf e zip_code|cep — o C6 recusa endereço incompleto",
    )

    @field_validator("juros_por")
    @classmethod
    def _juros_obrigatorio_quando_parcela(cls, v: JurosPor | None, info: Any) -> JurosPor | None:
        # O C6 exige interest_type quando installments > 1. O default já cobre;
        # anular explicitamente com parcelamento é o único jeito de chegar aqui,
        # e é 422 nosso em vez de 400 do banco.
        if v is None and (info.data.get("parcelas") or 1) > 1:
            raise ValueError("parcelas > 1 exige juros_por (loja ou emissor)")
        return v

    @field_validator("redirect_url")
    @classmethod
    def _redirect_navegavel(cls, v: str | None) -> str | None:
        # Esta URL não fica aqui: o banco a publica na PÁGINA DELE, e o pagador
        # a percorre. Repassar esquema arbitrário — `javascript:...` à frente —
        # é deixar esta API escolher o que roda no domínio do banco, na frente
        # de quem está digitando o cartão. Só destino navegável passa.
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("redirect_url deve começar com http:// ou https://")
        return v


class CheckoutIn(BaseModel):
    # `extra="forbid"` aqui, e não só no `checkout`: o módulo promete que dado de
    # cartão não existe nesta API, e a promessa só vale se o campo for RECUSADO.
    # Sem isto, `card_number` no nível de cima respondia 201 e sumia — o chamador
    # concluía que mandou o PAN e que a API o aceitou.
    model_config = {"extra": "forbid"}

    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    checkout: CheckoutCobranca
    credentials: dict[str, Any] | None = None


class CheckoutOut(BaseModel):
    """Resposta normalizada do link de pagamento."""

    id: str | None = Field(default=None, description="Id do checkout no banco")
    url: str | None = Field(default=None, description="URL do link — para onde o pagador vai")
    status: Status
    expira_em: datetime | None = None
    raw: dict[str, Any] | None = Field(default=None, description="Resposta crua do banco (debug)")


# --- Pix lote de cobv -----------------------------------------------------------


class LoteCobvIn(BaseModel):
    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    descricao: str = Field(examples=["Mensalidades 12/2027"])
    cobrancas: list[PixCobranca] = Field(description="Cada item exige txid e data_vencimento")
    credentials: dict[str, Any] | None = None


class LoteCobvRevisaoIn(BaseModel):
    """Revisão de lote de cobv (PATCH BACEN `/lotecobv/{id}`).

    Sem `descricao`, ao contrário do `LoteCobvIn`: o PATCH do BACEN carrega
    apenas `cobsv`. Reaproveitar o schema da criação obrigaria a mandar um campo
    que o banco ignora — e um campo que o chamador acha que está alterando, mas
    não está, é pior que campo ausente. Daí o `extra="forbid"`: mandar
    `descricao` aqui é `422`, não silêncio."""

    model_config = {"extra": "forbid"}

    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    cobrancas: list[PixCobranca] = Field(
        description="As cobranças a revisar — mesma forma da criação. Cada item exige "
                    "txid, data_vencimento e devedor")
    credentials: dict[str, Any] | None = None


# --- Pix Automático (BACEN: rec / solicrec / cobr) --------------------------------


class Recorrencia(BaseModel):
    """Vínculo de recorrência (Pix Automático) — o 'contrato de cobrança'."""

    contrato: str = Field(description="Identificador do contrato no recebedor", examples=["CT-2026-001"])
    objeto: str | None = Field(default=None, description="Descrição do objeto do contrato", examples=["Aluguel Apto 101"])
    devedor: Pagador
    periodicidade: str = Field(description="SEMANAL | MENSAL | TRIMESTRAL | SEMESTRAL | ANUAL", examples=["MENSAL"])
    data_inicial: date = Field(examples=["2027-01-10"])
    data_final: date | None = Field(default=None, examples=["2027-12-10"])
    valor_fixo: Decimal | None = Field(default=None, examples=["150.00"],
                                       description="valorRec — cobranças de valor fixo")
    valor_minimo: Decimal | None = Field(default=None, examples=["50.00"],
                                         description="valorMinimoRecebedor — valor variável")
    politica_retentativa: str = Field(default="PERMITE_3R_7D", description="NAO_PERMITE | PERMITE_3R_7D")
    loc: int | None = Field(default=None, description="Id de locrec p/ adesão via QR (Jornada 2)")
    txid_ativacao: str | None = Field(
        default=None, examples=["PEDIDO2027000000000000004242"],
        description="ativacao.dadosJornada.txid (Jornadas 3/4)")
    extras: dict[str, Any] | None = Field(default=None, description="Campos BACEN adicionais (merge no payload)")


class RecorrenciaIn(BaseModel):
    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    recorrencia: Recorrencia
    credentials: dict[str, Any] | None = None


#: Txid do BACEN — o mesmo padrão da cob/cobv, aplicado também ao cobr.
TXID_BACEN = r"^[a-zA-Z0-9]{26,35}$"


class CobrancaRecorrente(BaseModel):
    """Uma cobrança do ciclo (cobr) — agendar >= 2 dias antes do vencimento.
    O agendamento é responsabilidade do produto consumidor (gateway stateless)."""

    id_rec: str = Field(description="idRec da recorrência aprovada",
                        examples=["RR12345678202701101a2b3c4d5e6"])
    valor: Decimal = Field(gt=0, examples=["150.00"],
                           description="Valor da parcela do ciclo — maior que zero")
    data_vencimento: date = Field(
        examples=["2027-12-10"],
        description="Vencimento da parcela. O BACEN quer o agendamento com pelo menos "
                    "**2 dias** de antecedência; menos que isso o banco pode recusar. "
                    "Data no PASSADO é recusada aqui — não existe agendar para ontem.")
    info_adicional: str | None = Field(default=None, examples=["Parcela 3/12"])
    extras: dict[str, Any] | None = None

    @field_validator("data_vencimento")
    @classmethod
    def _nao_agenda_para_ontem(cls, v: date) -> date:
        # Medido: vencimento cinco dias no passado era aceito com 201 e seguia
        # para o banco. A antecedência de 2 dias fica como aviso — não sei se o
        # BACEN conta dia corrido ou útil, e travar errado impediria agendamento
        # que o banco aceita. O passado não tem essa ambiguidade.
        if v < date.today():
            raise ValueError(
                f"data_vencimento {v} está no passado; a cobrança do ciclo é agendada "
                "para o futuro (o BACEN pede >= 2 dias de antecedência)")
        return v


class CobrancaRecorrenteIn(BaseModel):
    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    cobranca: CobrancaRecorrente
    credentials: dict[str, Any] | None = None


class SolicitacaoRecorrenciaIn(BaseModel):
    """solicrec — pedido de autorização enviado ao app do pagador (Jornada 1)."""

    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict)
    dados: dict[str, Any] = Field(description="Payload BACEN da solicrec (idRec, ...)")
    credentials: dict[str, Any] | None = None


# --- Cadastro de webhook no banco ------------------------------------------------


class ServicoWebhook(str, Enum):
    """O que o banco notifica naquela URL.

    O vocabulário nasceu do C6, que tem duas notificações (boleto e cartão). O
    Inter tem UMA — e a chama de `COBRANCA`: quem lê a documentação do Inter
    manda essa palavra e levava `422` listando só os termos do outro banco.
    `COBRANCA` entra como grafia do mesmo serviço; o provider do C6 traduz para
    a sua antes de falar com o banco, senão o alias viraria `400` lá na frente.
    """

    bank_slip = "BANK_SLIP"
    checkout = "CHECKOUT"
    cobranca = "COBRANCA"


def campo_url_webhook(descricao: str) -> Any:
    """A URL que o BANCO vai chamar.

    Validada por um motivo prático antes de qualquer outro: destino inalcançável
    é aceito com `200` e o cadastro parece feito — o cliente só descobre que não
    recebe notificação quando um pagamento se perde. Ver `validar_url_webhook`.
    """
    return Field(description=descricao,
                 examples=["https://api.minhaempresa.com.br/webhooks/c6/empresa_123"])


class WebhookBancoIn(BaseModel):
    model_config = {"extra": "forbid"}

    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    url: str = campo_url_webhook(
        "URL **pública e https** que o banco chamará "
        "(ex: https://.../webhooks/c6/{tenant})")
    service: ServicoWebhook = Field(
        default=ServicoWebhook.bank_slip,
        description="O que o banco notifica: `BANK_SLIP` (boleto) ou `CHECKOUT` (cartão). `COBRANCA` é a grafia do Inter para o boleto e vale como sinônimo — o Inter tem uma notificação só, e ali o campo é ignorado.")
    credentials: dict[str, Any] | None = None


    @field_validator("url")
    @classmethod
    def _url_alcancavel(cls, v: str) -> str:
        return validar_url_webhook(v)


class WebhookPixIn(BaseModel):
    """Webhook BACEN por chave — o banco chama a URL quando um Pix cai na chave.

    Era `body: dict`: o Swagger não descrevia campo nenhum, campo com nome errado
    passava calado e `credentials` viajava sem tipo dentro de um dicionário
    livre."""

    model_config = {"extra": "forbid"}

    tenant_id: str = Field(examples=["empresa_123"])
    provider: Provider = Provider.c6
    banco: Banco | None = campo_banco()
    chave: str = Field(description="Chave Pix do recebedor (a mesma das cobranças)",
                       examples=["financeiro@minhaempresa.com.br"])
    url: str = campo_url_webhook(
        "URL **pública e https** que o banco chamará quando um Pix cair na chave")
    credentials: dict[str, Any] | None = None

    @field_validator("tenant_id", "chave", "url")
    @classmethod
    def _obrigatorio(cls, v: str, info: Any) -> str:
        # A versão com corpo livre recusava os três VAZIOS com "campo
        # obrigatório: <nome>", e a troca por schema tinha perdido a checagem.
        # A frase volta igual: há consumidor que lê o erro por ela.
        if not (v or "").strip():
            raise ValueError(f"campo obrigatório: {info.field_name}")
        return v

    @field_validator("url")
    @classmethod
    def _url_alcancavel(cls, v: str) -> str:
        return validar_url_webhook(v)


# --- Tokenização de credenciais ----------------------------------------------


class CredencialIn(BaseModel):
    """Cadastro de credenciais do banco — devolve um token opaco (única vez)."""

    tenant_id: str = Field(description="Tenant dono destas credenciais", examples=["empresa_123"])
    provider: Provider = Field(description="Caminho (`on`) ou o nome do banco no formato legado (ex: c6)")
    banco: Banco | None = campo_banco(
        "**Instituição** destas credenciais. É por ela que a credencial é "
        "guardada e procurada — com `provider=on`, é o que separa o C6 do "
        "Sicoob do mesmo tenant."
    )
    credentials: dict[str, Any] = Field(
        description="Esquema **próprio de cada banco** — o vigente sai em `GET /bancos`. "
                    "Cifradas em repouso; a chave é derivada do token, então o servidor "
                    "não decifra sozinho.",
        examples=[{
            "client_id": "seu-client-id",
            "client_secret": "seu-client-secret",
            "pfx_base64": "<PKCS12 em base64>",
            "pfx_password": "senha-do-certificado",
        }],
    )


class CertificadoOut(BaseModel):
    """Metadado do certificado mTLS. **Nunca** o certificado nem a chave."""

    situacao: str = Field(
        description=("`ok` · `expirando` · `expirado` · `ilegivel`. O limiar de "
                     "`expirando` acompanha a **vida** do certificado: 30 dias para um "
                     "anual, um terço da validade para os de vida curta. Fixo em 30, o "
                     "certificado do Inter — que vive 30 dias — nascia `expirando`."),
        examples=["ok"])
    titular: str | None = Field(default=None, examples=[
        "MSDOBRASILLTDA05230380000174-baas-api-sandbox.c6bank.info"],
        description="CN do certificado. Os bancos escrevem `<RAZAO><CNPJ>-<host>`, e o "
                    "**host diz o ambiente**: `baas-api-sandbox` é sandbox, `baas-api` "
                    "é produção. É por aqui que se confere qual certificado está em uso.")
    emissor: str | None = None
    valido_de: str | None = None
    valido_ate: str | None = Field(default=None, examples=["2027-08-21"])
    alerta_a_partir_de: int | None = Field(
        default=None, examples=[30],
        description="Quantos dias restantes fazem este certificado virar `expirando`. "
                    "Varia com a vida dele — sem este campo, `expirando` com 9 dias num "
                    "caso e `ok` com 25 noutro pareceria incoerência.")
    dias_restantes: int | None = Field(
        default=None, examples=[360],
        description="Negativo quando já venceu. O certificado dos bancos vale um ano e "
                    "**não tem renovação in-place**: vence e toda chamada passa a falhar "
                    "no handshake, de uma vez.")
    host: str | None = Field(
        default=None, examples=["baas-api-sandbox.c6bank.info"],
        description="O host extraído do CN — é ele que diz o ambiente. `null` quando o "
                    "banco não carimba host no CN (o do Inter é só o nome da aplicação).")
    base_em_uso: str | None = Field(
        default=None, examples=["https://baas-api-sandbox.c6bank.info"],
        description="Para onde ESTE servidor está apontado naquele banco.")
    ambiente_confere: bool | None = Field(
        default=None, examples=[True],
        description="O certificado é do mesmo ambiente da `base_em_uso`? `false` significa "
                    "que toda chamada vai falhar no handshake — o banco responde `403 mTLS`, "
                    "que se lê como credencial inválida e manda conferir client_id e secret, "
                    "que estão certos. `null` = não dá para dizer (sem host no CN).")
    formato: str | None = Field(default=None, examples=["pem"])
    detalhe: str | None = Field(default=None,
                                description="Por que não deu para ler, quando `ilegivel`.")
    cnpj: str | None = Field(default=None, examples=["05230380000174"],
                             description="Extraído do CN, para conferência num olhar.")
    par_confere: bool | None = Field(
        default=None, examples=[True],
        description="A chave privada é a DESTE certificado? `null` quando não há par PEM "
                    "para comparar. `false` é o erro clássico da troca de certificado — "
                    "`.crt` novo com `.key` antigo —, que no handshake vira uma mensagem "
                    "de TLS que não aponta o par trocado.")


class CredencialOut(BaseModel):
    token: str = Field(description="Token opaco (bapi_...) — exibido UMA única vez; guarde-o. "
                                   "Use nas demais rotas via Authorization: Bearer")
    tenant_id: str
    provider: Provider
    banco: Banco | None = campo_banco("Instituição destas credenciais (eco do request).")
    certificado: CertificadoOut | None = Field(
        default=None,
        description="Metadado do certificado mTLS enviado, quando há. Vem no cadastro "
                    "porque é onde o erro custa menos: carregar o certificado do ambiente "
                    "errado só aparecia no primeiro handshake, horas depois.")


# --- Conciliação (C6 Pay statement) ------------------------------------------


class ConciliacaoOut(BaseModel):
    """Página de recebíveis/transações — itens crus do banco + paginação."""

    page: int | None = None
    last_page: int | None = None
    total_items: int | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class WebhookEvent(BaseModel):
    """Evento normalizado de pagamento — também o corpo do push aos consumidores."""

    event: str = Field(description="Tipo do evento", examples=["cobranca.atualizada", "pix.recebido"])
    id: str | None = Field(default=None, description="Id da cobrança / txid")
    status: Status | None = None
    paid_at: datetime | None = Field(default=None, description="Data/hora do pagamento, se liquidado")
    valor: Decimal | None = Field(default=None, description="Valor pago, se aplicável")
    confirmado: bool | None = Field(
        default=None,
        description="O status foi reconsultado no banco? `true` confere; `false` o banco "
                    "discordou e o `status` aqui é o DELE; `null` não foi possível "
                    "perguntar (evento sem tenant, sem credencial no cofre, ou consulta "
                    "desligada). Só status que move dinheiro é reconsultado.",
    )
    pendente_de_entrega: bool | None = Field(
        default=None,
        description="`true` quando o push ao consumidor não saiu de primeira e o evento "
                    "ficou no outbox para re-tentativa com backoff.",
    )
    raw: dict[str, Any] | None = None


class CarneIn(BaseModel):
    tenant_id: str = Field(description="Identificador do tenant", examples=["empresa_123"])
    provider: Provider
    banco: Banco | None = campo_banco()
    account_config: dict[str, Any] = Field(default_factory=dict, description="Blob por provider (ver CobrancaIn)")
    bank: str | None = Field(
        default=None,
        description="Slug do layout na engine pyCobrança. **Redundante**: o layout vem do "
                    "`banco`. Aceito por compatibilidade e precisa concordar — `bank` "
                    "divergente responde 422, porque carnê desenhado como um banco e "
                    "registrado em outro não é pagável.",
        examples=["banco_c6"])
    parcelas: list[Cobranca] = Field(
        min_length=1,
        description="Parcelas do carnê (registradas individualmente). Pelo menos uma, e "
                    "cada uma com identificador próprio (`seu_numero`/`nosso_numero`)")
    credentials: dict[str, Any] | None = Field(
        default=None,
        description="Credenciais do banco no request (só memória; fallback: cofre VAULT__*).",
    )


class CarneOut(BaseModel):
    carne_pdf_base64: str | None = Field(default=None, description="PDF do carnê 3-vias em base64")
    cobrancas: list[CobrancaOut] = Field(default_factory=list, description="Cobranças registradas (uma por parcela)")
