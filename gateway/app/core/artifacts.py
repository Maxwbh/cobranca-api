# Artefatos de job em DISCO (Fase 2 do plano-jobs-lote.md).
#
# Contrato pyCobrança doc 12: "não retornar PDFs em base64 dentro do JSON" —
# persistir e devolver referências com hash, tamanho e expiração. Aqui o
# storage é o disco do container (Render: /app/data, volume gravável).
#
# Layout:
#   <ARTIFACT_DIR>/<job_id>/items/<item_id>.pdf
#   <ARTIFACT_DIR>/<job_id>/manifest.json
#   <ARTIFACT_DIR>/<job_id>/errors.json
#   <ARTIFACT_DIR>/<job_id>/boletos-<job_id>.zip
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from urllib.parse import urlencode
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: Retenção padrão dos artefatos (dias) — expiração publicada no manifesto.
RETENCAO_DIAS = int(os.environ.get("ARTIFACT_TTL_DIAS", "7"))

_SEGURO = re.compile(r"[^A-Za-z0-9._-]")


def raiz() -> Path:
    """Diretório base dos artefatos (env ARTIFACT_DIR; default /app/data/jobs)."""
    return Path(os.environ.get("ARTIFACT_DIR", "/app/data/jobs"))


def _href(caminho: str, tenant_id: str | None) -> str:
    """Link que o consumidor consegue seguir.

    As rotas de download exigem `tenant_id` (é o isolamento entre clientes), e o
    manifesto publicava o caminho sem ele: seguir o `href` do zip dava `422`.
    Mesmo defeito do `Location` das rotas de criação, só que dentro do corpo."""
    return f"{caminho}?{urlencode({'tenant_id': tenant_id})}" if tenant_id else caminho


def _slug(valor: str) -> str:
    limpo = _SEGURO.sub("_", str(valor))[:120]
    return limpo or "item"


def dir_job(job_id: str) -> Path:
    return raiz() / _slug(job_id)


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def salvar_item(job_id: str, item_id: str, pdf: bytes,
                tenant_id: str | None = None) -> dict[str, Any]:
    """Grava o PDF do item e devolve os metadados do artefato."""
    destino = dir_job(job_id) / "items"
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"{_slug(item_id)}.pdf"
    caminho = destino / nome
    caminho.write_bytes(pdf)
    return {
        "tipo": "pdf",
        "nome": nome,
        "bytes": len(pdf),
        "sha256": sha256(pdf),
        "href": _href(f"/jobs/boletos/{job_id}/artifacts/items/{nome}", tenant_id),
    }


def _expira_em(criado: datetime | None = None) -> str:
    base = criado or datetime.now(timezone.utc)
    return (base + timedelta(days=RETENCAO_DIAS)).isoformat()


