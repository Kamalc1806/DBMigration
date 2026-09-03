"""Top-level orchestrator that ties the pipeline together."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .analyzer import AnalysisResult, analyze
from .connectors import build_connector
from .generator import TargetGenerator
from .reporting import render_console, write_excel, write_reports


@dataclass
class MigrationOptions:
    target_engine: str
    source_engine: Optional[str] = None     # required for DDL-file input
    source_file: Optional[str] = None
    source_url: Optional[str] = None
    source_schema: Optional[str] = None      # DB schema/owner for live introspection
    output_dir: str = "migration_output"
    generated_at: str = ""                   # caller supplies a timestamp (scripts can't call Date.now)


@dataclass
class MigrationOutcome:
    analysis: AnalysisResult
    console_text: str
    excel_path: str
    reports: dict
    scripts: dict


class MigrationPlugin:
    """Reusable programmatic entry point (the CLI is a thin wrapper over this)."""

    def __init__(self, options: MigrationOptions):
        self.opt = options

    # -- individual steps (each is independently reusable) ------------------ #
    def extract(self):
        connector = build_connector(
            engine=self.opt.source_engine,
            source_file=self.opt.source_file,
            source_url=self.opt.source_url,
            schema=self.opt.source_schema,
        )
        return connector.extract()

    def run(self) -> MigrationOutcome:
        # 1. get source schema (2 = analyze below)
        schema = self.extract()

        # 2. analyze + map + compatibility
        analysis = analyze(schema, self.opt.target_engine)

        os.makedirs(self.opt.output_dir, exist_ok=True)

        # 3. build target scripts folder tree (3.1 subfolders per object type)
        scripts = TargetGenerator(schema, analysis,
                                  os.path.join(self.opt.output_dir, "target_scripts")).generate()

        # 3.2 Excel of target object state
        excel_path = os.path.join(self.opt.output_dir, "target_object_state.xlsx")
        write_excel(analysis, excel_path)

        # 4. detailed status + effort reports
        reports = write_reports(analysis, os.path.join(self.opt.output_dir, "reports"),
                                generated_at=self.opt.generated_at)

        # tabular console view
        console_text = render_console(analysis)

        return MigrationOutcome(
            analysis=analysis,
            console_text=console_text,
            excel_path=excel_path,
            reports=reports,
            scripts=scripts,
        )
