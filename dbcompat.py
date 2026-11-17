"""
数据库方言兼容层

本地开发：SQLite（config.DB_PATH）
云端部署：PostgreSQL（环境变量 DATABASE_URL，例如 Neon / Supabase 连接串）

对上层保持 sqlite3 的调用习惯：
  conn.execute(sql, params) / cursor / fetchone / fetchall / lastrowid / commit / close
PostgreSQL 下自动完成：
  - ? 占位符转 %s
  - AUTOINCREMENT 转 SERIAL
  - INSERT 自动补 RETURNING id 以支持 lastrowid
  - 字面量 % 转义
"""
import os
import re
import sqlite3

from config import DB_PATH as DB_PATH_SQLITE

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if IS_POSTGRES:
    import psycopg2
    from psycopg2 import pool as pg_pool
    IntegrityError = psycopg2.IntegrityError
    Error = psycopg2.Error
else:
    IntegrityError = sqlite3.IntegrityError
    Error = sqlite3.Error


# ---------------------------- 行对象 ----------------------------
class Row:
    """同时支持按列名和按下标取值，并支持 tuple 解包"""

    __slots__ = ("_keys", "_vals", "_map")

    def __init__(self, keys, vals):
        self._keys = tuple(keys)
        self._vals = tuple(vals)
        self._map = {k: i for i, k in enumerate(self._keys)}

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._vals[key]
        return self._vals[self._map[key]]

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self):
        return list(self._keys)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __repr__(self):
        return "Row(%s)" % dict(zip(self._keys, self._vals))


# ---------------------------- SQL 转换 ----------------------------
_AUTOINC = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.I)
_BLOB = re.compile(r"\bBLOB\b", re.I)
_INSERT_TABLE = re.compile(r"INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
# 这些表没有自增 id 列，不能补 RETURNING id
_NO_ID_TABLES = {"submission_files"}


def _translate(sql, has_params=True):
    """返回 (改写后的 sql, 是否需要读取 RETURNING id)"""
    q = sql
    want_id = False

    if _AUTOINC.search(q):
        q = _AUTOINC.sub("SERIAL PRIMARY KEY", q)

    if _BLOB.search(q):
        q = _BLOB.sub("BYTEA", q)

    q = q.replace("last_insert_rowid()", "lastval()")

    # 有参数时：先转义字面量百分号，再把 ? 换成 %s
    if has_params:
        q = q.replace("%", "%%").replace("?", "%s")

    head = q.lstrip()[:6].upper()
    if head == "INSERT" and "RETURNING" not in q.upper():
        m = _INSERT_TABLE.search(q)
        table = m.group(1).lower() if m else ""
        if table not in _NO_ID_TABLES:
            q = q.rstrip().rstrip(";") + " RETURNING id"
            want_id = True

    return q, want_id


# ---------------------------- 游标 ----------------------------
class _PGCursor:
    def __init__(self, raw):
        self._raw = raw
        self._cols = []
        self._consumed = False
        self.lastrowid = None

    def _sync_cols(self):
        desc = self._raw.description
        self._cols = [d[0] for d in desc] if desc else []

    def execute(self, sql, params=()):
        has_params = params is not None and params != ()
        q, want_id = _translate(sql, has_params)
        self._raw.execute(q, params if has_params else None)
        self._consumed = False
        self.lastrowid = None
        if want_id:
            got = self._raw.fetchone()
            self.lastrowid = got[0] if got else None
            self._consumed = True
        self._sync_cols()
        return self

    def executemany(self, sql, seq):
        q, _ = _translate(sql, True)
        q = q.replace(" RETURNING id", "")
        self._raw.executemany(q, seq)
        self._sync_cols()
        return self

    def _row(self, tup):
        if tup is None:
            return None
        return Row(self._cols, tup)

    def fetchone(self):
        if self._consumed:
            return None
        return self._row(self._raw.fetchone())

    def fetchall(self):
        if self._consumed:
            return []
        return [self._row(t) for t in self._raw.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def rowcount(self):
        return self._raw.rowcount

    def close(self):
        self._raw.close()


# ---------------------------- 连接 ----------------------------
class _PGConn:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        cur = _PGCursor(self._raw.cursor())
        return cur.execute(sql, params)

    def executemany(self, sql, seq):
        cur = _PGCursor(self._raw.cursor())
        return cur.executemany(sql, seq)

    def cursor(self):
        return _PGCursor(self._raw.cursor())

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        try:
            if not self._raw.closed:
                self._raw.rollback()
        except Exception:
            pass
        release(self._raw)


_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        dsn = DATABASE_URL
        _pool = pg_pool.ThreadedConnectionPool(1, 10, dsn)
    return _pool


def release(raw):
    """把连接归还连接池"""
    try:
        if _pool is not None:
            _pool.putconn(raw)
        else:
            raw.close()
    except Exception:
        try:
            raw.close()
        except Exception:
            pass


def connect():
    """获取连接：有 DATABASE_URL 走 PostgreSQL，否则 SQLite"""
    if IS_POSTGRES:
        last_err = None
        for _ in range(3):
            try:
                return _PGConn(_get_pool().getconn())
            except Exception as e:  # Neon 冷启动会短暂拒连
                last_err = e
                import time
                time.sleep(1.5)
        raise last_err
    conn = sqlite3.connect(DB_PATH_SQLITE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table):
    """兼容两种方言的表结构查询"""
    if IS_POSTGRES:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=?", (table,)
        ).fetchall()
        return [r[0] for r in rows]
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]
