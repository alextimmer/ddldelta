# Flyway output: same versioned-file mechanics as schemachange (write_plan
# shares naming V<label>.<NNNN>__<table>.sql, fuse and exists-guard), but
# Flyway only accepts NUMERIC versions (digits separated by . or _) - a
# delivery label like "2026Q3" must be mapped by the caller. No flyway.conf
# is generated; connection config is the consumer's concern.

import re
from dataclasses import dataclass
from pathlib import Path

from ddldelta.errors import GenerationError
from ddldelta.plan import MigrationPlan
from ddldelta.render.files import (
    CRITICAL_FILE_HEADER,
    CRITICAL_SUMMARY_HEADER,
    META_PREFIX,
    PROVENANCE_TEMPLATE,
    write_plan,
)

_FLYWAY_VERSION = re.compile(r"^[0-9]+([._][0-9]+)*$")


@dataclass(frozen=True)
class FlywayRenderer:
    target_dir: Path
    generated_by: str
    meta_ddl: tuple[str, ...] = ()
    meta_prefix: str = META_PREFIX
    provenance_template: str = PROVENANCE_TEMPLATE
    file_header: str = CRITICAL_FILE_HEADER
    summary_header: str = CRITICAL_SUMMARY_HEADER

    def render(self, plan: MigrationPlan) -> tuple[Path, ...]:
        if not _FLYWAY_VERSION.match(plan.label):
            raise GenerationError(
                f"'{plan.label}' is not a valid Flyway version (digits "
                "separated by . or _) - map the delivery label to a Flyway "
                "version before rendering.")
        return write_plan(plan, self.target_dir, self.generated_by,
                          meta_ddl=self.meta_ddl, meta_prefix=self.meta_prefix,
                          provenance_template=self.provenance_template,
                          file_header=self.file_header,
                          summary_header=self.summary_header)
