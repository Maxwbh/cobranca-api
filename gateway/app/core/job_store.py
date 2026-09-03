# Persistência de jobs de lote (processamento assíncrono — plano Fase 1).
#
# Contrato pyCobrança doc 12: a orquestração (estado, itens, idempotência) é
# do SERVIÇO; a engine só resolve domínio. Estado sobrevive a restart do
# processo por estar no banco.
#
# Backend (mesmo padrão do cofre): Postgres/Supabase se SUPABASE_DB_URL ou
# DATABASE_URL existir (schema próprio, default `boleto_api`); senão SQLite.
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Any

# Estados (doc 12)
JOB_RECEIVED = "received"
JOB_VALIDATING = "validating"
JOB_PROCESSING = "processing"
JOB_COMPLETED = "completed"
JOB_PARTIAL = "partially_completed"
JOB_FAILED = "failed"

class StatusItem(str, Enum):
    """Estados possíveis de um item — o vocabulário fechado do filtro."""

    pending = "pending"
    completed = "completed"
    failed = "failed"


ITEM_PENDING = "pending"
ITEM_COMPLETED = "completed"
ITEM_FAILED = "failed"

_SCHEMA_JOB = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    meta TEXT
)
"""
_SCHEMA_ITEM = """
CREATE TABLE IF NOT EXISTS job_items (
    job_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    indice INTEGER NOT NULL,
    status TEXT NOT NULL,
    resultado TEXT,
    PRIMARY KEY (job_id, item_id)
)
"""
_SCHEMA_IDEMP = """
CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotencia
    ON jobs (tenant_id, idempotency_key)
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def novo_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:24]}"


