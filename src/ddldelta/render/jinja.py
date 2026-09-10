# Optional template-driven renderer (requires the 'jinja' extra). The USER's
# Jinja template decides what each file contains - e.g. calling macros that
# parametrize COPY INTO workloads - while ddldelta supplies the schema/plan
# context. Outputs are REGENERABLE artifacts: unlike the migration renderers
# this one overwrites without the exists-guard; rendering into a folder whose
# files a deploy tool checksums makes checksum discipline the caller's job.

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ddldelta.errors import GenerationError
from ddldelta.model import Schema
from ddldelta.plan import MigrationPlan
from ddldelta.render.sql import statement


def _import_jinja2() -> Any:
    """Raw import seam, factored out so a test can monkeypatch it to raise
    ImportError - simulating the optional dependency being absent - without
    actually uninstalling jinja2."""
    import jinja2
    return jinja2


def _require_jinja2() -> Any:
    try:
        return _import_jinja2()
    except ImportError:
        raise GenerationError(
            "jinja2 is not installed - install the 'jinja' extra "
            "(ddldelta[jinja]) to use JinjaRenderer") from None


@dataclass(frozen=True)
class JinjaRenderer:
    """Renders a MigrationPlan or a Schema through a user-supplied Jinja
    template. `searchpath` is a FileSystemLoader root so the template can
    `{% import %}` sibling macro files (e.g. a shared COPY INTO macro).
    `filename_template` is itself a (tiny) Jinja template, rendered with the
    same context as the body template. A plain subdirectory INSIDE
    target_dir (e.g. "sub/{{ table.name }}.sql") is allowed and created on
    demand; a rendered name that is empty or escapes target_dir (table/
    column identifiers come from vendor-controlled DDL, so this is not
    trusted input - e.g. a table literally named "../../evil") raises
    GenerationError instead of being written.
    """

    target_dir: Path
    searchpath: Path
    template: str
    filename_template: str
    meta_ddl: Sequence[str] = ()
    vars: Mapping[str, Any] = field(default_factory=dict)

    def _environment(self) -> Any:
        jinja2 = _require_jinja2()
        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.searchpath)),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )

    def _render(self, env: Any, source: str, from_file: bool, context: Mapping[str, Any]) -> str:
        jinja2 = _require_jinja2()
        try:
            tmpl = env.get_template(source) if from_file else env.from_string(source)
            result: str = tmpl.render(context)
            return result
        except jinja2.TemplateError as error:
            raise GenerationError(f"jinja template {self.template!r}: {error}") from error

    def _target(self, filename: str) -> Path:
        """Resolves a rendered filename against target_dir, refusing an
        empty name or one that escapes target_dir. A plain subdirectory
        INSIDE target_dir is fine and gets created by `_write`."""
        if not filename.strip():
            raise GenerationError(
                f"filename template {self.filename_template!r} rendered an empty file name")
        target = (self.target_dir / filename).resolve()
        if not target.is_relative_to(self.target_dir.resolve()):
            raise GenerationError(
                f"rendered file name {filename!r} escapes the target directory "
                f"{self.target_dir} - refusing to write")
        return target

    def _write(self, env: Any, context: dict[str, Any]) -> Path:
        filename = self._render(env, self.filename_template, from_file=False, context=context)
        content = self._render(env, self.template, from_file=True, context=context)
        target = self._target(filename)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as error:
            raise GenerationError(f"cannot write {target}: {error}") from error
        return target

    def render(self, plan: MigrationPlan) -> tuple[Path, ...]:
        """Renderer protocol: one file per TablePlan. `critical` and the raw
        (never auto-commented) `statements` are handed to the template -
        presentation of a critical table is the template's decision, not
        this renderer's."""
        env = self._environment()
        written: list[Path] = []
        for table_plan in plan.tables:
            context: dict[str, Any] = {
                "plan": plan,
                "table": table_plan,
                "label": plan.label,
                "comparison": plan.comparison,
                "critical": table_plan.critical,
                "changes": table_plan.changes,
                "statements": [statement(c, self.meta_ddl) for c in table_plan.changes],
                "vars": self.vars,
            }
            written.append(self._write(env, context))
        return tuple(written)

    def render_schema(self, schema: Schema, label: str = "") -> tuple[Path, ...]:
        """Schema-driven scaffolding: one file per table of the CURRENT
        schema (no diff involved) - e.g. generating a per-table COPY INTO
        script from a macro."""
        env = self._environment()
        written: list[Path] = []
        for name in sorted(schema):
            table = schema[name]
            context: dict[str, Any] = {
                "table": table,
                "columns": [c.name for c in table.columns],
                "column_defs": list(table.columns),
                "key": table.key,
                "label": label,
                "vars": self.vars,
            }
            written.append(self._write(env, context))
        return tuple(written)