def consolidar(job_id: str, job: dict[str, Any],
               itens: list[dict[str, Any]]) -> dict[str, Any]:
    tenant_id = job.get("tenant_id")
    """Gera manifest.json, errors.json e o zip consolidado do job.

    O zip contém os PDFs + manifesto + relatório de erros (doc 12).
    """
    base = dir_job(job_id)
    base.mkdir(parents=True, exist_ok=True)
    itens_dir = base / "items"

    ok = [i for i in itens if i.get("status") == "completed"]
    falhas = [i for i in itens if i.get("status") == "failed"]

    arquivos: list[dict[str, Any]] = []
    for item in ok:
        art = (item.get("resultado") or {}).get("artifact")
        if art:
            arquivos.append({**art, "item_id": item["item_id"]})

    manifesto = {
        "job_id": job_id,
        "tenant_id": job.get("tenant_id"),
        "tipo": job.get("tipo", "boletos"),
        "status": job.get("status"),
        "total": job.get("total"),
        "completed": len(ok),
        "failed": len(falhas),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "expira_em": _expira_em(),
        "retencao_dias": RETENCAO_DIAS,
        "arquivos": arquivos,
    }
    erros = [{"item_id": i["item_id"], "indice": i.get("indice"),
              "errors": (i.get("resultado") or {}).get("errors", [])} for i in falhas]

    (base / "manifest.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "errors.json").write_text(
        json.dumps(erros, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_nome = f"boletos-{_slug(job_id)}.zip"
    zip_path = base / zip_nome
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for art in arquivos:
            origem = itens_dir / art["nome"]
            if origem.exists():
                z.write(origem, f"pdfs/{art['nome']}")
        z.write(base / "manifest.json", "manifest.json")
        z.write(base / "errors.json", "errors.json")

    conteudo_zip = zip_path.read_bytes()
    manifesto["consolidado"] = {
        "tipo": "zip", "nome": zip_nome, "bytes": len(conteudo_zip),
        "sha256": sha256(conteudo_zip),
        "href": _href(f"/jobs/boletos/{job_id}/artifacts/{zip_nome}", tenant_id),
    }
    (base / "manifest.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def ler_manifesto(job_id: str) -> dict[str, Any] | None:
    caminho = dir_job(job_id) / "manifest.json"
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def caminho_artefato(job_id: str, nome: str, item: bool = False) -> Path | None:
    """Resolve o caminho de um artefato, barrando path traversal."""
    base = dir_job(job_id) / ("items" if item else "")
    alvo = (base / _slug(nome)).resolve()
    try:
        alvo.relative_to(dir_job(job_id).resolve())
    except ValueError:
        return None
    return alvo if alvo.is_file() else None


def expirado(manifesto: dict[str, Any]) -> bool:
    try:
        return datetime.fromisoformat(manifesto["expira_em"]) < datetime.now(timezone.utc)
    except (KeyError, ValueError):
        return False


def remover(job_id: str) -> None:
    shutil.rmtree(dir_job(job_id), ignore_errors=True)


# ------------------------------------------------------------------ CNAB (Fase 3)
def salvar_remessa(job_id: str, sublote_id: str, conteudo: str,
                   tenant_id: str | None = None) -> dict[str, Any]:
    """Grava o arquivo CNAB de um sublote (imutável, para auditoria)."""
    destino = dir_job(job_id) / "files"
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"{_slug(sublote_id)}.rem"
    dados = conteudo.encode("utf-8")
    (destino / nome).write_bytes(dados)
    linhas = conteudo.splitlines()
    return {
        "tipo": "cnab", "nome": nome, "bytes": len(dados), "sha256": sha256(dados),
        "registros": len(linhas),
        "href": _href(f"/jobs/cnab/remessas/{job_id}/files/{nome}", tenant_id),
    }


def consolidar_remessas(job_id: str, job: dict[str, Any],
                        itens: list[dict[str, Any]]) -> dict[str, Any]:
    """Manifesto dos arquivos CNAB (um por sublote) + zip consolidado."""
    tenant_id = job.get("tenant_id")
    base = dir_job(job_id)
    base.mkdir(parents=True, exist_ok=True)
    files_dir = base / "files"

    ok = [i for i in itens if i.get("status") == "completed"]
    falhas = [i for i in itens if i.get("status") == "failed"]
    arquivos = [{**(i.get("resultado") or {}).get("artifact", {}),
                 "sublote_id": i["item_id"],
                 "chave": (i.get("resultado") or {}).get("chave"),
                 "quantidade": (i.get("resultado") or {}).get("quantidade")}
                for i in ok if (i.get("resultado") or {}).get("artifact")]

    manifesto = {
        "job_id": job_id, "tenant_id": job.get("tenant_id"), "tipo": "cnab_remessas",
        "status": job.get("status"), "sublotes": job.get("total"),
        "completed": len(ok), "failed": len(falhas),
        "total_registros": sum(a.get("registros", 0) for a in arquivos),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "expira_em": _expira_em(), "retencao_dias": RETENCAO_DIAS,
        "arquivos": arquivos,
    }
    erros = [{"sublote_id": i["item_id"],
              "chave": (i.get("resultado") or {}).get("chave"),
              "errors": (i.get("resultado") or {}).get("errors", [])} for i in falhas]

    (base / "manifest.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "errors.json").write_text(
        json.dumps(erros, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_nome = f"remessas-{_slug(job_id)}.zip"
    zip_path = base / zip_nome
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for a in arquivos:
            origem = files_dir / a["nome"]
            if origem.exists():
                z.write(origem, f"cnab/{a['nome']}")
        z.write(base / "manifest.json", "manifest.json")
        z.write(base / "errors.json", "errors.json")

    conteudo_zip = zip_path.read_bytes()
    manifesto["consolidado"] = {
        "tipo": "zip", "nome": zip_nome, "bytes": len(conteudo_zip),
        "sha256": sha256(conteudo_zip),
        "href": _href(f"/jobs/cnab/remessas/{job_id}/files/{zip_nome}", tenant_id),
    }
    (base / "manifest.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def caminho_arquivo_cnab(job_id: str, nome: str) -> Path | None:
    """Arquivo CNAB (.rem) ou consolidado/manifesto do job, com anti-traversal."""
    for base in (dir_job(job_id) / "files", dir_job(job_id)):
        alvo = (base / _slug(nome)).resolve()
        try:
            alvo.relative_to(dir_job(job_id).resolve())
        except ValueError:
            continue
        if alvo.is_file():
            return alvo
    return None
