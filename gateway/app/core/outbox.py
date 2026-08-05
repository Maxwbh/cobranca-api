# Entrega confiável dos eventos ao consumidor downstream — as duas pontas.
#
# ENTRADA (inbox): o banco reentrega. C6, Sicoob e Inter re-postam a notificação
# quando não recebem 2xx a tempo, e a mesma liquidação chega N vezes. Sem
# memória do que já passou, o consumidor recebe N pushes de "pago" e dá baixa N
# vezes. `ja_visto()` marca o corpo bruto e diz se ele já foi processado.
#
# SAÍDA (outbox): o push era uma tentativa só — consumidor fora do ar por 30s e
# o evento SUMIA (o `except` devolvia False e ninguém mais sabia dele). Agora a
# falha vira linha na fila, com backoff exponencial, e o drenador re-tenta.
#
# Por que persistente e não fila em memória: o processo reinicia (deploy, OOM,
# free tier dormindo) e o que não estiver em disco morre com ele. É o mesmo
# argumento do job_store — estado de entrega é do SERVIÇO, não do request.
#
# Backend igual ao do cofre e ao do job_store: Postgres/Supabase se houver DSN,
# senão SQLite.
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# Backoff entre tentativas (segundos). A última define a janela total: ~17min.
BACKOFF = (5, 15, 60, 300, 900)


def max_tentativas() -> int:
    """Derivado do BACKOFF em tempo de chamada — a primeira tentativa é inline,
    as demais vêm da fila. Função e não constante para que trocar o BACKOFF
    (teste ou ajuste) não deixe o limite dessincronizado."""
    return len(BACKOFF) + 1


PENDENTE = "pendente"
ENTREGUE = "entregue"
DESISTIU = "desistiu"

_SCHEMA_OUTBOX = """
CREATE TABLE IF NOT EXISTS webhook_outbox (
    evento_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    secret TEXT,
    corpo TEXT NOT NULL,
    status TEXT NOT NULL,
    tentativas INTEGER NOT NULL DEFAULT 0,
    ultimo_erro TEXT,
    proxima_em TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
)
"""
_SCHEMA_OUTBOX_IDX = """
CREATE INDEX IF NOT EXISTS webhook_outbox_pendentes
    ON webhook_outbox (status, proxima_em)
"""
# `visto_em` fica para a limpeza por idade; a PK é a impressão do corpo.
_SCHEMA_INBOX = """
CREATE TABLE IF NOT EXISTS webhook_inbox (
    impressao TEXT PRIMARY KEY,
    banco TEXT NOT NULL,
    tenant_id TEXT,
    visto_em TEXT NOT NULL
)
"""


# Retenção. As duas tabelas guardam coisas com validade diferente:
#
#   inbox  — só precisa cobrir a JANELA DE REENTREGA do banco, que é de horas.
#            7 dias é folga larga; guardar mais é pagar disco para deduplicar
#            uma notificação que o banco não vai mandar de novo.
#   outbox — as linhas `entregue`/`desistiu` não têm função operacional, só
#            forense ("por que o consumidor não recebeu em março?"). 30 dias.
#            `pendente` NUNCA é apagado por idade: ainda tem trabalho a fazer.
RETENCAO_INBOX_DIAS = 7
RETENCAO_OUTBOX_DIAS = 30


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _em(segundos: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)).isoformat()


def _corte(dias: float) -> str:
    """Instante a partir do qual a linha é velha. Comparação lexicográfica de
    ISO-8601 em UTC — o mesmo truque que `pendentes()` já usa, e que só vale
    porque TODA gravação passa por `agora()`, com formato idêntico."""
    return (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()


def _dias(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, "") or default)
    except ValueError:
        return default


def impressao(banco: str, tenant_id: str | None, corpo: bytes) -> str:
    """Identidade da notificação: banco + tenant + bytes exatos do corpo.

    Sobre os bytes brutos, e não sobre o evento normalizado, porque duas
    notificações diferentes podem normalizar para o mesmo evento (o banco muda
    um campo que não mapeamos) — e essa segunda merece passar.
    """
    h = hashlib.sha256()
    h.update(banco.encode())
    h.update(b"\x00")
    h.update((tenant_id or "").encode())
    h.update(b"\x00")
    h.update(corpo)
    return h.hexdigest()


