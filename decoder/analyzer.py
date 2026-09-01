"""AST 기반 코드 분석.

이 모듈이 하는 일은 "코드에서 학습 대상을 뽑아내는 것"이다.
설명은 하지 않는다. 설명은 LLM의 몫이고, 여기서는 무엇을 설명해야 하는지만 정한다.

핵심 난점은 5주차에서 다루는 그 문제다:
    sorted(GEN_IMAGES_DIR.glob("*.png"))
AST는 "GEN_IMAGES_DIR 이라는 이름의 무언가에 .glob 을 호출했다"까지만 안다.
이게 pathlib.Path.glob 인지는 타입을 알아야 한다.

여기서는 3단 해석을 쓴다.
    1. import 맵      — from pathlib import Path  →  Path = pathlib.Path
    2. 바인딩 추적    — p = Path(...)             →  p 는 pathlib.Path 인스턴스
                        (호출 대상이 '클래스'인지는 런타임에 inspect 로 확인한다)
    3. 어노테이션     — def f(p: Path)            →  p 는 pathlib.Path
해석에 실패하면 unresolved 로 남기고, 근거가 될 만한 단서(receiver_origin)를
같이 실어 LLM 에게 넘긴다. 실패를 감추지 않는 것이 이 도구의 설계 원칙이다.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

from .docs import is_class, module_is_allowed, return_type_of

# ---------------------------------------------------------------------------
# 자료구조
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    """코드에 등장한, 설명이 필요할 수 있는 이름 하나."""

    source: str  # 코드에 쓰인 그대로. 예: "GEN_IMAGES_DIR.glob"
    kind: str  # call | attribute | decorator | context_manager | import
    line: int
    col: int
    qualname: str | None = None  # 해석 성공 시. 예: "pathlib.Path.glob"
    resolution: str = "unresolved"  # import | binding | annotation | builtin | unresolved
    receiver_origin: str | None = None  # 해석 실패 시 LLM 에게 줄 단서

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyntaxFeature:
    """라이브러리가 아니라 '문법' 쪽 학습 대상."""

    feature: str
    label: str
    line: int
    doc_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Analysis:
    symbols: list[Symbol] = field(default_factory=list)
    syntax: list[SyntaxFeature] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols": [s.to_dict() for s in self.symbols],
            "syntax": [s.to_dict() for s in self.syntax],
            "imports": self.imports,
            "error": self.error,
            "unresolved_count": sum(1 for s in self.symbols if s.qualname is None),
        }


# ---------------------------------------------------------------------------
# 문법 요소 → 공식 문서
# ---------------------------------------------------------------------------

_REF = "https://docs.python.org/3/reference"
_TUT = "https://docs.python.org/3/tutorial"

SYNTAX_TABLE: dict[str, tuple[str, str]] = {
    "ListComp": ("리스트 컴프리헨션", f"{_REF}/expressions.html#displays-for-lists-sets-and-dictionaries"),
    "SetComp": ("집합 컴프리헨션", f"{_REF}/expressions.html#displays-for-lists-sets-and-dictionaries"),
    "DictComp": ("딕셔너리 컴프리헨션", f"{_REF}/expressions.html#dictionary-displays"),
    "GeneratorExp": ("제너레이터 표현식", f"{_REF}/expressions.html#generator-expressions"),
    "JoinedStr": ("f-string", f"{_REF}/lexical_analysis.html#f-strings"),
    "NamedExpr": ("월러스 연산자 (:=)", f"{_REF}/expressions.html#assignment-expressions"),
    "Await": ("await 식", f"{_REF}/expressions.html#await-expression"),
    "AsyncWith": ("async with", f"{_REF}/compound_stmts.html#the-async-with-statement"),
    "AsyncFor": ("async for", f"{_REF}/compound_stmts.html#the-async-for-statement"),
    "AsyncFunctionDef": ("async 함수 정의", f"{_REF}/compound_stmts.html#coroutines"),
    "With": ("with 문 (컨텍스트 매니저)", f"{_REF}/compound_stmts.html#the-with-statement"),
    "Lambda": ("람다 식", f"{_REF}/expressions.html#lambda"),
    "IfExp": ("조건 표현식 (삼항)", f"{_REF}/expressions.html#conditional-expressions"),
    "Starred": ("언패킹 (*)", f"{_REF}/expressions.html#expression-lists"),
    "Slice": ("슬라이싱", f"{_REF}/expressions.html#slicings"),
    "Yield": ("yield", f"{_REF}/expressions.html#yield-expressions"),
    "YieldFrom": ("yield from", f"{_REF}/expressions.html#yield-expressions"),
    "Match": ("구조적 패턴 매칭 (match)", f"{_TUT}/controlflow.html#match-statements"),
    "Global": ("global 선언", f"{_REF}/simple_stmts.html#the-global-statement"),
    "Nonlocal": ("nonlocal 선언", f"{_REF}/simple_stmts.html#the-nonlocal-statement"),
}

BUILTIN_NAMES = set(dir(__builtins__)) if isinstance(__builtins__, dict) is False else set(__builtins__.keys())


# ---------------------------------------------------------------------------
# 1단계 — import 수집
# ---------------------------------------------------------------------------


class _ImportCollector(ast.NodeVisitor):
    """이름 → 정규화된 경로 매핑을 만든다."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            self.aliases[local] = target
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None or node.level:  # 상대 임포트는 해석 불가
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self.aliases[local] = f"{node.module}.{alias.name}"
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# 2단계 — 변수 바인딩 추적
# ---------------------------------------------------------------------------


