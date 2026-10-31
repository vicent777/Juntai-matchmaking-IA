"""Leitura explícita e minimizada do PostgreSQL, sem comandos de escrita."""

import os
import re
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from app.supervised.features import INV_NUM, INV_CAT, INV_MULTI, STA_NUM, STA_CAT, STA_MULTI
from app.supervised.schemas import InvestorProfile, StartupProfile


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def connection(env_file: Path):
    import psycopg2
    from dotenv import dotenv_values

    values = {**dotenv_values(env_file), **os.environ}
    if not all(values.get(k) for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")):
        raise ValueError("Defina DB_HOST, DB_PORT, DB_USER, DB_PASSWORD e DB_NAME; valores nunca são impressos.")
    conn = psycopg2.connect(
        host=values["DB_HOST"], port=int(values["DB_PORT"]), user=values["DB_USER"],
        password=values["DB_PASSWORD"], dbname=values["DB_NAME"], connect_timeout=10,
        options="-c default_transaction_read_only=on", application_name="juntai_synthetic_read_only",
    )
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    return conn


def database_state(cursor):
    """Hashes calculados no servidor: nenhum conteúdo pessoal é exportado aqui."""
    from psycopg2 import sql

    cursor.execute("SHOW transaction_read_only")
    if cursor.fetchone()[0] != "on":
        raise ValueError("A fonte exige transação somente de leitura.")
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    tables = [r[0] for r in cursor.fetchall()]
    state = {}
    for table in tables:
        cursor.execute(sql.SQL("SELECT count(*),md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text) h FROM public.{} t) s").format(sql.Identifier(table)))
        count, digest = cursor.fetchone()
        state[table] = {"count": count, "digest": digest}
    cursor.execute("SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
    columns = cursor.fetchall()
    cursor.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname")
    indexes = cursor.fetchall()
    cursor.execute("SELECT c.relname,x.conname,pg_get_constraintdef(x.oid) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,x.conname")
    constraints = cursor.fetchall()
    cursor.execute("SELECT t.typname,array_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_type t JOIN pg_enum e ON t.oid=e.enumtypid GROUP BY t.typname ORDER BY t.typname")
    return {"tables": state, "columns": columns, "indexes": indexes, "constraints": constraints, "enums": cursor.fetchall()}


def read_profiles(cursor, table, model, numeric, categorical, arrays):
    from psycopg2 import sql

    fields = list(dict.fromkeys(("id", *numeric, *categorical, *arrays)))
    if table == "startups":
        fields.append("statusModeracao")
    projections = []
    for field in fields:
        column = sql.SQL("p.{}").format(sql.Identifier(snake(field)))
        if field in arrays:
            column += sql.SQL("::text[]")
        projections.append(column)
    cursor.execute(sql.SQL("SELECT {},p.status_moderacao,u.ativo,u.tipo_perfil,u.id FROM public.{} p JOIN public.usuarios u ON u.id=p.usuario_id ORDER BY p.id").format(sql.SQL(",").join(projections), sql.Identifier(table)))
    profiles, excluded, present = [], Counter(), Counter()
    raw = cursor.fetchall()
    role = "investidor" if table == "investidores" else "startup"
    for row in raw:
        profile = dict(zip(fields, row[:len(fields)]))
        status, active, actual_role, user_id = row[len(fields):]
        if status != "aprovado" or not active or actual_role != role:
            excluded["inelegivel"] += 1
            continue
        # Sem imputação ou conversão silenciosa de enums legados.
        profile["usuario"] = {"id": str(user_id), "ativo": active}
        profile["id"] = str(profile["id"])
        try:
            validated = model.model_validate(profile)
        except ValidationError as exc:
            excluded["contrato_invalido"] += 1
            for error in exc.errors(include_input=False, include_url=False):
                excluded["campo_invalido:" + str(error["loc"][0])] += 1
            continue
        # Mínimo explícito; os demais campos ausentes continuam ausentes nas features.
        sufficient = (validated.tipoInvestidor is not None and bool(validated.segmentosInteresse) and bool(validated.estagiosInteresse)) if role == "investidor" else all((validated.segmento, validated.estagio, validated.modeloNegocio))
        if not sufficient:
            excluded["informacao_insuficiente"] += 1
            continue
        profiles.append(validated)
        for name in fields:
            value = getattr(validated, name)
            if value is not None and value != []:
                present[name] += 1
    return profiles, {"lidos": len(raw), "aproveitados": len(profiles), "descartados": len(raw) - len(profiles), "motivos": dict(excluded), "campos_preenchidos": dict(sorted(present.items()))}


def load_source(env_file: Path):
    conn = connection(env_file)
    try:
        with conn.cursor() as cursor:
            state = database_state(cursor)
            investors, iq = read_profiles(cursor, "investidores", InvestorProfile, INV_NUM, INV_CAT, INV_MULTI)
            startups, sq = read_profiles(cursor, "startups", StartupProfile, STA_NUM, STA_CAT, STA_MULTI)
        return investors, startups, {"investidores": iq, "startups": sq}, state
    finally:
        conn.rollback()
        conn.close()


def verify_source(env_file: Path, before):
    conn = connection(env_file)
    try:
        with conn.cursor() as cursor:
            after = database_state(cursor)
        if after != before:
            raise ValueError("O estado da fonte mudou durante a execução; verificar outros processos antes de aceitar o lote.")
        return True
    finally:
        conn.rollback()
        conn.close()