class Outbox:
    """Interface mínima; implementações SQLite e Postgres abaixo."""

    # --- entrada (dedup)
    def ja_visto(self, impressao_: str, banco: str, tenant_id: str | None) -> bool: ...
    def esquecer(self, impressao_: str) -> None: ...

    # --- saída (fila)
    def enfileirar(self, *, url: str, secret: str, corpo: bytes) -> str: ...
    def pendentes(self, limite: int = 50) -> list[dict[str, Any]]: ...
    def marcar_entregue(self, evento_id: str) -> None: ...
    def marcar_falha(self, evento_id: str, erro: str) -> None: ...
    def contar(self, status: str) -> int: ...

    # --- manutenção
    def limpar(self, *, inbox_antes: str, outbox_antes: str) -> dict[str, int]: ...


class SqliteOutbox(Outbox):
    def __init__(self, path: str) -> None:
        self.path = path
        with self._conn() as c:
            c.execute(_SCHEMA_OUTBOX)
            c.execute(_SCHEMA_OUTBOX_IDX)
            c.execute(_SCHEMA_INBOX)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def ja_visto(self, impressao_, banco, tenant_id) -> bool:
        # INSERT ... ON CONFLICT DO NOTHING + rowcount: a checagem e a marca são
        # a MESMA operação. Duas reentregas simultâneas do banco (acontece)
        # passariam as duas por um SELECT-depois-INSERT.
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO webhook_inbox (impressao, banco, tenant_id, visto_em)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (impressao) DO NOTHING",
                (impressao_, banco, tenant_id, agora()))
            return cur.rowcount == 0

    def esquecer(self, impressao_) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM webhook_inbox WHERE impressao = ?", (impressao_,))

    def enfileirar(self, *, url, secret, corpo) -> str:
        evento_id = f"evt_{uuid.uuid4().hex[:24]}"
        ts = agora()
        with self._conn() as c:
            c.execute(
                "INSERT INTO webhook_outbox (evento_id, url, secret, corpo, status,"
                " tentativas, proxima_em, criado_em, atualizado_em)"
                " VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (evento_id, url, secret, corpo.decode("utf-8"), PENDENTE,
                 _em(BACKOFF[0]), ts, ts))
        return evento_id

    def pendentes(self, limite=50):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM webhook_outbox WHERE status = ? AND proxima_em <= ?"
                " ORDER BY proxima_em LIMIT ?", (PENDENTE, agora(), limite)).fetchall()
        return [dict(r) for r in rows]

    def marcar_entregue(self, evento_id) -> None:
        with self._conn() as c:
            c.execute("UPDATE webhook_outbox SET status = ?, atualizado_em = ?"
                      " WHERE evento_id = ?", (ENTREGUE, agora(), evento_id))

    def marcar_falha(self, evento_id, erro) -> None:
        with self._conn() as c:
            row = c.execute("SELECT tentativas FROM webhook_outbox WHERE evento_id = ?",
                            (evento_id,)).fetchone()
            if not row:
                return
            n = row["tentativas"] + 1
            esgotou = n >= max_tentativas()
            c.execute(
                "UPDATE webhook_outbox SET status = ?, tentativas = ?, ultimo_erro = ?,"
                " proxima_em = ?, atualizado_em = ? WHERE evento_id = ?",
                (DESISTIU if esgotou else PENDENTE, n, erro[:500],
                 _em(BACKOFF[min(n - 1, len(BACKOFF) - 1)]), agora(), evento_id))

    def contar(self, status) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) AS n FROM webhook_outbox WHERE status = ?",
                            (status,)).fetchone()
        return int(row["n"])

    def limpar(self, *, inbox_antes, outbox_antes):
        with self._conn() as c:
            i = c.execute("DELETE FROM webhook_inbox WHERE visto_em < ?",
                          (inbox_antes,)).rowcount
            # `status != PENDENTE` e não `IN (entregue, desistiu)`: um estado novo
            # que alguém acrescente amanhã não deve ser preservado por omissão —
            # o que não pode sumir é o que ainda tem trabalho, e isso é o pendente.
            o = c.execute("DELETE FROM webhook_outbox WHERE status != ?"
                          " AND atualizado_em < ?", (PENDENTE, outbox_antes)).rowcount
        return {"inbox": max(i, 0), "outbox": max(o, 0)}