class _BindingCollector(ast.NodeVisitor):
    """변수가 어떤 타입인지 추론한다. 완벽할 필요는 없고, 근거가 있으면 된다."""

    def __init__(self, aliases: dict[str, str]) -> None:
        self.aliases = aliases
        self.types: dict[str, str] = {}  # 변수명 → 정규화 경로
        self.origins: dict[str, str] = {}  # 변수명 → 어디서 왔는지 (해석 실패 시 단서)

    # p = Path("...")  /  client = httpx.AsyncClient()
    def visit_Assign(self, node: ast.Assign) -> None:
        self._bind_from_value(node.targets, node.value)
        self.generic_visit(node)

    # p: Path = ...
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            annotated = self._flatten(node.annotation)
            if annotated:
                resolved = self._resolve_dotted(annotated)
                if resolved:
                    self.types[node.target.id] = resolved
        self.generic_visit(node)

    # with X() as y:  /  async with X() as y:
    def visit_With(self, node: ast.With) -> None:
        self._bind_from_withitems(node.items)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._bind_from_withitems(node.items)
        self.generic_visit(node)

    # def f(p: Path)
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._bind_args(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._bind_args(node)
        self.generic_visit(node)

    # -- 내부 --------------------------------------------------------------

    def _bind_args(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if arg.annotation is None:
                continue
            annotated = self._flatten(arg.annotation)
            if not annotated:
                continue
            resolved = self._resolve_dotted(annotated)
            if resolved:
                self.types[arg.arg] = resolved

    def _bind_from_withitems(self, items: list[ast.withitem]) -> None:
        for item in items:
            if item.optional_vars is None:
                continue
            self._bind_from_value([item.optional_vars], item.context_expr, via_with=True)

    def _bind_from_value(
        self, targets: list[ast.expr], value: ast.expr, via_with: bool = False
    ) -> None:
        # r = await client.get(url)  →  Await 를 벗겨야 Call 이 보인다.
        if isinstance(value, ast.Await):
            value = value.value

        # results = []  /  cache = {}  /  name = "x"  →  리터럴은 타입이 자명하다.
        literal = _literal_type(value)
        if literal:
            for target in targets:
                if isinstance(target, ast.Name):
                    self.types[target.id] = literal
            return

        if not isinstance(value, ast.Call):
            return
        callee = self._flatten(value.func)
        if not callee:
            return
        resolved = self._resolve_dotted(callee)

        for target in targets:
            if not isinstance(target, ast.Name):
                continue

            if resolved and is_class(resolved):
                # 클래스를 호출했으니 반환값은 그 인스턴스다.
                # 단 with 문에서는 __enter__ 의 반환값이 바인딩되므로 엄밀히는 다르다.
                # 대부분 self 를 반환하지만, 그 가정을 기록은 해둔다.
                self.types[target.id] = resolved
                if via_with:
                    self.origins.setdefault(
                        target.id, f"{resolved}.__enter__() 가 self 를 반환한다고 가정"
                    )
                continue

            # 함수 호출이면 반환 타입을 런타임 어노테이션으로 한 번 더 시도한다.
            returned = return_type_of(resolved) if resolved else None
            if returned:
                self.types[target.id] = returned
                continue

            # 여기까지 오면 타입은 모른다. '어디서 왔는지'만 LLM 에게 넘긴다.
            self.origins[target.id] = resolved or callee

    def _resolve_dotted(self, dotted: str) -> str | None:
        """'Path' 또는 'httpx.AsyncClient' 같은 표기를 정규화 경로로."""
        head, _, tail = dotted.partition(".")
        if head in self.aliases:
            base = self.aliases[head]
            return f"{base}.{tail}" if tail else base
        return None

    @staticmethod
    def _flatten(node: ast.expr) -> str | None:
        """Attribute/Name 체인을 점 표기 문자열로 편다."""
        parts: list[str] = []
        current: ast.expr | None = node
        while True:
            if isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            elif isinstance(current, ast.Name):
                parts.append(current.id)
                break
            elif isinstance(current, ast.Subscript):  # Optional[Path] 같은 경우
                current = current.value
            else:
                return None
        return ".".join(reversed(parts))


# ---------------------------------------------------------------------------
# 3단계 — 심볼 + 문법 요소 수집
# ---------------------------------------------------------------------------


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self, bindings: _BindingCollector) -> None:
        self.b = bindings
        self.symbols: list[Symbol] = []
        self.syntax: list[SyntaxFeature] = []
        self._seen: set[tuple[str, int]] = set()

    # -- 심볼 ---------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _BindingCollector._flatten(node.func)
        if dotted:
            self._add_symbol(dotted, "call", node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # 호출되지 않는 속성 접근 (예: math.pi, df.columns)
        parent_is_call = getattr(node, "_is_callee", False)
        if not parent_is_call:
            dotted = _BindingCollector._flatten(node)
            if dotted:
                self._add_symbol(dotted, "attribute", node.lineno, node.col_offset)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._decorators(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._decorators(node)
        self.generic_visit(node)

    def _decorators(self, node: Any) -> None:
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            dotted = _BindingCollector._flatten(target)
            if dotted:
                self._add_symbol(dotted, "decorator", dec.lineno, dec.col_offset)

    def _add_symbol(self, dotted: str, kind: str, line: int, col: int) -> None:
        key = (dotted, line)
        if key in self._seen:
            return
        self._seen.add(key)

        qualname, resolution, origin = self._resolve(dotted)

        # 해석됐지만 표준/허용 라이브러리가 아니면 학습 대상에서 뺀다.
        # (사용자가 직접 정의한 함수까지 설명할 필요는 없다)
        if qualname is None and resolution == "local":
            return

        self.symbols.append(
            Symbol(
                source=dotted,
                kind=kind,
                line=line,
                col=col,
                qualname=qualname,
                resolution=resolution,
                receiver_origin=origin,
            )
        )

    def _resolve(self, dotted: str) -> tuple[str | None, str, str | None]:
        head, _, tail = dotted.partition(".")

        # (a) import 로 직접 들어온 이름
        if head in self.b.aliases:
            base = self.b.aliases[head]
            return (f"{base}.{tail}" if tail else base), "import", None

        # (b) 추적된 변수 바인딩. 여기가 GEN_IMAGES_DIR.glob 을 푸는 지점이다.
        if head in self.b.types:
            base = self.b.types[head]
            return (f"{base}.{tail}" if tail else base), "binding", None

        # (c) 내장 함수
        if not tail and head in BUILTIN_NAMES:
            return head, "builtin", None

        # (d) 함수 반환값이라 타입은 모르지만 출처는 아는 경우
        if head in self.b.origins:
            return None, "unresolved", f"{head} = {self.b.origins[head]}(...) 의 반환값"

        # (e) 아무 단서도 없음
        if tail:
            return None, "unresolved", f"{head} 의 정의가 이 코드 조각 안에 없음"
        return None, "local", None

    # -- 문법 ---------------------------------------------------------------

    def generic_visit(self, node: ast.AST) -> None:
        name = type(node).__name__
        if name in SYNTAX_TABLE:
            label, url = SYNTAX_TABLE[name]
            line = getattr(node, "lineno", 0)
            if not any(f.feature == name and f.line == line for f in self.syntax):
                self.syntax.append(SyntaxFeature(feature=name, label=label, line=line, doc_url=url))
        super().generic_visit(node)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def analyze_code(code: str) -> dict[str, Any]:
    """코드에서 학습 대상을 추출한다. Tool Calling 에서 호출되는 진입점."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        # 스니펫 하나만 붙여넣는 경우가 흔하므로 식 단독으로도 시도한다.
        try:
            tree = ast.parse(code, mode="eval")
        except SyntaxError:
            return Analysis(error=f"{exc.msg} (line {exc.lineno})").to_dict()

    imports = _ImportCollector()
    imports.visit(tree)

    bindings = _BindingCollector(imports.aliases)
    bindings.visit(tree)

    _mark_callees(tree)

    symbols = _SymbolCollector(bindings)
    symbols.visit(tree)

    symbols.symbols.sort(key=lambda s: (s.line, s.col))
    symbols.syntax.sort(key=lambda s: s.line)

    return Analysis(
        symbols=symbols.symbols,
        syntax=symbols.syntax,
        imports=imports.aliases,
    ).to_dict()


def _literal_type(node: ast.expr) -> str | None:
    """리터럴 대입의 타입. AST 만으로 확실히 알 수 있는 몇 안 되는 경우."""
    if isinstance(node, (ast.List, ast.ListComp)):
        return "list"
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return "dict"
    if isinstance(node, (ast.Set, ast.SetComp)):
        return "set"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.JoinedStr):
        return "str"
    if isinstance(node, ast.Constant):
        return {str: "str", int: "int", float: "float", bool: "bool", bytes: "bytes"}.get(
            type(node.value)
        )
    return None


def _mark_callees(tree: ast.AST) -> None:
    """Call 의 func 로 쓰인 Attribute 를 표시해 중복 수집을 막는다."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node.func._is_callee = True  # type: ignore[attr-defined]


def stdlib_roots() -> set[str]:
    return set(sys.stdlib_module_names)


__all__ = ["analyze_code", "Analysis", "Symbol", "SyntaxFeature", "module_is_allowed"]
