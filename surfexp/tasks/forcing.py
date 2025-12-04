"""Forcing task."""
import os
from datetime import timedelta

from deode.datetime_utils import as_timedelta
from deode.logs import logger
from deode.os_utils import deodemakedirs
from pysurfex.cli import create_forcing, cli_modify_forcing
from pysurfex.verification import concat_datasets, converter2ds

from surfexp.tasks.tasks import PySurfexBaseTask


class Forcing(PySurfexBaseTask):
    """Create forcing task."""

    def __init__(self, config):
        """Construct forcing task.

        Args:
            config (dict): Actual configuration dict

        """
        PySurfexBaseTask.__init__(self, config, "Forcing")
        try:
            mode = self.config["task.args.mode"]
        except KeyError:
            mode = "default"
        logger.info("Forcing mode is: {}", mode)
        lmode = mode
        if lmode == "forecast":
            lmode = "default"
        try:
            self.args = self.config[f"forcing.args.{lmode}"].dict()
        except KeyError:
            raise RuntimeError from KeyError
        if mode == "an_forcing":
            self.basetime = self.basetime - self.fcint
        if mode == "default" and self.config["an_forcing.enabled"]:
            self.basetime = self.basetime - self.fcint
        if mode in ("default", "an_forcing"):
            self.duration = self.fcint
        else:
            self.duration = as_timedelta(self.config["general.times.forecast_range"])
            mode = "forecast"
        self.mode = mode

    def execute(self):
        """Execute the forcing task.

        Raises:
            NotImplementedError: _description_

        """
        dtg_start = self.basetime.strftime("%Y%m%d%H")
        dtg_stop = (self.basetime + self.duration).strftime("%Y%m%d%H")

        logger.info("start={} stop={}", dtg_start, dtg_stop)
        forcing_dir = self.config["system.forcing_dir"]
        default_forcing_dir = f"{forcing_dir}/default"
        forcing_dir = f"{forcing_dir}/{self.mode}"
        forcing_dir = self.platform.substitute(forcing_dir, basetime=self.basetime)
        self.exp_file_paths.system_file_paths.update(
            {"default_forcing_dir": default_forcing_dir}
        )
        deodemakedirs(forcing_dir)

        cforcing_filetype = self.soda_settings.get_setting(
            "NAM_IO_OFFLINE#CFORCING_FILETYPE"
        )
        output_format = cforcing_filetype.lower()
        if output_format == "netcdf":
            output = f"{forcing_dir}/FORCING.nc"
            logger.info("Forcing output: {}", output)
        else:
            raise NotImplementedError(output_format)

        self.args.update({"output-filename": output})
        self.args.update({"output-format": output_format})
        self.args.update({"system-file-paths": self.get_exp_file_paths_file()})

        logger.info("args={}", self.args)
        argv = []
        for key, lvalue in self.args.items():
            value = lvalue
            if isinstance(value, str):
                value = self.substitute(value, basetime=self.basetime)
            if isinstance(value, bool):
                if value:
                    argv.append(f"--{key}")
            else:
                argv.append(f"--{key}")
                argv.append(str(value))

        argv += [dtg_start, dtg_stop]
        logger.info("argv={}", " ".join(argv))
        create_forcing(argv=argv)


class ModifyForcing(PySurfexBaseTask):
    """Create modify forcing task."""

    def __init__(self, config):
        """Construct modify forcing task.

        Args:
            config (ParsedObject): Parsed configuration

        """
        PySurfexBaseTask.__init__(self, config, "ModifyForcing")
        try:
            self.mode = self.config["task.args.mode"]
        except KeyError:
            raise RuntimeError from KeyError

        try:
            self.config["forcing.modify_variables"]
        except KeyError:
            self.variables = ["LWdown", "DIR_SWdown"]

    def execute(self):
        """Execute the forcing task."""
        dtg_prev = self.basetime - self.fcint
        logger.debug("modify forcing dtg={} dtg_prev={}", self.basetime, dtg_prev)
        forcing_dir = self.config["system.forcing_dir"]
        forcing_dir = f"{forcing_dir}/{self.mode}"
        input_dir = self.platform.substitute(forcing_dir, basetime=dtg_prev)
        output_dir = self.platform.substitute(forcing_dir, basetime=self.basetime)
        input_file = input_dir + "/FORCING.nc"
        output_file = output_dir + "/FORCING.nc"
        time_step = int(self.fcint.total_seconds()/3600)

        argv = [
            "--input_file",
            input_file,
            "--output_file",
            output_file,
            "--time_step",
            str(time_step),
            time_step,
        ]
        argv = argv + self.variables
        if os.path.exists(output_file) and os.path.exists(input_file):
            cli_modify_forcing(argv=argv)
        else:
            logger.info("Output or input is missing: {}", output_file)


