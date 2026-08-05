# Idempotência de POST que cria recurso no banco — hoje o /checkout.
#
# O problema é banal e caro: duplo clique no botão, retry do cliente HTTP, ou o
# APEX reenviando o submit criam DOIS links de pagamento para a mesma venda. Um
# deles fica órfão, e nada impede o pagador de pagar os dois.
#
# Semântica (a mesma do /jobs, e a que o mercado espera do header):
#   mesma chave + mesmo corpo  -> devolve a resposta guardada, sem tocar no banco
#   mesma chave + corpo outro  -> 422; a chave identifica UMA requisição, e
#                                 reaproveitá-la com outro payload é bug de quem
#                                 chama, não intenção de criar outra coisa
#   sem chave                  -> passa direto (o header é opt-in)
#
# Escopo por tenant: chaves de tenants diferentes não colidem.
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

# Retenção. Uma chave só é útil enquanto o recurso que ela criou for útil, e o
# link de pagamento do C6 expira em 7 dias por default. 30 dias cobre isso com
# folga e ainda pega o reenvio tardio de quem guardou a chave num job. Passado
# esse prazo, a mesma chave volta a criar um checkout novo — o que está certo:
# o link antigo já não existe para ser devolvido.
RETENCAO_DIAS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotencia (
    tenant_id TEXT NOT NULL,
    escopo TEXT NOT NULL,
    chave TEXT NOT NULL,
    impressao TEXT NOT NULL,
    resposta TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    PRIMARY KEY (tenant_id, escopo, chave)
)
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def impressao(payload: Any) -> str:
    """Impressão do corpo, estável à ordem das chaves — `sort_keys` para que o
    mesmo pedido serializado em outra ordem não pareça um pedido diferente."""
    bruto = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


class ConflitoDeIdempotencia(Exception):
    """Chave reusada com outro corpo — o router traduz para 422."""


class IdempotencyStore:
    def buscar(self, tenant_id: str, escopo: str, chave: str,
               impressao_: str) -> dict[str, Any] | None: ...
    def guardar(self, tenant_id: str, escopo: str, chave: str, impressao_: str,
                resposta: dict[str, Any]) -> None: ...
    def limpar(self, antes: str) -> int: ...


class SqliteIdempotencyStore(IdempotencyStore):
    def __init__(self, path: str) -> None:
        self.path = path
        with self._conn() as c:
            c.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def buscar(self, tenant_id, escopo, chave, impressao_):
        with self._conn() as c:
            row = c.execute(
                "SELECT impressao, resposta FROM idempotencia"
                " WHERE tenant_id = ? AND escopo = ? AND chave = ?",
                (tenant_id, escopo, chave)).fetchone()
        if not row:
            return None
        if row["impressao"] != impressao_:
            raise ConflitoDeIdempotencia
        return json.loads(row["resposta"])

    def guardar(self, tenant_id, escopo, chave, impressao_, resposta) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO idempotencia (tenant_id, escopo, chave, impressao,"
                " resposta, criado_em) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (tenant_id, escopo, chave) DO NOTHING",
                (tenant_id, escopo, chave, impressao_,
                 json.dumps(resposta, default=str, ensure_ascii=False), agora()))

    def limpar(self, antes) -> int:
        with self._conn() as c:
            return max(c.execute("DELETE FROM idempotencia WHERE criado_em < ?",
                                 (antes,)).rowcount, 0)


class PostgresIdempotencyStore(IdempotencyStore):
    def __init__(self, dsn: str, schema: str | None = None) -> None:
        self.dsn = dsn
        self.schema = schema or os.environ.get("DB_SCHEMA", "boleto_api")
        self.tabela = f"{self.schema}.idempotencia"
        with self._conn() as c:
            c.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            c.execute(_SCHEMA.replace("idempotencia", self.tabela, 1))

    def _conn(self):
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True)

    def buscar(self, tenant_id, escopo, chave, impressao_):
        with self._conn() as c:
            row = c.execute(
                f"SELECT impressao, resposta FROM {self.tabela}"
                " WHERE tenant_id = %s AND escopo = %s AND chave = %s",
                (tenant_id, escopo, chave)).fetchone()
        if not row:
            return None
        if row[0] != impressao_:
            raise ConflitoDeIdempotencia
        return json.loads(row[1])

    def guardar(self, tenant_id, escopo, chave, impressao_, resposta) -> None:
        with self._conn() as c:
            c.execute(
                f"INSERT INTO {self.tabela} (tenant_id, escopo, chave, impressao,"
                " resposta, criado_em) VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (tenant_id, escopo, chave) DO NOTHING",
                (tenant_id, escopo, chave, impressao_,
                 json.dumps(resposta, default=str, ensure_ascii=False), agora()))

    def limpar(self, antes) -> int:
        with self._conn() as c:
            return max(c.execute(f"DELETE FROM {self.tabela} WHERE criado_em < %s",
                                 (antes,)).rowcount, 0)


_instancia: IdempotencyStore | None = None
_lock = threading.Lock()


def get_idempotency_store() -> IdempotencyStore:
    global _instancia
    with _lock:
        if _instancia is None:
            dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
            _instancia = PostgresIdempotencyStore(dsn) if dsn else SqliteIdempotencyStore(
                os.environ.get("IDEMPOTENCY_DB_PATH")
                or os.environ.get("CREDENTIAL_DB_PATH", "credentials.db"))
        return _instancia


def reset_idempotency_store() -> None:
    """Descarta o singleton — para os testes trocarem de banco entre casos."""
    global _instancia
    with _lock:
        _instancia = None


def limpar() -> int:
    """Apaga chaves além da retenção. Devolve quantas saíram.

    Chamada pela manutenção do outbox (`outbox.limpar()`) e disponível direto
    para cron. Sem ela a tabela só cresce — uma linha por venda, para sempre."""
    try:
        dias = float(os.environ.get("IDEMPOTENCY_RETENCAO_DIAS", "") or RETENCAO_DIAS)
    except ValueError:
        dias = RETENCAO_DIAS
    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    return get_idempotency_store().limpar(corte)