class PostgresOutbox(Outbox):
    def __init__(self, dsn: str, schema: str | None = None) -> None:
        self.dsn = dsn
        self.schema = schema or os.environ.get("DB_SCHEMA", "boleto_api")
        self.outbox = f"{self.schema}.webhook_outbox"
        self.inbox = f"{self.schema}.webhook_inbox"
        with self._conn() as c:
            c.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            # Só a TABELA leva o schema; o nome do índice não é qualificável em
            # Postgres, então o DDL do índice é montado à parte (um `.replace`
            # cego renomearia `webhook_outbox_pendentes` junto e falharia).
            c.execute(_SCHEMA_OUTBOX.replace("webhook_outbox", self.outbox, 1))
            c.execute("CREATE INDEX IF NOT EXISTS webhook_outbox_pendentes"
                      f" ON {self.outbox} (status, proxima_em)")
            c.execute(_SCHEMA_INBOX.replace("webhook_inbox", self.inbox, 1))

    def _conn(self):
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True)

    def ja_visto(self, impressao_, banco, tenant_id) -> bool:
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO {self.inbox} (impressao, banco, tenant_id, visto_em)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (impressao) DO NOTHING",
                (impressao_, banco, tenant_id, agora()))
            return cur.rowcount == 0

    def esquecer(self, impressao_) -> None:
        with self._conn() as c:
            c.execute(f"DELETE FROM {self.inbox} WHERE impressao = %s", (impressao_,))

    def enfileirar(self, *, url, secret, corpo) -> str:
        evento_id = f"evt_{uuid.uuid4().hex[:24]}"
        ts = agora()
        with self._conn() as c:
            c.execute(
                f"INSERT INTO {self.outbox} (evento_id, url, secret, corpo, status,"
                " tentativas, proxima_em, criado_em, atualizado_em)"
                " VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)",
                (evento_id, url, secret, corpo.decode("utf-8"), PENDENTE,
                 _em(BACKOFF[0]), ts, ts))
        return evento_id

    def pendentes(self, limite=50):
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM {self.outbox} WHERE status = %s AND proxima_em <= %s"
                " ORDER BY proxima_em LIMIT %s", (PENDENTE, agora(), limite)).fetchall()
            cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in rows]

    def marcar_entregue(self, evento_id) -> None:
        with self._conn() as c:
            c.execute(f"UPDATE {self.outbox} SET status = %s, atualizado_em = %s"
                      " WHERE evento_id = %s", (ENTREGUE, agora(), evento_id))

    def marcar_falha(self, evento_id, erro) -> None:
        with self._conn() as c:
            row = c.execute(f"SELECT tentativas FROM {self.outbox} WHERE evento_id = %s",
                            (evento_id,)).fetchone()
            if not row:
                return
            n = row[0] + 1
            esgotou = n >= max_tentativas()
            c.execute(
                f"UPDATE {self.outbox} SET status = %s, tentativas = %s, ultimo_erro = %s,"
                " proxima_em = %s, atualizado_em = %s WHERE evento_id = %s",
                (DESISTIU if esgotou else PENDENTE, n, erro[:500],
                 _em(BACKOFF[min(n - 1, len(BACKOFF) - 1)]), agora(), evento_id))

    def contar(self, status) -> int:
        with self._conn() as c:
            row = c.execute(f"SELECT COUNT(*) FROM {self.outbox} WHERE status = %s",
                            (status,)).fetchone()
        return int(row[0])

    def limpar(self, *, inbox_antes, outbox_antes):
        with self._conn() as c:
            i = c.execute(f"DELETE FROM {self.inbox} WHERE visto_em < %s",
                          (inbox_antes,)).rowcount
            o = c.execute(f"DELETE FROM {self.outbox} WHERE status <> %s"
                          " AND atualizado_em < %s", (PENDENTE, outbox_antes)).rowcount
        return {"inbox": max(i, 0), "outbox": max(o, 0)}


_instancia: Outbox | None = None
_lock = threading.Lock()


def get_outbox() -> Outbox:
    """Singleton — o drenador roda numa thread e precisa do mesmo store."""
    global _instancia
    with _lock:
        if _instancia is None:
            dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
            _instancia = PostgresOutbox(dsn) if dsn else SqliteOutbox(
                os.environ.get("OUTBOX_DB_PATH")
                or os.environ.get("CREDENTIAL_DB_PATH", "credentials.db"))
        return _instancia