class Interpolate2grid(PySurfexBaseTask):
    """Create modify forcing task."""

    def __init__(self, config):
        """Construct modify forcing task.

        Args:
            config (ParsedObject): Parsed configuration

        """
        PySurfexBaseTask.__init__(self, config, "Interpolate2grid")
        try:
            self.steps = [int(self.config["task.args.step"])]
        except KeyError:
            fc_length = int(int(self.fcint.total_seconds()) / 3600)
            self.steps = range(fc_length)
        try:
            self.mode = self.config["task.args.mode"]
        except KeyError:
            self.mode = "default"
        if self.mode == "an_forcing":
            self.basetime = self.basetime - self.fcint
        self.mars_config = self.config[f"mars.{self.mode}.config"]

    def execute(self):
        """Execute."""
        variables = [
            "surface_geopotential",
            "air_temperature_2m",
            "dew_point_temperature_2m",
            "surface_air_pressure",
            "x_wind_10m",
            "y_wind_10m",
            "precipitation_amount_acc",
            "snowfall_amount_acc",
            "integral_of_surface_downwelling_shortwave_flux_in_air_wrt_time",
            "integral_of_surface_downwelling_longwave_flux_in_air_wrt_time",
        ]

        ncdir = f"{self.platform.get_system_value('casedir')}/grib"
        gribdir = ncdir

        mapping = {
            "surface_geopotential": {"indicatorOfParameter": 129},
            "air_temperature_2m": {"indicatorOfParameter": 167},
            "dew_point_temperature_2m": {"indicatorOfParameter": 168},
            "surface_air_pressure": {"indicatorOfParameter": 134},
            "x_wind_10m": {"indicatorOfParameter": 165},
            "y_wind_10m": {"indicatorOfParameter": 166},
            "precipitation_amount_acc": {
                "indicatorOfParameter": 228,
                "timeRangeIndicator": 4,
            },
            "snowfall_amount_acc": {"indicatorOfParameter": 144, "timeRangeIndicator": 4},
            "integral_of_surface_downwelling_shortwave_flux_in_air_wrt_time": {
                "indicatorOfParameter": 169,
                "timeRangeIndicator": 4,
            },
            "integral_of_surface_downwelling_longwave_flux_in_air_wrt_time": {
                "indicatorOfParameter": 175,
                "timeRangeIndicator": 4,
            },
        }

        for leadtime in self.steps:
            validtime = self.basetime + timedelta(hours=leadtime)
            validtime = validtime.strftime("%Y%m%d%H")
            ofiles = []
            for var in variables:
                try:
                    time_range_indicator = mapping[var]["timeRangeIndicator"]
                except KeyError:
                    time_range_indicator = 0
                indicator_of_parameter = mapping[var]["indicatorOfParameter"]
                output = (
                    f"{ncdir}/{self.mode}/{var}_"
                    + f"{self.basetime.strftime('%Y%m%d%H')}+{leadtime:02d}.nc"
                )
                input_file = (
                    f"{gribdir}/{self.mode}/{self.mars_config}_"
                    + f"{self.basetime.strftime('%Y%m%d%H')}+@LL@.grib1"
                )
                ofiles.append(output)
                argv = [
                    "-g",
                    self.domain_file,
                    "--output",
                    output,
                    "--inputfile",
                    input_file,
                    "--inputtype",
                    "grib1",
                    "--indicatorOfParameter",
                    f"{indicator_of_parameter}",
                    "--levelType",
                    "1",
                    "--level",
                    "0",
                    "--timeRangeIndicator",
                    f"{time_range_indicator}",
                    "--out-variable",
                    var,
                    "--basetime",
                    self.basetime.strftime("%Y%m%d%H"),
                    "--validtime",
                    validtime,
                    "--fcint", "86400",
                ]
                logger.info("converter2ds {}", " ".join(argv))
                converter2ds(argv=argv)

            argv = [
                "-o",
                f"{ncdir}/{self.mode}/{self.mars_config}_{self.basetime.strftime('%Y%m%d%H')}+{leadtime:02d}.nc",
            ]
            argv = argv + ofiles
            concat_datasets(argv=argv)
