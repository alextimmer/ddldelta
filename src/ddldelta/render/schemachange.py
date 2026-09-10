# The schemachange output format. Thin over write_plan - naming, fuse and
# guard are shared file mechanics; schemachange accepts arbitrary version
# labels (delivery names like 2026Q3), so no validation is needed here.
# The per-supplier schemachange-config.yml is generator.py's concern (it is
# consumer configuration, not migration content).

from dataclasses import dataclass
from pathlib import Path

from ddldelta.plan import MigrationPlan
from ddldelta.render.files import (
    CRITICAL_FILE_HEADER,
    CRITICAL_SUMMARY_HEADER,
    META_PREFIX,
    PROVENANCE_TEMPLATE,
    write_plan,
)


@dataclass(frozen=True)
class SchemachangeRenderer:
    target_dir: Path
    generated_by: str
    meta_ddl: tuple[str, ...] = ()
    meta_prefix: str = META_PREFIX
    provenance_template: str = PROVENANCE_TEMPLATE
    file_header: str = CRITICAL_FILE_HEADER
    summary_header: str = CRITICAL_SUMMARY_HEADER

    def render(self, plan: MigrationPlan) -> tuple[Path, ...]:
        return write_plan(
            plan, self.target_dir, self.generated_by,
            meta_ddl=self.meta_ddl, meta_prefix=self.meta_prefix,
            provenance_template=self.provenance_template,
            file_header=self.file_header, summary_header=self.summary_header)