def reset_outbox() -> None:
    """Descarta o singleton — para os testes trocarem de banco entre casos."""
    global _instancia
    with _lock:
        _instancia = None


# --- drenador ---------------------------------------------------------------------


def drenar(entregar) -> int:
    """Re-tenta os pendentes vencidos. `entregar(url, secret, corpo) -> bool`.

    Devolve quantos saíram. Recebe a função de entrega em vez de importar o
    forwarder para não fechar o ciclo de import (o forwarder enfileira aqui).
    """
    ob = get_outbox()
    entregues = 0
    for linha in ob.pendentes():
        corpo = linha["corpo"].encode("utf-8")
        try:
            ok = entregar(linha["url"], linha["secret"] or "", corpo)
        except Exception as e:  # noqa: BLE001 — o drenador não pode morrer por um destino
            ob.marcar_falha(linha["evento_id"], f"{type(e).__name__}: {e}")
            continue
        if ok:
            ob.marcar_entregue(linha["evento_id"])
            entregues += 1
        else:
            ob.marcar_falha(linha["evento_id"], "resposta não-2xx do consumidor")
    return entregues


# --- manutenção -------------------------------------------------------------------


def limpar() -> dict[str, int]:
    """Apaga o que passou da retenção nas três tabelas de estado de entrega.

    Sem isto elas só crescem: cada notificação recebida deixa uma linha no inbox
    para sempre, e cada push entregue deixa a sua no outbox. Num volume modesto
    de mil eventos/dia, é um SQLite inutilizável em alguns meses.

    Chamável direto (cron, script de manutenção, teste); a thread do drenador
    também chama de hora em hora. Devolve quantas linhas saíram de cada tabela.
    """
    # Import tardio: `idempotency` não sabe nada de outbox, e manter a seta em um
    # sentido só evita ciclo se um dia ele precisar enfileirar alguma coisa.
    from app.core import idempotency

    contas = get_outbox().limpar(
        inbox_antes=_corte(_dias("WEBHOOK_INBOX_RETENCAO_DIAS", RETENCAO_INBOX_DIAS)),
        outbox_antes=_corte(_dias("OUTBOX_RETENCAO_DIAS", RETENCAO_OUTBOX_DIAS)),
    )
    contas["idempotencia"] = idempotency.limpar()
    return contas


_thread: threading.Thread | None = None

# A limpeza não precisa da cadência do drenador (30s): varrer três tabelas a cada
# meio minuto é trabalho de banco para nada. De hora em hora sobra.
INTERVALO_LIMPEZA_SEG = 3600


def iniciar_drenador(entregar, intervalo: float | None = None) -> bool:
    """Sobe a thread que drena a fila em background. Idempotente.

    O produto é um container só, sem scheduler: sem isto, um evento enfileirado
    só sairia quando o próximo webhook chegasse — e se nenhum chegar, nunca. A
    mesma thread faz a limpeza por idade, mais espaçada.

    `OUTBOX_DRAIN_INTERVAL=0` desliga (é o que os testes usam, chamando
    `drenar()` e `limpar()` direto). **Desligar a thread desliga também a
    limpeza** — nesse modo, agende `limpar()` por fora.
    """
    global _thread
    if intervalo is None:
        intervalo = float(os.environ.get("OUTBOX_DRAIN_INTERVAL", "30"))
    if intervalo <= 0:
        return False
    with _lock:
        if _thread and _thread.is_alive():
            return False

        def loop() -> None:
            desde_a_limpeza = 0.0
            while True:
                time.sleep(intervalo)
                try:
                    drenar(entregar)
                except Exception:  # noqa: BLE001 — thread de fundo nunca derruba a app
                    pass
                desde_a_limpeza += intervalo
                if desde_a_limpeza >= INTERVALO_LIMPEZA_SEG:
                    desde_a_limpeza = 0.0
                    try:
                        limpar()
                    except Exception:  # noqa: BLE001
                        pass

        _thread = threading.Thread(target=loop, name="outbox-drain", daemon=True)
        _thread.start()
        return True


def evento_para_corpo(event: dict[str, Any]) -> bytes:
    """JSON compacto e estável — o mesmo byte a byte que a assinatura cobre."""
    return json.dumps(event, default=str, separators=(",", ":")).encode("utf-8")
