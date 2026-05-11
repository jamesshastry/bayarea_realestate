"""Stdlib-only ``trace``-based coverage measurement for ``packages/finance/``.

This is a developer convenience for environments where the official
toolchain (``uv sync && uv run pytest --cov=packages/finance --cov-fail-under=95``)
cannot be invoked. It uses ``trace`` from the standard library plus
in-test stubs of ``pytest`` and ``hypothesis`` to drive every test
function once.

CI uses the official toolchain — this script is *not* the gate.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
import trace
import types

# ── stub pytest ────────────────────────────────────────────────────────────
pt = types.ModuleType("pytest")


class _Marker:
    def __getattr__(self, name):
        def deco(*a, **kw):
            def wrap(fn):
                return fn

            if a and callable(a[0]):
                return a[0]
            return wrap

        return deco


pt.mark = _Marker()


class _Raises:
    def __init__(self, exc, match=None):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, tb):
        if exc_type is None:
            raise AssertionError(f"expected {self.exc}")
        return issubclass(exc_type, self.exc)


def raises(exc, match=None):
    return _Raises(exc, match)


pt.raises = raises


def parametrize(name, vals):
    def deco(fn):
        names = [n.strip() for n in name.split(",")]

        def wrapped():
            for v in vals:
                if isinstance(v, tuple) and len(names) > 1:
                    fn(*v)
                else:
                    fn(v)

        return wrapped

    return deco


pt.parametrize = parametrize
sys.modules["pytest"] = pt

# ── stub hypothesis ────────────────────────────────────────────────────────
hyp = types.ModuleType("hypothesis")


def settings(*a, **kw):
    def deco(fn):
        return fn

    return deco


def given(*a, **kw):
    def deco(fn):
        def wrapped(*aa, **kk):
            pass

        return wrapped

    return deco


hyp.given = given
hyp.settings = settings


class HealthCheck:
    too_slow = "too_slow"
    function_scoped_fixture = "function_scoped_fixture"


hyp.HealthCheck = HealthCheck
strategies = types.ModuleType("hypothesis.strategies")


def _stub(*a, **kw):
    return None


for name in ("decimals", "integers", "sampled_from", "one_of", "none", "text"):
    setattr(strategies, name, _stub)
hyp.strategies = strategies
sys.modules["hypothesis"] = hyp
sys.modules["hypothesis.strategies"] = strategies

# Make ``finance`` importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PACKAGES = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _PACKAGES)


def run_all() -> None:
    modules = [
        "finance.tests.test_tax_rules",
        "finance.tests.test_affordability",
        "finance.tests.test_timing",
        "finance.tests.test_cost_of_waiting",
        "finance.tests.test_confidence",
        "finance.tests.test_golden",
    ]
    for mname in modules:
        m = importlib.import_module(mname)
        for name, fn in inspect.getmembers(m, inspect.isfunction):
            if name.startswith("test_"):
                try:
                    fn()
                except TypeError:
                    pass  # parametrize stub mismatch (handled below)
                except Exception as e:
                    print(f"  {mname}::{name}: {type(e).__name__}: {e}")

    from finance.tests.test_tax_rules import (
        test_min_down_payment_is_defined_and_positive,
    )

    for lt in ("conforming", "high_balance", "jumbo", "fha"):
        test_min_down_payment_is_defined_and_positive(lt)

    from finance.confidence import SAMPLE_THRESHOLDS
    from finance.tests.test_confidence import (
        test_every_metric_in_threshold_table_high_band_returns_full_score as t1,
    )

    for n in SAMPLE_THRESHOLDS:
        t1(n)

    from finance.tests.test_golden import test_golden_row

    for i in range(100):
        test_golden_row(i)


tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
tracer.runfunc(run_all)
results = tracer.results()

source_files = [
    "packages/finance/__init__.py",
    "packages/finance/_types.py",
    "packages/finance/affordability.py",
    "packages/finance/confidence.py",
    "packages/finance/cost_of_waiting.py",
    "packages/finance/phase_weights.py",
    "packages/finance/tax_rules.py",
    "packages/finance/timing.py",
]


def executable_lines(path: str) -> set[int]:
    """Return the set of executable lines in ``path`` using the AST.

    Docstrings (``Expr(Constant(string))`` at the head of a module,
    function, or class) are excluded — they're "executed" in the sense
    that the constant is evaluated, but ``trace`` doesn't reliably
    record them and counting them inflates the denominator artificially.
    Pure type-annotation statements (``ann_assign`` with no value) are
    also excluded.
    """

    import ast

    src = open(path).read()
    src_lines = src.splitlines()
    tree = ast.parse(src, path)
    docstring_lines: set[int] = set()
    pragma_lines: set[int] = set()
    for i, line in enumerate(src_lines, start=1):
        if "pragma: no cover" in line:
            pragma_lines.add(i)

    def collect_docstring(body):
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            if isinstance(body[0].value.value, str):
                # Mark every line of the docstring as a docstring line.
                start = body[0].lineno
                end = body[0].end_lineno or start
                for ln in range(start, end + 1):
                    docstring_lines.add(ln)

    # Module-level docstring.
    collect_docstring(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            collect_docstring(node.body)

    # First pass: collect every line covered by *any* pragma'd statement.
    excluded_lines: set[int] = set(pragma_lines)
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            ln = getattr(node, "lineno", None)
            end_ln = getattr(node, "end_lineno", ln) or ln
            if ln is None:
                continue
            stmt_range = set(range(ln, (end_ln or ln) + 1))
            if stmt_range & pragma_lines:
                excluded_lines |= stmt_range

    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            if isinstance(node, ast.AnnAssign) and node.value is None:
                continue  # type-annotation only
            ln = getattr(node, "lineno", None)
            if ln is None or ln in docstring_lines or ln in excluded_lines:
                continue
            lines.add(ln)
    return lines


total_exec = total_hit = 0
print()
print(f"{'file':<55} {'exec':>6} {'hit':>6} {'%':>6}")
print("-" * 80)
per_file = []
for f in source_files:
    abs_f = os.path.abspath(f)
    exec_lines = executable_lines(abs_f)
    hit_lines = {
        ln
        for (fn, ln), cnt in results.counts.items()
        if os.path.abspath(fn) == abs_f and cnt > 0
    }
    actual_hit = exec_lines & hit_lines
    n_exec = len(exec_lines)
    n_hit = len(actual_hit)
    pct = 100 * n_hit / n_exec if n_exec else 100
    miss = sorted(exec_lines - actual_hit)
    per_file.append((f, n_exec, n_hit, pct, miss))
    print(f"{f:<55} {n_exec:>6} {n_hit:>6} {pct:>5.1f}%")
    total_exec += n_exec
    total_hit += n_hit
print("-" * 80)
print(
    f"{'TOTAL':<55} {total_exec:>6} {total_hit:>6} {100 * total_hit / total_exec:>5.1f}%"
)

print()
print("=== misses per file ===")
for f, _n_exec, _n_hit, _pct, miss in per_file:
    if miss:
        print(f"{f}: missing {miss}")
