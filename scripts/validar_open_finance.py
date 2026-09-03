#!/usr/bin/env python3
"""Valida o que os bancos atuais expõem no Open Finance — pelo diretório oficial.

Open Finance não se descobre no portal do banco. Quem publica o que cada
instituição expõe é o **Diretório de Participantes**, e ele é público: um JSON
sem autenticação, com organização, papéis, authorisation servers, famílias de
API, versão, certificação e endpoint mTLS de cada uma. É a fonte que decide, e
por isso é ela que este roteiro lê — não a documentação comercial dos bancos.

    python scripts/validar_open_finance.py
    python scripts/validar_open_finance.py --json > evidencia-open-finance.json
    python scripts/validar_open_finance.py --participantes participants.json  # cópia local

Nenhuma credencial é usada: o diretório é aberto. Nada é enviado a banco nenhum.

## O que este roteiro PROVA, e o que ele não prova

Prova que o banco é participante ativo e **quais famílias de API ele expõe**.

Atenção ao **lado** de cada família, porque é onde a leitura fácil erra: nas
APIs de pagamento do Open Finance quem publica é a **detentora da conta do
PAGADOR**, e quem consome é o iniciador (ITP), que debita a conta do pagador.
Então `payments-pix-recurring-payments-automatic` publicada por um banco
significa *"sou o banco do pagador e aceito débito de Pix Automático iniciado
por um ITP"* — e **não** *"ofereço ao meu cliente PJ a API de cobrança
recorrente"*, que é o que uma API de cobrança precisa. Essa segunda é a
`rec`/`cobr` do BACEN, na API do próprio banco, e não aparece no diretório.

Some-se a norma: desde 16/06/2025 o lado **pagador** é obrigatório para quem
oferece conta transacional a pagadores, enquanto o lado **recebedor** é
facultativo. Um ✅ nesta coluna é, em boa parte, obrigação cumprida — não
diferencial de produto.

**Não** prova que esta API poderia consumi-las. Consumir Open Finance exige ser
participante do ecossistema com papel habilitado (DADOS para dados, ITP para
iniciação), certificados BRCAC/BRSEAL da ICP do Open Finance, FAPI-BR
(private_key_jwt + PAR), registro dinâmico de cliente (DCR) e certificação de
conformidade publicada no diretório. O modelo de credencial desta API —
`client_id` + `client_secret` + certificado do portal do banco, um por banco — é
de **cliente do banco**, e não alcança nada disso. A distância entre as duas
colunas do relatório é exatamente essa.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

DIRETORIO = "https://data.directory.openbankingbrasil.org.br/participants"

# CNPJ (8 primeiros dígitos) -> banco desta API — as 19 instituições, não só as
# quatro do caminho ON: a pergunta "quais bancos oferecem Pix Automático" vale
# para o catálogo inteiro. O diretório indexa por ORGANIZAÇÃO, e os sistemas
# cooperativos entram pela central (Sicoob pela Confederação, não pelo Bancoob;
# Sicredi pela Confederação; Unicred e Ailos pelas centrais): casar por nome
# acharia dezenas de singulares, e nenhuma delas é quem publica as APIs.
BANCOS = {
    "05463212": "ailos",           # CENTRAL AILOS
    "00000000": "banco_brasil",    # BANCO DO BRASIL S.A.
    "00000208": "banco_brasilia",  # BRB
    "07237373": "banco_nordeste",  # BNB
    "28127603": "banestes",
    "92702067": "banrisul",        # BCO DO ESTADO DO RS
    "60746948": "bradesco",
    "31872495": "c6",
    "00360305": "caixa",
    "33479023": "citibank",
    "00416968": "inter",
    "60701190": "itau",
    "58160789": "safra",
    "90400888": "santander",       # BCO SANTANDER (BRASIL)
    "04891850": "sicoob",          # Confederação Nacional das Cooperativas do Sicoob
    "03795072": "sicredi",         # Confederação Sicredi
    "00315557": "unicred",         # Unicred do Brasil
}
# CrediSIS e HSBC não têm entrada: o primeiro não consta no diretório sob a
# central, e o segundo não opera mais no Brasil (a operação foi para o Bradesco
# em 2016). A engine mantém os dois porque o layout CNAB deles ainda é pedido
# para boleto — o que não implica Pix nenhum.
SEM_ENTRADA = {
    "credisis": "não localizado no diretório sob a central do sistema",
    "hsbc": "não opera mais no Brasil (operação incorporada pelo Bradesco em 2016)",
}

# As famílias que interessam a uma API de cobrança. O resto do catálogo do Open
# Finance (investimentos, câmbio, seguros, dados cadastrais) está fora do
# produto e listá-lo daria volume sem informação.
INTERESSE = {
    "payments-pix": "iniciação de pagamento Pix (ITP)",
    "payments-consents": "consentimento de pagamento",
    "payments-pix-recurring-payments": "pagamento recorrente Pix",
    "payments-pix-recurring-payments-automatic": "PIX AUTOMÁTICO pelo Open Finance",
    "payments-recurring-consents": "consentimento de recorrência",
    "payments-recurring-consents-automatic": "consentimento de Pix Automático",
    "enrollments": "vínculo do dispositivo (jornada sem redirecionamento)",
    "accounts": "dados de conta (conciliação)",
    "resources": "recursos compartilhados",
}


def baixar(url: str) -> list:
    import httpx
    with httpx.Client(timeout=120.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def familias(org: dict) -> dict[str, dict]:
    """Família de API -> o que o diretório afirma sobre ela (a mais recente).

    Um banco pode publicar a mesma família em vários authorisation servers (o
    Itaú publica em doze). Guardar a maior versão evita relatório dizendo que o
    banco está numa versão antiga porque uma marca secundária ficou para trás.
    """
    achado: dict[str, dict] = {}
    for servidor in org.get("AuthorisationServers", []):
        for recurso in servidor.get("ApiResources", []):
            nome = recurso.get("ApiFamilyType")
            if not nome:
                continue
            versao = recurso.get("ApiVersion") or "0"
            atual = achado.get(nome)
            if atual and _versao(atual["versao"]) >= _versao(versao):
                continue
            achado[nome] = {
                "versao": versao,
                "status": recurso.get("Status"),
                "certificacao": recurso.get("CertificationStatus"),
                "certificacao_expira": recurso.get("CertificationExpirationDate"),
                "marca": servidor.get("CustomerFriendlyName"),
                "endpoints": [e.get("ApiEndpoint") for e in
                              (recurso.get("ApiDiscoveryEndpoints") or [])][:3],
            }
    return achado


def _versao(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in str(v).split("."))


def validar(participantes: list) -> list[dict]:
    por_banco = {}
    for org in participantes:
        chave = str(org.get("RegistrationNumber", ""))[:8]
        banco = BANCOS.get(chave)
        if not banco:
            continue
        fams = familias(org)
        por_banco[banco] = {
            "banco": banco,
            "organizacao": org.get("OrganisationName"),
            "status": org.get("Status"),
            "papeis": sorted({p.get("Role") for p in org.get("OrgDomainRoleClaims", [])
                              if p.get("Status") == "Active" and p.get("Role")}),
            "authorisation_servers": len(org.get("AuthorisationServers", [])),
            "familias_total": len(fams),
            "familias_de_interesse": {n: fams[n] for n in INTERESSE if n in fams},
            "faltando_de_interesse": [n for n in INTERESSE if n not in fams],
        }
    # Banco que não aparece no diretório é resultado, não omissão.
    for banco in BANCOS.values():
        por_banco.setdefault(banco, {"banco": banco, "status": "AUSENTE_DO_DIRETORIO",
                                     "familias_de_interesse": {},
                                     "faltando_de_interesse": list(INTERESSE)})
    for banco, motivo in SEM_ENTRADA.items():
        por_banco[banco] = {"banco": banco, "status": "SEM_ENTRADA_NO_DIRETORIO",
                            "motivo": motivo, "familias_de_interesse": {},
                            "faltando_de_interesse": list(INTERESSE)}
    return [por_banco[b] for b in sorted(por_banco)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="evidência crua em JSON no stdout")
    ap.add_argument("--participantes", help="arquivo local do diretório (evita rebaixar 5 MB)")
    args = ap.parse_args()

    try:
        participantes = (json.load(open(args.participantes)) if args.participantes
                         else baixar(DIRETORIO))
    except Exception as e:  # noqa: BLE001 — sem o diretório não há o que validar
        print(f"não foi possível ler o diretório: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    relatorio = validar(participantes)

    if args.json:
        print(json.dumps({"executado_em": datetime.now().isoformat(timespec="seconds"),
                          "fonte": args.participantes or DIRETORIO,
                          "funcionalidade": "open_finance",
                          "participantes_no_diretorio": len(participantes),
                          "bancos": relatorio}, ensure_ascii=False, indent=2, default=str))
        return 0

    print(f"diretório: {len(participantes)} organizações\n")

    # Resumo primeiro: com 19 instituições, o detalhe de cada uma enterra a
    # resposta da pergunta que se faz na prática — quem tem Pix Automático.
    print(f"{'banco':16} {'Pix Aut.':9} {'ITP Pix':8} status")
    print("-" * 60)
    for r in relatorio:
        tem = "payments-pix-recurring-payments-automatic" in r["familias_de_interesse"]
        pix = "payments-pix" in r["familias_de_interesse"]
        print(f"{r['banco']:16} {'✅ sim' if tem else '⛔ não':9} "
              f"{'sim' if pix else 'não':8} {r['status']}")
    print()

    for r in relatorio:
        print(f"{'='*72}\n{r['banco'].upper()} — {r.get('organizacao') or '—'} "
              f"[{r['status']}]\n{'='*72}")
        if not r.get("papeis"):
            print(f"  {r.get('motivo') or 'não consta no diretório de participantes'}\n")
            continue
        print(f"  papéis: {', '.join(r['papeis']) or '—'}")
        print(f"  authorisation servers: {r['authorisation_servers']} | "
              f"famílias publicadas: {r['familias_total']}")
        for nome, dados in r["familias_de_interesse"].items():
            print(f"    ✅ {nome:44} v{dados['versao']:8} {dados['certificacao'] or ''}")
        for nome in r["faltando_de_interesse"]:
            print(f"    ⛔ {nome:44} não publicada")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
