from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    dsn: str


class PostgreSQLCursor:
    def __init__(self, cursor, *, lastrowid: int | None = None) -> None:
        self.cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class PostgreSQLConnection:
    def __init__(self, raw_connection) -> None:
        self.raw_connection = raw_connection

    def execute(self, sql: str, params: object = ()) -> PostgreSQLCursor:
        postgres_sql = postgres_statement(sql)
        cursor = self.raw_connection.execute(postgres_sql, params or ())
        lastrowid = None
        if re.search(r"\bRETURNING\s+id\b", postgres_sql, flags=re.IGNORECASE):
            row = cursor.fetchone()
            if row is not None:
                lastrowid = int(row["id"] if isinstance(row, Mapping) else row[0])
        return PostgreSQLCursor(cursor, lastrowid=lastrowid)

    def executescript(self, script: str) -> None:
        for statement in split_sql_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self.raw_connection.commit()

    def rollback(self) -> None:
        self.raw_connection.rollback()

    def close(self) -> None:
        self.raw_connection.close()


IDENTITY_TABLES = {
    "video_pricing_rules",
    "admin_audit_logs",
    "api_providers",
    "canvas_conversations",
    "canvas_messages",
    "dialogues",
    "generation_tasks",
    "invite_codes",
    "invite_redemptions",
    "packages",
    "point_ledger",
    "provider_call_logs",
    "pricing_rules",
    "records",
    "users",
}

SCHEMA_TABLE_ORDER = {
    "users": 10,
    "admin_audit_logs": 15,
    "pricing_rules": 20,
    "packages": 30,
    "dialogues": 40,
    "records": 50,
    "generation_tasks": 60,
    "point_ledger": 70,
    "user_settings": 80,
    "app_settings": 90,
    "api_providers": 100,
    "invite_codes": 110,
    "invite_redemptions": 120,
    "canvas_conversations": 130,
    "canvas_messages": 140,
    "canvas_projects": 150,
    "canvas_project_assets": 160,
}


def database_settings_from_mapping(config: Mapping[str, object]) -> DatabaseSettings:
    database_url = str(config.get("DATABASE_URL") or "").strip()
    if database_url:
        scheme = database_url.split(":", 1)[0].lower()
        if scheme in {"postgres", "postgresql"}:
            return DatabaseSettings(backend="postgresql", dsn=database_url)
        if scheme == "sqlite":
            return DatabaseSettings(backend="sqlite", dsn=database_url.removeprefix("sqlite:///"))
        raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")
    return DatabaseSettings(backend="sqlite", dsn=str(config.get("DATABASE") or Path("data/huishi.sqlite3")))


def translate_qmark_placeholders(sql: str) -> str:
    output: list[str] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            output.append(char)
            if in_single and index + 1 < len(sql) and sql[index + 1] == "'":
                output.append(sql[index + 1])
                index += 2
                continue
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            output.append(char)
            in_double = not in_double
            index += 1
            continue
        if char == "?" and not in_single and not in_double:
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def rewrite_insert_or_ignore(sql: str) -> str:
    stripped = sql.strip()
    rewritten = re.sub(r"^INSERT\s+OR\s+IGNORE\s+INTO\s+", "INSERT INTO ", stripped, count=1, flags=re.IGNORECASE)
    if rewritten == stripped:
        return sql
    if re.search(r"\bON\s+CONFLICT\b", rewritten, flags=re.IGNORECASE):
        return rewritten
    return f"{rewritten} ON CONFLICT DO NOTHING"


def add_returning_id_if_needed(sql: str) -> str:
    stripped = sql.strip()
    if re.search(r"\bRETURNING\b", stripped, flags=re.IGNORECASE):
        return sql
    match = re.match(r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", stripped, flags=re.IGNORECASE)
    if not match:
        return sql
    table = match.group(1).lower()
    if table not in IDENTITY_TABLES:
        return sql
    return f"{stripped} RETURNING id"


def postgres_statement(sql: str) -> str:
    return translate_qmark_placeholders(add_returning_id_if_needed(rewrite_insert_or_ignore(sql)))


def postgres_schema_from_sqlite(schema: str) -> str:
    converted = schema.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
    )
    converted = re.sub(r"\bREAL\b", "DOUBLE PRECISION", converted, flags=re.IGNORECASE)
    statements = split_sql_script(converted)
    statements.sort(key=_schema_statement_order)
    return ";\n\n".join(statements) + (";" if statements else "")


def _schema_statement_order(statement: str) -> int:
    match = re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", statement, flags=re.IGNORECASE)
    if match is None:
        return 10_000
    return SCHEMA_TABLE_ORDER.get(match.group(1).lower(), 9_000)


def split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(script):
        char = script[index]
        if char == "'" and not in_double:
            current.append(char)
            if in_single and index + 1 < len(script) and script[index + 1] == "'":
                current.append(script[index + 1])
                index += 2
                continue
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            current.append(char)
            in_double = not in_double
            index += 1
            continue
        if char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
