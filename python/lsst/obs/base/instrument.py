# This file is part of obs_base.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

__all__ = ("Instrument", "makeExposureRecordFromObsInfo", "makeVisitRecordFromObsInfo",
           "addUnboundedCalibrationLabel")

import os.path
from abc import ABCMeta, abstractmethod

from lsst.daf.butler import TIMESPAN_MIN, TIMESPAN_MAX


class Instrument(metaclass=ABCMeta):
    """Base class for instrument-specific logic for the Gen3 Butler.

    Concrete instrument subclasses should be directly constructable with no
    arguments.
    """

    configPaths = []
    """Paths to config files to read for specific Tasks.

    The paths in this list should contain files of the form `task.py`, for
    each of the Tasks that requires special configuration.
    """

    @property
    @abstractmethod
    def filterDefinitions(self):
        """`~lsst.obs.base.FilterDefinitionCollection`, defining the filters
        for this instrument.
        """
        return None

    def __init__(self, *args, **kwargs):
        self.filterDefinitions.reset()
        self.filterDefinitions.defineFilters()

    @classmethod
    @abstractmethod
    def getName(cls):
        raise NotImplementedError()

    @abstractmethod
    def getCamera(self):
        """Retrieve the cameraGeom representation of this instrument.

        This is a temporary API that should go away once obs_ packages have
        a standardized approach to writing versioned cameras to a Gen3 repo.
        """
        raise NotImplementedError()

    @abstractmethod
    def register(self, registry):
        """Insert instrument, physical_filter, and detector entries into a
        `Registry`.
        """
        raise NotImplementedError()

    def _registerFilters(self, registry):
        """Register the physical and abstract filter Dimension relationships.
        This should be called in the ``register`` implementation.

        Parameters
        ----------
        registry : `lsst.daf.butler.core.Registry`
            The registry to add dimensions to.
        """
        for filter in self.filterDefinitions:
            # fix for undefined abstract filters causing trouble in the registry:
            if filter.abstract_filter is None:
                abstract_filter = filter.physical_filter
            else:
                abstract_filter = filter.abstract_filter

            registry.insertDimensionData("physical_filter",
                                         {"instrument": self.getName(),
                                          "name": filter.physical_filter,
                                          "abstract_filter": abstract_filter
                                          })

    @abstractmethod
    def getRawFormatter(self, dataId):
        """Return the Formatter class that should be used to read a particular
        raw file.

        Parameters
        ----------
        dataId : `DataCoordinate`
            Dimension-based ID for the raw file or files being ingested.

        Returns
        -------
        formatter : `Formatter` class
            Class to be used that reads the file into an
            `lsst.afw.image.Exposure` instance.
        """
        raise NotImplementedError()

    @abstractmethod
    def writeCuratedCalibrations(self, butler):
        """Write human-curated calibration Datasets to the given Butler with
        the appropriate validity ranges.

        This is a temporary API that should go away once obs_ packages have
        a standardized approach to this problem.
        """
        raise NotImplementedError()

    def applyConfigOverrides(self, name, config):
        """Apply instrument-specific overrides for a task config.

        Parameters
        ----------
        name : `str`
            Name of the object being configured; typically the _DefaultName
            of a Task.
        config : `lsst.pex.config.Config`
            Config instance to which overrides should be applied.
        """
        for root in self.configPaths:
            path = os.path.join(root, f"{name}.py")
            if os.path.exists(path):
                config.load(path)


def makeExposureRecordFromObsInfo(obsInfo, universe):
    """Construct an exposure DimensionRecord from
    `astro_metadata_translator.ObservationInfo`.

    Parameters
    ----------
    obsInfo : `astro_metadata_translator.ObservationInfo`
        A `~astro_metadata_translator.ObservationInfo` object corresponding to
        the exposure.
    universe : `DimensionUniverse`
        Set of all known dimensions.

    Returns
    -------
    record : `DimensionRecord`
        A record containing exposure metadata, suitable for insertion into
        a `Registry`.
    """
    dimension = universe["exposure"]
    return dimension.RecordClass.fromDict({
        "instrument": obsInfo.instrument,
        "id": obsInfo.exposure_id,
        "name": obsInfo.observation_id,
        "group": obsInfo.exposure_group,
        "datetime_begin": obsInfo.datetime_begin,
        "datetime_end": obsInfo.datetime_end,
        "exposure_time": obsInfo.exposure_time.to_value("s"),
        "dark_time": obsInfo.dark_time.to_value("s"),
        "observation_type": obsInfo.observation_type,
        "physical_filter": obsInfo.physical_filter,
        "visit": obsInfo.visit_id,
    })


def makeVisitRecordFromObsInfo(obsInfo, universe, *, region=None):
    """Construct a visit `DimensionRecord` from
    `astro_metadata_translator.ObservationInfo`.

    Parameters
    ----------
    obsInfo : `astro_metadata_translator.ObservationInfo`
        A `~astro_metadata_translator.ObservationInfo` object corresponding to
        the exposure.
    universe : `DimensionUniverse`
        Set of all known dimensions.
    region : `lsst.sphgeom.Region`, optional
        Spatial region for the visit.

    Returns
    -------
    record : `DimensionRecord`
        A record containing visit metadata, suitable for insertion into a
        `Registry`.
    """
    dimension = universe["visit"]
    return dimension.RecordClass.fromDict({
        "instrument": obsInfo.instrument,
        "id": obsInfo.visit_id,
        "name": obsInfo.observation_id,
        "datetime_begin": obsInfo.datetime_begin,
        "datetime_end": obsInfo.datetime_end,
        "exposure_time": obsInfo.exposure_time.to_value("s"),
        "physical_filter": obsInfo.physical_filter,
        "region": region,
    })


def addUnboundedCalibrationLabel(registry, instrumentName):
    """Add a special 'unbounded' calibration_label dimension entry for the
    given camera that is valid for any exposure.

    If such an entry already exists, this function just returns a `DataId`
    for the existing entry.

    Parameters
    ----------
    registry : `Registry`
        Registry object in which to insert the dimension entry.
    instrumentName : `str`
        Name of the instrument this calibration label is associated with.

    Returns
    -------
    dataId : `DataId`
        New or existing data ID for the unbounded calibration.
    """
    d = dict(instrument=instrumentName, calibration_label="unbounded")
    try:
        return registry.expandDataId(d)
    except LookupError:
        pass
    entry = d.copy()
    entry["datetime_begin"] = TIMESPAN_MIN
    entry["datetime_end"] = TIMESPAN_MAX
    registry.insertDimensionData("calibration_label", entry)
    return registry.expandDataId(d)
