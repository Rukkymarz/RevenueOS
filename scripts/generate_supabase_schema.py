"""Render the existing ORM schema as PostgreSQL DDL, without connecting to a DB.

One-time migration authoring helper. Does not replace Alembic or apply changes.
"""
import sys
from pathlib import Path
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from revenueos.db import Base
from revenueos import models  # noqa: F401

if __name__ == "__main__":
    dialect = postgresql.dialect()
    statements = ["-- Preserves the existing RevenueOS models; apply only to its isolated project."]
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)) + ";")
        statements.extend(str(CreateIndex(index).compile(dialect=dialect)) + ";" for index in table.indexes)
        statements.append(f"ALTER TABLE public.{table.name} ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;")
        if "created_at" in table.c:
            statements.append(f"ALTER TABLE public.{table.name} ALTER COLUMN created_at SET DEFAULT now();")
    Path(sys.argv[1]).write_text("\n".join(statements), encoding="utf-8")
