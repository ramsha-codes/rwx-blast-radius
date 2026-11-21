"""Milestone 8 prototype runtime (profiling builds only; never imported by selector.py).

_isp(site, a, b) == `a is b`, evaluating nothing but the two already-evaluated operands. It only calls `==`
when BOTH operand types are provably free of user-defined equality (builtin value types, or classes whose
__eq__/__ne__ are object's/str's/int's...), so no user code runs. Otherwise the (test, site) pair is recorded
as unsupported and the selector must fall back to coverage.
Records per test: S = sites observed with safe operands, I = sites where `is` and `==` disagreed,
U = sites seen with unsupported operand types. Executions outside a test's call phase (import, collection,
fixtures/setUpClass, untagged subprocesses) are recorded under test "" = site-wide 'unattributed'.
"""
import atexit, builtins, json, os

_OK = set()
_BAD = set()
_BASE_EQ = None
_data = {}
_S = _I = _U = None


def _init():
    global _BASE_EQ
    _BASE_EQ = {object.__eq__, str.__eq__, int.__eq__, float.__eq__, bytes.__eq__}
    _BASE_NE = {object.__ne__, str.__ne__, int.__ne__, float.__ne__, bytes.__ne__}
    globals()["_BASE_NE"] = _BASE_NE
    _OK.update({type(None), bool, int, float, str, bytes})


def _classify(t):
    try:
        ok = t.__eq__ in _BASE_EQ and t.__ne__ in _BASE_NE
    except Exception:
        ok = False
    (_OK if ok else _BAD).add(t)
    return ok


def set_test(name):
    global _S, _I, _U
    key = name or ""
    d = _data.get(key)
    if d is None:
        d = _data[key] = (set(), set(), set())
    _S, _I, _U = d


def _isp(site, a, b):
    r = a is b
    ta = type(a)
    tb = type(b)
    if (ta in _OK or (ta not in _BAD and _classify(ta))) and (tb in _OK or (tb not in _BAD and _classify(tb))):
        if r != (a == b):
            _I.add(site)
        else:
            _S.add(site)
    else:
        _U.add(site)
    return r


def _ispn(site, a, b):
    return not _isp(site, a, b)


def dump():
    d = os.environ.get("ISPROF_DIR")
    if not d or not _data:
        return
    out = {k: {"s": sorted(v[0]), "i": sorted(v[1]), "u": sorted(v[2])} for k, v in _data.items()}
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.getpid()}.tmp")
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, os.path.join(d, f"{os.getpid()}.json"))


def install():
    _init()
    set_test(None)
    builtins._isp = _isp
    builtins._ispn = _ispn
    atexit.register(dump)


# ------------------------------------------------------------------ pytest plugin
def _run_task(name, fn, args, kwargs):
    """Runs inside a spawned pool child: attribute this task to the submitting test."""
    set_test(name)
    try:
        return fn(*args, **kwargs)
    finally:
        set_test(None)


def _patch_pool():
    import concurrent.futures as cf
    orig = cf.ProcessPoolExecutor.submit
    cur = _plugin_state

    def submit(self, fn, /, *args, **kwargs):
        if cur["id"] is None:
            return orig(self, fn, *args, **kwargs)
        return orig(self, _run_task, cur["id"], fn, args, kwargs)
    cf.ProcessPoolExecutor.submit = submit


_plugin_state = {"id": None}


def pytest_sessionstart(session):
    _patch_pool()


def pytest_sessionfinish(session, exitstatus):
    dump()


try:
    import pytest

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(item):
        _plugin_state["id"] = item.nodeid
        set_test(item.nodeid)
        try:
            yield
        finally:
            set_test(None)
            _plugin_state["id"] = None
except ImportError:
    pass
