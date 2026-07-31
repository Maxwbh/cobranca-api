#!/usr/bin/env python3
"""Benchmark do caminho OFFLINE em lote (Sicoob) — 100 a 500 boletos.

Mede o tempo de resposta dos dois caminhos que existem para lote:

  1. POST /api/boleto/multi   — SINCRONO: um PDF com todos os boletos.
     Limitado por LOTE_MAX_ITENS (default 200) — acima disso responde 413.
  2. POST /jobs/boletos       — ASSINCRONO: 202 + job_id, processa em
     background e publica artefatos. E o caminho para volume alto.

Por que os dois: comparar sincrono x assincrono no MESMO volume mostra onde o
sincrono deixa de ser viavel — e o 413 documenta o limite em vez de deixar o
cliente descobrir com timeout.

Uso:
    python scripts/benchmark_lote.py                          # HML, 100..500
    python scripts/benchmark_lote.py --tamanhos 100 200       # subconjunto
    python scripts/benchmark_lote.py --base-url http://localhost:8000
    python scripts/benchmark_lote.py --repeticoes 3           # mediana de 3
    python scripts/benchmark_lote.py --json saida.json        # resultado bruto

Nao precisa de credencial: o caminho offline nao fala com banco.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

# A URL do Render nao e fixa (vem do nome do servico): o alvo remoto sai de
# COB_BASE_URL. Sem ela, o benchmark roda contra o servico local.
BASE_PADRAO = os.environ.get("COB_BASE_URL", "http://localhost:8000")
BANCO = "sicoob"

# Conta de teste — dados de forma, nao credencial. O caminho offline nao
# autentica em banco nenhum; isto so alimenta o layout do boleto.
CONTA = {
    "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181",
    "agencia": "3073",
    "conta_corrente": "12345678",
    "convenio": "1234567",
    "carteira": "1",
}


def _boleto(indice: int, vencimento: str) -> dict:
    return {
        "bank": BANCO,
        **CONTA,
        "valor": 150.0 + indice,
        "sacado": f"Pagador Teste {indice:04d}",
        "sacado_documento": "52998224725",
        "nosso_numero": str(indice + 1),
        "numero_documento": f"BENCH{indice:05d}",
        "data_vencimento": vencimento,
    }


def gerar_lote(n: int) -> list[dict]:
    venc = (date.today() + timedelta(days=30)).isoformat()
    return [_boleto(i, venc) for i in range(n)]


def _post(url: str, corpo: bytes, headers: dict, timeout: int):
    req = urllib.request.Request(url, data=corpo, headers=headers, method="POST")
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = r.read()
            return r.status, dados, dict(r.headers), time.perf_counter() - inicio
    except urllib.error.HTTPError as e:
        dados = e.read()
        return e.code, dados, dict(e.headers), time.perf_counter() - inicio
    except Exception as e:  # timeout, conexao derrubada
        return None, str(e).encode(), {}, time.perf_counter() - inicio


def _cab(headers: dict, nome: str, default=""):
    """Header case-insensitive: HTTP/2 minusculiza os nomes (o Render serve h2),
    entao um dict cru erraria o lookup de X-Boletos-Count."""
    alvo = nome.lower()
    for k, v in (headers or {}).items():
        if k.lower() == alvo:
            return v
    return default


def _get(url: str, timeout: int):
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(), time.perf_counter() - inicio
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.perf_counter() - inicio
    except Exception as e:
        return None, str(e).encode(), time.perf_counter() - inicio


# ---------------------------------------------------------------- sincrono
def medir_multi(base: str, n: int, timeout: int) -> dict:
    """POST /api/boleto/multi — multipart com o JSON do lote."""
    lote = json.dumps(gerar_lote(n)).encode()
    marca = "----benchlote"
    corpo = (
        f"--{marca}\r\n"
        'Content-Disposition: form-data; name="data"; filename="lote.json"\r\n'
        "Content-Type: application/json\r\n\r\n"
    ).encode() + lote + f"\r\n--{marca}--\r\n".encode()

    status, dados, headers, seg = _post(
        f"{base}/api/boleto/multi?type=pdf", corpo,
        {"Content-Type": f"multipart/form-data; boundary={marca}"}, timeout)

    r = {"caminho": "sincrono", "endpoint": "/api/boleto/multi", "n": n,
         "status": status, "segundos": round(seg, 3), "bytes": len(dados or b"")}
    if status == 200:
        r["ok"] = int(_cab(headers, "X-Boletos-Count", 0))
        r["falhas"] = int(_cab(headers, "X-Boletos-Failed", 0))
        r["lote_status"] = _cab(headers, "X-Batch-Status")
        r["pdf"] = (dados or b"")[:4] == b"%PDF"
    elif status == 413:
        try:
            r["limite"] = json.loads(dados)
        except Exception:
            pass
    elif dados:
        r["erro"] = dados[:200].decode("utf-8", "replace")
    return r


# --------------------------------------------------------------- assincrono
def medir_job(base: str, n: int, timeout: int, poll_max: int,
              intervalo: float = 1.0) -> dict:
    corpo = json.dumps({
        "tenant_id": "benchmark",
        "boletos": gerar_lote(n),   # o contrato do job usa `boletos`
    }).encode()
    status, dados, _h, seg_criacao = _post(
        f"{base}/jobs/boletos", corpo, {"Content-Type": "application/json"}, timeout)

    r = {"caminho": "assincrono", "endpoint": "/jobs/boletos", "n": n,
         "status": status, "segundos_aceite": round(seg_criacao, 3)}
    if status == 413:
        # JOB_MAX_ITENS (default 200) tambem limita o caminho ASSINCRONO.
        try:
            r["limite"] = json.loads(dados)
        except Exception:
            pass
        return r
    if status != 202:
        r["erro"] = (dados or b"")[:300].decode("utf-8", "replace")
        return r

    job = json.loads(dados)
    job_id = job.get("job_id") or job.get("id")
    r["job_id"] = job_id

    # poll ate estado terminal — o tempo que importa e o do PROCESSAMENTO
    inicio = time.perf_counter()
    estado, tentativas = None, 0
    while time.perf_counter() - inicio < poll_max:
        st, corpo_get, _ = _get(f"{base}/jobs/boletos/{job_id}?tenant_id=benchmark", timeout)
        tentativas += 1
        if st == 200:
            j = json.loads(corpo_get)
            estado = j.get("status") or j.get("state")
            if estado in ("completed", "partially_completed", "failed"):
                r.update({"estado": estado,
                          "completed": j.get("completed"), "failed": j.get("failed"),
                          "total": j.get("total")})
                break
        time.sleep(intervalo)
    r["segundos_processamento"] = round(time.perf_counter() - inicio, 3)
    r["segundos_total"] = round(seg_criacao + (time.perf_counter() - inicio), 3)
    r["polls"] = tentativas
    if estado is None:
        r["estado"] = "TIMEOUT_DO_BENCHMARK"
    return r


# ------------------------------------------------------------------ fatiado
def medir_fatiado(base: str, n: int, fatia: int, timeout: int) -> dict:
    """Volume acima do limite exige FATIAR — e o que o cliente tem de fazer hoje.

    Mede o custo real de emitir `n` boletos em pedaços de `fatia`, incluindo o
    overhead de N requisicoes em vez de uma.
    """
    restante, pedacos, inicio = n, [], time.perf_counter()
    while restante > 0:
        atual = min(fatia, restante)
        r = medir_multi(base, atual, timeout)
        pedacos.append(r)
        if r["status"] != 200:
            break
        restante -= atual
    total = time.perf_counter() - inicio
    ok = sum(p.get("ok", 0) for p in pedacos)
    return {"caminho": "fatiado", "endpoint": f"/api/boleto/multi x{len(pedacos)}",
            "n": n, "fatia": fatia, "status": 200 if ok == n else 0,
            "segundos": round(total, 3), "requisicoes": len(pedacos),
            "boletos_ok": ok,
            "segundos_por_fatia": [p.get("segundos") for p in pedacos]}


def _por_boleto(seg: float | None, n: int) -> str:
    if not seg or not n:
        return "—"
    return f"{seg / n * 1000:.1f} ms"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=BASE_PADRAO)
    ap.add_argument("--tamanhos", type=int, nargs="+", default=[100, 200, 300, 400, 500])
    ap.add_argument("--repeticoes", type=int, default=1, help="mediana de N execuções")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--poll-max", type=int, default=900, help="teto do poll do job (s)")
    ap.add_argument("--poll-intervalo", type=float, default=1.0,
                    help="intervalo entre consultas do job (s). O tempo medido do "
                         "assincrono e QUANTIZADO por este valor: com 1.0s, um job "
                         "de 1.2s pode medir 2s. Use 0.05 em ambiente local.")
    ap.add_argument("--fatiar", type=int, metavar="TAM",
                    help="acima do limite, fatia em pedaços de TAM (ex.: 200)")
    ap.add_argument("--so-sincrono", action="store_true")
    ap.add_argument("--so-assincrono", action="store_true")
    ap.add_argument("--json", help="grava o resultado bruto")
    a = ap.parse_args()

    base = a.base_url.rstrip("/")
    print(f"Benchmark de lote OFFLINE ({BANCO}) — {base}")
    print(f"tamanhos: {a.tamanhos} | repetições: {a.repeticoes}\n")

    st, corpo, seg = _get(f"{base}/api/health", 90)
    if st != 200:
        print(f"ERRO: {base}/api/health respondeu {st}", file=sys.stderr)
        return 1
    print(f"health OK ({seg:.2f}s — inclui cold start do free tier)\n")

    resultados = []
    for n in a.tamanhos:
        if not a.so_assincrono:
            amostras = [medir_multi(base, n, a.timeout) for _ in range(a.repeticoes)]
            r = min(amostras, key=lambda x: x["segundos"])
            if a.repeticoes > 1:
                r["mediana_segundos"] = round(
                    statistics.median(x["segundos"] for x in amostras), 3)
            resultados.append(r)
            marca = {200: "ok", 413: "413 (acima do limite)"}.get(r["status"], f"status {r['status']}")
            print(f"  sync  n={n:4d}  {r['segundos']:7.2f}s  "
                  f"{_por_boleto(r['segundos'], n):>9}/boleto  {marca}")
        if a.fatiar and n > a.fatiar:
            r = medir_fatiado(base, n, a.fatiar, a.timeout)
            resultados.append(r)
            print(f"  fatia n={n:4d}  {r['segundos']:7.2f}s  "
                  f"{_por_boleto(r['segundos'], n):>9}/boleto  "
                  f"{r['requisicoes']} requisições de {a.fatiar}, {r['boletos_ok']} ok")
        if not a.so_sincrono:
            r = medir_job(base, n, a.timeout, a.poll_max, a.poll_intervalo)
            resultados.append(r)
            if r.get("status") == 202:
                tot = r.get("segundos_total")
                print(f"  job   n={n:4d}  {tot:7.2f}s  "
                      f"{_por_boleto(tot, n):>9}/boleto  "
                      f"aceite={r['segundos_aceite']:.2f}s estado={r.get('estado')}")
            elif r.get("status") == 413:
                print(f"  job   n={n:4d}       —              —      "
                      f"413 (acima de JOB_MAX_ITENS)")
            else:
                print(f"  job   n={n:4d}  ERRO status={r.get('status')} "
                      f"{r.get('erro','')[:90]}")

    print("\n" + "=" * 74)
    print(f"{'caminho':<12}{'n':>6}{'total':>10}{'por boleto':>13}{'resultado':>28}")
    print("-" * 74)
    for r in resultados:
        if r["caminho"] == "fatiado":
            seg = r["segundos"]
            desf = f"{r['requisicoes']}x{r['fatia']} → {r['boletos_ok']} ok"
        elif r["caminho"] == "sincrono":
            seg = r["segundos"]
            desf = ("PDF ok" if r.get("pdf") else
                    "LIMITE 413" if r["status"] == 413 else f"status {r['status']}")
        else:
            seg = r.get("segundos_total")
            desf = ("LIMITE 413" if r.get("status") == 413
                    else r.get("estado", f"status {r.get('status')}"))
        print(f"{r['caminho']:<12}{r['n']:>6}{(f'{seg:.2f}s' if seg else '—'):>10}"
              f"{_por_boleto(seg, r['n']):>13}{desf:>28}")
    print("=" * 74)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"base_url": base, "banco": BANCO, "resultados": resultados},
                      f, ensure_ascii=False, indent=2)
        print(f"\nresultado bruto: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
