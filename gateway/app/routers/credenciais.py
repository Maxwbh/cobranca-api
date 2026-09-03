# Cadastro de credenciais -> token opaco (tokenização; ver core/credential_store.py).
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core import certificado as cert_mod
from app.core import credential_store
from app.registry import base_do_banco, chave_credencial
from app.schemas import (Banco, CertificadoOut, CredencialIn, CredencialOut,
                         Provider)

router = APIRouter(prefix="/credenciais", tags=["credenciais"])


def _certificado(credenciais: dict, chave: str | None = None) -> CertificadoOut | None:
    """Metadado do certificado — nunca o certificado, nunca a chave.

    `core/vault.py`: "NUNCA logar credencial/certificado". O que sai daqui é
    derivado e não reconstrói nada: titular, emissor, validade, se o par casa e
    se o ambiente do certificado é o mesmo para onde a API está apontada.
    """
    achado = cert_mod.descrever(credenciais)
    if achado is None:
        return None
    base = base_do_banco(chave)
    return CertificadoOut(**achado.to_dict(),
                          cnpj=cert_mod.cnpj_do_titular(achado),
                          par_confere=cert_mod.par_confere(credenciais),
                          host=cert_mod.host_do_titular(achado),
                          base_em_uso=base,
                          ambiente_confere=cert_mod.ambiente_confere(achado, base))


@router.post("", response_model=CredencialOut, status_code=201)
def cadastrar(body: CredencialIn) -> CredencialOut:
    """Armazena as credenciais cifradas (chave derivada do token) e devolve o token.

    O token é exibido UMA única vez — o servidor não consegue recuperá-lo nem
    decifrar as credenciais sem ele. Use-o nas demais rotas via
    `Authorization: Bearer bapi_...`.
    """
    store = credential_store.get_store()
    # A credencial é do BANCO, não do caminho: guardar por `provider` colocaria
    # C6 e Sicoob do mesmo tenant na mesma chave assim que `provider=on` entrou
    # em uso. Para o apelido legado (`provider=c6`) a chave não muda, então
    # token emitido antes continua valendo.
    chave = chave_credencial(body.provider, body.banco)
    token = credential_store.enroll(store, body.tenant_id, chave, body.credentials)
    return CredencialOut(token=token, tenant_id=body.tenant_id, provider=body.provider,
                         banco=body.banco, certificado=_certificado(body.credentials, chave))


@router.delete("", status_code=204)
def revogar(authorization: str = Header(description="Bearer bapi_...")) -> None:
    """Revoga o token imediatamente (apaga o registro cifrado)."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="use Authorization: Bearer bapi_...")
    store = credential_store.get_store()
    if not credential_store.revoke(store, authorization[7:].strip()):
        raise HTTPException(status_code=401, detail="token inválido")


@router.get("", response_model=CredencialOut)
def consultar(authorization: str = Header(description="Bearer bapi_...")) -> CredencialOut:
    """O que está guardado sob este token — **sem** o segredo.

    Existe por causa de uma pergunta que a API não sabia responder: *quando a
    minha integração para de funcionar?* O certificado mTLS dos bancos vale um
    ano e não tem renovação in-place — vence, e toda chamada passa a falhar no
    handshake de uma vez, sem nada no código ter mudado.

    Responde também *qual* certificado está em uso, que é onde a confusão
    acontece de verdade: os bancos entregam pacotes com mais de um, e o ambiente
    está no **host** dentro do CN (`baas-api-sandbox` × `baas-api`). Carregar o
    do ambiente errado só aparecia no primeiro handshake.

    O `token` volta mascarado: ele é exibido uma única vez, no cadastro, e o
    servidor não consegue recuperá-lo — devolvê-lo aqui seria mentira.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="use Authorization: Bearer bapi_...")
    store = credential_store.get_store()
    achado = credential_store.resolve(store, authorization[7:].strip())
    if achado is None:
        raise HTTPException(status_code=401, detail="token inválido")
    tenant_id, chave, credenciais = achado
    return CredencialOut(
        token="bapi_" + "*" * 8, tenant_id=tenant_id,
        provider=Provider(chave) if chave in Provider._value2member_map_ else Provider.on,
        banco=Banco(chave) if chave in Banco._value2member_map_ else None,
        certificado=_certificado(credenciais, chave))
