"""Child process for the tpcds micro-check (run by selector.py under CPU/memory/wall limits, cwd = a /tmp tree whose
sqlglot/ is the PATCHED pinned source). For each given TPC-DS query it repeats the test's pipeline -- parse_one, pickle
round trip, find_tables, execute(schema=TPCDS_SCHEMA), transpile(sql, write="duckdb") -- and compares with the
pristine fingerprints. Stops at the first difference. Prints exactly one JSON line; anything else means "keep".
usage: micro_check.py <profile.json.gz> <comma-separated query ids>"""
import ast
import csv
import gzip
import hashlib
import json
import pickle
import sys


def main() -> None:
    with gzip.open(sys.argv[1], "rt", encoding="utf-8") as fh:
        prof = json.load(fh)
    ids = [int(x) for x in sys.argv[2].split(",") if x]
    from sqlglot import find_tables, parse_one, transpile
    from sqlglot.executor import execute
    from sqlglot.executor.table import Table
    from tests.helpers import FIXTURES_DIR, TPCDS_SCHEMA, load_sql_fixture_pairs

    sqls = list(load_sql_fixture_pairs("optimizer/tpc-ds/tpc-ds.sql"))
    tables: dict = {}

    def load(name):
        path = f"{FIXTURES_DIR}/optimizer/tpc-ds/{name}.csv.gz"
        reader = csv.reader(gzip.open(path, "rt", encoding="utf-8", newline=""), delimiter="|")
        rows, ctypes = [], []
        columns = next(reader)
        for row in reader:
            if not ctypes:
                for v in row:
                    if not v:
                        ctypes.append(str)
                    else:
                        try:
                            ctypes.append(type(ast.literal_eval(v)))
                        except (ValueError, SyntaxError):
                            ctypes.append(str)
            rows.append(tuple(None if (t is not str and v == "") else t(v) for t, v in zip(ctypes, row)))
        return Table(columns=columns, rows=rows)

    for i in ids:
        meta, sql, _ = sqls[i]
        if not meta.get("execute"):
            print(json.dumps({"ok": False, "why": "not-executed-query", "q": i}))
            return
        try:
            duck = transpile(sql, write="duckdb")[0]
        except Exception as e:  # noqa: BLE001 - any exception is an observable difference unless pristine had it
            duck = "EXC:" + type(e).__name__
        try:
            expr = pickle.loads(pickle.dumps(parse_one(sql)))
            tabs = {}
            for t in find_tables(expr):
                if t.name not in tables:
                    tables[t.name] = load(t.name)
                tabs[t.name] = tables[t.name]
            r = execute(expr, schema=TPCDS_SCHEMA, tables=tabs)
            res = hashlib.sha1(repr((list(r.columns), r.rows)).encode()).hexdigest()
        except Exception as e:  # noqa: BLE001
            res = "EXC:" + type(e).__name__
        if [duck, res] != prof["fp"][str(i)]:
            print(json.dumps({"ok": False, "why": "diff", "q": i}))
            return
    print(json.dumps({"ok": True, "n": len(ids)}))


if __name__ == "__main__":
    main()