class JobStore:
    """Interface mínima; implementações SQLite e Postgres abaixo."""

    # --- escrita
    def criar(self, job: dict[str, Any], itens: list[dict[str, Any]]) -> None: ...
    def atualizar_status(self, job_id: str, status: str, **contadores: int) -> None: ...
    def concluir_item(self, job_id: str, item_id: str, status: str,
                      resultado: dict[str, Any]) -> None: ...
    def salvar_metricas(self, job_id: str, metricas: dict[str, Any]) -> None: ...

    # --- leitura
    def obter(self, tenant_id: str, job_id: str) -> dict[str, Any] | None: ...
    def itens(self, job_id: str, status: str | None = None,
              limite: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...
    def por_idempotencia(self, tenant_id: str, chave: str) -> str | None: ...


class SqliteJobStore(JobStore):
    def __init__(self, path: str) -> None:
        self.path = path
        with self._conn() as c:
            c.execute(_SCHEMA_JOB)
            c.execute(_SCHEMA_ITEM)
            c.execute(_SCHEMA_IDEMP)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def criar(self, job, itens) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO jobs (job_id, tenant_id, tipo, status, total, completed, failed,"
                " idempotency_key, criado_em, atualizado_em, meta)"
                " VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)",
                (job["job_id"], job["tenant_id"], job["tipo"], job["status"], job["total"],
                 job.get("idempotency_key"), job["criado_em"], job["criado_em"],
                 json.dumps(job.get("meta") or {})),
            )
            c.executemany(
                "INSERT INTO job_items (job_id, item_id, indice, status, resultado)"
                " VALUES (?, ?, ?, ?, NULL)",
                [(job["job_id"], i["item_id"], i["indice"], ITEM_PENDING) for i in itens],
            )

    def atualizar_status(self, job_id, status, **contadores) -> None:
        campos = ", ".join(f"{k} = ?" for k in contadores)
        sets = f"status = ?, atualizado_em = ?{', ' + campos if campos else ''}"
        with self._conn() as c:
            c.execute(f"UPDATE jobs SET {sets} WHERE job_id = ?",
                      (status, agora(), *contadores.values(), job_id))

    def concluir_item(self, job_id, item_id, status, resultado) -> None:
        with self._conn() as c:
            c.execute("UPDATE job_items SET status = ?, resultado = ? WHERE job_id = ? AND item_id = ?",
                      (status, json.dumps(resultado, ensure_ascii=False), job_id, item_id))

    def salvar_metricas(self, job_id, metricas) -> None:
        with self._conn() as c:
            row = c.execute("SELECT meta FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            meta = json.loads(row["meta"] or "{}") if row else {}
            meta["metricas"] = metricas
            c.execute("UPDATE jobs SET meta = ? WHERE job_id = ?",
                      (json.dumps(meta, ensure_ascii=False), job_id))

    def obter(self, tenant_id, job_id):
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE job_id = ? AND tenant_id = ?",
                            (job_id, tenant_id)).fetchone()
        return _job_dict(row) if row else None

    def itens(self, job_id, status=None, limite=100, offset=0):
        sql = "SELECT * FROM job_items WHERE job_id = ?"
        args: list[Any] = [job_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY indice LIMIT ? OFFSET ?"
        args += [limite, offset]
        with self._conn() as c:
            return [_item_dict(r) for r in c.execute(sql, args).fetchall()]

    def por_idempotencia(self, tenant_id, chave):
        with self._conn() as c:
            row = c.execute("SELECT job_id FROM jobs WHERE tenant_id = ? AND idempotency_key = ?",
                            (tenant_id, chave)).fetchone()
        return row["job_id"] if row else None


class PostgresJobStore(JobStore):
    """Postgres/Supabase em schema próprio (default `boleto_api`)."""

    def __init__(self, dsn: str, schema: str | None = None) -> None:
        import psycopg  # noqa: F401 — validação de dependência

        self.dsn = dsn
        schema = schema or os.environ.get("CREDENTIAL_DB_SCHEMA", "boleto_api")
        if not re.fullmatch(r"[a-z0-9_]+", schema):
            raise ValueError("CREDENTIAL_DB_SCHEMA inválido (use [a-z0-9_])")
        self.jobs = f'"{schema}".jobs'
        self.items = f'"{schema}".job_items'
        with self._conn() as c:
            c.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            c.execute(_SCHEMA_JOB.replace("CREATE TABLE IF NOT EXISTS jobs",
                                          f"CREATE TABLE IF NOT EXISTS {self.jobs}"))
            c.execute(_SCHEMA_ITEM.replace("CREATE TABLE IF NOT EXISTS job_items",
                                           f"CREATE TABLE IF NOT EXISTS {self.items}"))
            c.execute(_SCHEMA_IDEMP.replace("ON jobs", f"ON {self.jobs}"))

    def _conn(self):
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True)

    def criar(self, job, itens) -> None:
        with self._conn() as c:
            c.execute(
                f"INSERT INTO {self.jobs} (job_id, tenant_id, tipo, status, total, completed,"
                " failed, idempotency_key, criado_em, atualizado_em, meta)"
                " VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s)",
                (job["job_id"], job["tenant_id"], job["tipo"], job["status"], job["total"],
                 job.get("idempotency_key"), job["criado_em"], job["criado_em"],
                 json.dumps(job.get("meta") or {})),
            )
            for i in itens:
                c.execute(
                    f"INSERT INTO {self.items} (job_id, item_id, indice, status, resultado)"
                    " VALUES (%s, %s, %s, %s, NULL)",
                    (job["job_id"], i["item_id"], i["indice"], ITEM_PENDING))

    def atualizar_status(self, job_id, status, **contadores) -> None:
        campos = ", ".join(f"{k} = %s" for k in contadores)
        sets = f"status = %s, atualizado_em = %s{', ' + campos if campos else ''}"
        with self._conn() as c:
            c.execute(f"UPDATE {self.jobs} SET {sets} WHERE job_id = %s",
                      (status, agora(), *contadores.values(), job_id))

    def concluir_item(self, job_id, item_id, status, resultado) -> None:
        with self._conn() as c:
            c.execute(f"UPDATE {self.items} SET status = %s, resultado = %s"
                      " WHERE job_id = %s AND item_id = %s",
                      (status, json.dumps(resultado, ensure_ascii=False), job_id, item_id))

    def salvar_metricas(self, job_id, metricas) -> None:
        with self._conn() as c:
            row = c.execute(f"SELECT meta FROM {self.jobs} WHERE job_id = %s",
                            (job_id,)).fetchone()
            meta = json.loads((row[0] if row else None) or "{}")
            meta["metricas"] = metricas
            c.execute(f"UPDATE {self.jobs} SET meta = %s WHERE job_id = %s",
                      (json.dumps(meta, ensure_ascii=False), job_id))

    def obter(self, tenant_id, job_id):
        with self._conn() as c:
            row = c.execute(f"SELECT * FROM {self.jobs} WHERE job_id = %s AND tenant_id = %s",
                            (job_id, tenant_id)).fetchone()
            cols = [d[0] for d in c.description] if row else []
        return _job_dict(dict(zip(cols, row))) if row else None

    def itens(self, job_id, status=None, limite=100, offset=0):
        sql = f"SELECT * FROM {self.items} WHERE job_id = %s"
        args: list[Any] = [job_id]
        if status:
            sql += " AND status = %s"
            args.append(status)
        sql += " ORDER BY indice LIMIT %s OFFSET %s"
        args += [limite, offset]
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
            cols = [d[0] for d in c.description]
        return [_item_dict(dict(zip(cols, r))) for r in rows]

    def por_idempotencia(self, tenant_id, chave):
        with self._conn() as c:
            row = c.execute(f"SELECT job_id FROM {self.jobs}"
                            " WHERE tenant_id = %s AND idempotency_key = %s",
                            (tenant_id, chave)).fetchone()
        return row[0] if row else None


def _job_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["meta"] = json.loads(d.get("meta") or "{}")
    return d


def _item_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    if d.get("resultado"):
        d["resultado"] = json.loads(d["resultado"])
    return d


def get_job_store() -> JobStore:
    """Supabase/Postgres se houver DSN; senão SQLite (mesmo padrão do cofre)."""
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        return PostgresJobStore(dsn)
    return SqliteJobStore(os.environ.get("JOB_DB_PATH")
                          or os.environ.get("CREDENTIAL_DB_PATH", "credentials.db"))
