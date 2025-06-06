"""Offline control suite."""
from pathlib import Path

from deode.suites.base import EcflowSuiteTask, SuiteDefinition


class SurfexSuiteDefinitionDTAnalysedForcingControl(SuiteDefinition):
    """Surfex suite."""

    def __init__(
        self,
        config,
        dry_run=False,
    ):
        """Initialize a SurfexSuite object.

        Args:
        ----
            suite_name (str): Name of the suite
            config (ParsedConfig): Parsed configuration
            dry_run (str, optional): Dry run. Defaults to False

        Raises:
        ------
            NotImplementedError: Not implmented

        """
        SuiteDefinition.__init__(self, config, dry_run=dry_run)

        template = Path(__file__).parent.resolve() / "../templates/ecflow/requeue.py"
        template = template.as_posix()

        run_cmd = self.config["suite_control.run_cmd"]
        start_offline_sfx = EcflowSuiteTask(
            "StartOfflineSfx",
            self.suite,
            config,
            self.task_settings,
            self.ecf_files,
            variables={"ARGS": f"run_cmd={run_cmd}"},
            input_template=template,
        )
        start_offline_sfx.ecf_node.add_time("03:00")
