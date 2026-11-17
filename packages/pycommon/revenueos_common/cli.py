"""`revenueos` command line.

  revenueos audit verify        walk the hash chain; exit 0 if intact, 2 if tampered
                                (prints the first broken row's seq and id), 1 on error
  revenueos audit export FILE   write the ledger as JSON lines with the chain head hash
"""
import argparse
import json
import sys

from .db import Database, DatabaseError


def audit_verify(db: Database) -> int:
    try:
        broken = db.scalar("SELECT audit_verify() AS broken")
        total = db.scalar("SELECT count(*) AS n FROM audit_log")
    except DatabaseError as e:
        print(f"audit verify: database error: {e.message}", file=sys.stderr)
        return 1
    if broken is None:
        head = db.scalar("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1")
        print(json.dumps({"status": "intact", "rows": total, "head": head}))
        return 0
    row = db.one("SELECT id, seq, actor, action, target, created_at FROM audit_log WHERE seq = $seq::bigint",
                 seq=broken)
    print(json.dumps({"status": "tampered", "rows": total, "first_broken": row}, default=str))
    print(f"audit verify: TAMPERED at seq {broken} (id {row['id'] if row else 'unknown'})", file=sys.stderr)
    return 2


def audit_export(db: Database, path: str) -> int:
    rows = db.rows("SELECT seq, prev_hash, hash, actor, action, target, payload, created_at FROM audit_log ORDER BY seq")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, sort_keys=True) + "\n")
    print(json.dumps({"exported": len(rows), "head": rows[-1]["hash"] if rows else None, "path": path}))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="revenueos")
    sub = p.add_subparsers(dest="cmd", required=True)
    audit = sub.add_parser("audit").add_subparsers(dest="audit_cmd", required=True)
    ver = audit.add_parser("verify")
    exp = audit.add_parser("export")
    exp.add_argument("path")
    for sp in (ver, exp):
        sp.add_argument("--db", help="database name (default $PGDATABASE)")
    args = p.parse_args(argv)
    db = Database(dbname=args.db, actor="cli")
    if args.cmd == "audit" and args.audit_cmd == "verify":
        return audit_verify(db)
    if args.cmd == "audit" and args.audit_cmd == "export":
        return audit_export(db, args.path)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
