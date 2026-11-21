"""pytest plugin used ONLY at map-build time (never at submission runtime).

Records, per test, facts that line coverage cannot see:
  * which tests/fixtures files the test opened,
  * which Parser/Generator/Tokenizer/Dialect/Expression classes were instantiated
    (as the set of modules defining classes in their MRO).
Written to $MAP_RAW_DIR/<pid>.json when the (worker) process finishes.
"""
import builtins, io, json, os, pathlib

RAW = os.environ.get("MAP_RAW_DIR", "/work/raw")
cur = {"id": None, "phase": None, "cls": None}
opens = {}      # nodeid -> {"call": set, "setup": set}
mods = {}       # nodeid -> set(module names)
untracked = {"opens": set(), "mods": set()}
_class_cache = {}


def _record_class(c):
    m = _class_cache.get(c)
    if m is None:
        m = frozenset(k.__module__ for k in c.__mro__ if k.__module__.startswith("sqlglot"))
        _class_cache[c] = m
    nid = cur["id"]
    target = mods.setdefault(nid, set()) if nid else untracked["mods"]
    target |= m


def _record_open(path):
    try:
        p = os.path.abspath(os.fspath(path)).replace("\\", "/")
    except Exception:
        return
    if "/tests/fixtures/" not in p:
        return
    rel = "tests/fixtures/" + p.split("/tests/fixtures/", 1)[1]
    nid = cur["id"]
    if nid is None:
        untracked["opens"].add(rel)
    else:
        opens.setdefault(nid, {"call": set(), "setup": set()})[
            "setup" if cur["phase"] == "setup" else "call"].add(rel)


_orig_open = builtins.open
def _open(file, *a, **k):
    if isinstance(file, (str, bytes, os.PathLike)):
        _record_open(file)
    return _orig_open(file, *a, **k)
builtins.open = _open
io.open = _open
_orig_popen = pathlib.Path.open
def _popen(self, *a, **k):
    _record_open(self)
    return _orig_popen(self, *a, **k)
pathlib.Path.open = _popen


def _wrap_init(cls):
    orig = cls.__init__
    def init(self, *a, **k):
        _record_class(type(self))
        orig(self, *a, **k)
    cls.__init__ = init


_installed = False


def _install():
    global _installed
    if _installed:
        return
    _installed = True
    import sqlglot.expressions.core as core
    from sqlglot.dialects.dialect import Dialect
    from sqlglot.generator import Generator
    from sqlglot.parser import Parser
    from sqlglot.tokens import Tokenizer
    for c in (core.Expr, Dialect, Generator, Parser, Tokenizer):
        _wrap_init(c)
    # Dialect.get_or_raise may hand back cached instances: record the class too.
    orig = Dialect.get_or_raise.__func__
    def goe(cls, dialect=None):
        r = orig(cls, dialect)
        _record_class(type(r))
        return r
    Dialect.get_or_raise = classmethod(goe)


def pytest_sessionstart(session):
    _install()
    _patch_pool()


def _run_task(name, fn, args, kwargs):
    """Runs inside a spawned pool child: attribute coverage/class use to the submitting test."""
    _install()
    _child_setup()
    cur["id"] = name
    _switch(name + "|run")
    try:
        import pickle
        try:   # arguments were pickled by the parent / unpickled before we got here: redo it
            pickle.loads(pickle.dumps((args, kwargs)))   # inside this test's coverage context
        except Exception:
            pass
        res = fn(*args, **kwargs)
        try:   # the result is pickled by this child and unpickled by the parent's reader thread
            pickle.loads(pickle.dumps(res))
        except Exception:
            pass
        return res
    finally:
        cur["id"] = None
        _switch("")


_child_ready = False


def _child_setup():
    global _child_ready
    if _child_ready:
        return
    _child_ready = True
    import atexit
    atexit.register(_dump)


def _patch_pool():
    """ProcessPoolExecutor children are separate processes; tag each task with the test that
    submitted it so the child's coverage data lands in that test's context."""
    import concurrent.futures as cf
    orig = cf.ProcessPoolExecutor.submit

    def submit(self, fn, /, *args, **kwargs):
        if cur["id"] is None:
            return orig(self, fn, *args, **kwargs)
        return orig(self, _run_task, cur["id"], fn, args, kwargs)
    cf.ProcessPoolExecutor.submit = submit


def _switch(name):
    # pytest 9 subtests reset pytest-cov's context to "", losing everything after the
    # first subtest. We therefore manage coverage contexts ourselves.
    try:
        import coverage
        c = coverage.Coverage.current()
        if c is not None:
            c.switch_context(name)
    except Exception:
        pass


def pytest_collectstart(collector):
    # Code executed while a test MODULE is imported/collected (module and class bodies, parametrize
    # data...) belongs to every test in that module: if it breaks, the whole file errors out.
    if collector.nodeid.endswith(".py"):
        _switch("collect:" + collector.nodeid + "|run")


def pytest_collectreport(report):
    if report.nodeid.endswith(".py"):
        _switch("")


def pytest_runtest_logstart(nodeid, location):
    cur.update(id=nodeid, phase="setup")
    _switch(nodeid + "|run")


def pytest_runtest_logreport(report):
    if cur["id"] is not None:
        _switch(cur["id"] + "|run")


def pytest_runtest_call(item):
    cur["phase"] = "call"


def pytest_runtest_teardown(item):
    cur["phase"] = "teardown"


def pytest_runtest_logfinish(nodeid, location):
    cur.update(id=None, phase=None)
    _switch("")


def pytest_sessionfinish(session, exitstatus):
    _dump()


def _dump():
    os.makedirs(RAW, exist_ok=True)
    out = {
        "opens": {k: {p: sorted(v) for p, v in d.items()} for k, d in opens.items()},
        "mods": {k: sorted(v) for k, v in mods.items()},
        "untracked_opens": sorted(untracked["opens"]),
    }
    with _orig_open(os.path.join(RAW, f"{os.getpid()}.json"), "w") as f:
        json.dump(out, f)
