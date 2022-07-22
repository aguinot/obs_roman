# This file is part of obs_base.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (http://www.lsst.org).
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

from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING, Any

import dateutil.parser
from lsst.ip.isr import BrighterFatterKernel, CrosstalkCalib, Defects, Linearizer, PhotodiodeCalib
from lsst.meas.algorithms.simple_curve import Curve

if TYPE_CHECKING:
    import datetime

    import lsst.afw.cameraGeom


def read_one_chip(root: str, chip_name: str, chip_id: int) -> tuple[dict[datetime.datetime, Any], str]:
    """Read data for a particular sensor from the standard format at a
    particular root.

    Parameters
    ----------
    root : `str`
        Path to the top level of the data tree.  This is expected to hold
        directories named after the sensor names.  They are expected to be
        lower case.
    chip_name : `str`
        The name of the sensor for which to read data.
    chip_id : `int`
        The identifier for the sensor in question.

    Returns
    -------
    `dict`
        A dictionary of objects constructed from the appropriate factory class.
        The key is the validity start time as a `datetime` object.
    """
    factory_map = {
        "qe_curve": Curve,
        "defects": Defects,
        "linearizer": Linearizer,
        "crosstalk": CrosstalkCalib,
        "bfk": BrighterFatterKernel,
        "photodiode": PhotodiodeCalib,
    }
    files = []
    extensions = (".ecsv", ".yaml")
    for ext in extensions:
        files.extend(glob.glob(os.path.join(root, chip_name, f"*{ext}")))
    parts = os.path.split(root)
    instrument = os.path.split(parts[0])[1]  # convention is that these reside at <instrument>/<data_name>
    data_name = parts[1]
    if data_name not in factory_map:
        raise ValueError(
            f"Unknown calibration data type, '{data_name}' found. "
            f"Only understand {','.join(k for k in factory_map)}"
        )
    factory = factory_map[data_name]
    data_dict: dict[datetime.datetime, Any] = {}
    for f in files:
        date_str = os.path.splitext(os.path.basename(f))[0]
        valid_start = dateutil.parser.parse(date_str)
        data_dict[valid_start] = factory.readText(f)
        check_metadata(data_dict[valid_start], valid_start, instrument, chip_id, f, data_name)
    return data_dict, data_name


def check_metadata(
    obj: Any, valid_start: datetime.datetime, instrument: str, chip_id: int, filepath: str, data_name: str
) -> None:
    """Check that the metadata is complete and self consistent

    Parameters
    ----------
    obj : object of same type as the factory
        Object to retrieve metadata from in order to compare with
        metadata inferred from the path.
    valid_start : `datetime`
        Start of the validity range for data
    instrument : `str`
        Name of the instrument in question
    chip_id : `int`
        Identifier of the sensor in question
    filepath : `str`
        Path of the file read to construct the data
    data_name : `str`
        Name of the type of data being read

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If the metadata from the path and the metadata encoded
        in the path do not match for any reason.
    """
    md = obj.getMetadata()
    finst = md["INSTRUME"]
    fchip_id = md["DETECTOR"]
    fdata_name = md["OBSTYPE"]
    if not (
        (finst.lower(), int(fchip_id), fdata_name.lower()) == (instrument.lower(), chip_id, data_name.lower())
    ):
        raise ValueError(
            f"Path and file metadata do not agree:\n"
            f"Path metadata: {instrument} {chip_id} {data_name}\n"
            f"File metadata: {finst} {fchip_id} {fdata_name}\n"
            f"File read from : %s\n" % (filepath)
        )


def read_all(
    root: str, camera: lsst.afw.cameraGeom.Camera
) -> tuple[dict[str, dict[datetime.datetime, Any]], str]:
    """Read all data from the standard format at a particular root.

    Parameters
    ----------
    root : `str`
        Path to the top level of the data tree.  This is expected to hold
        directories named after the sensor names.  They are expected to be
        lower case.
    camera : `lsst.afw.cameraGeom.Camera`
        The camera that goes with the data being read.

    Returns
    -------
    dict
        A dictionary of dictionaries of objects constructed with the
        appropriate factory class. The first key is the sensor name lowered,
        and the second is the validity start time as a `datetime` object.

    Notes
    -----
    Each leaf object in the constructed dictionary has metadata associated with
    it. The detector ID may be retrieved from the DETECTOR entry of that
    metadata.
    """
    root = os.path.normpath(root)
    dirs = os.listdir(root)  # assumes all directories contain data
    dirs = [d for d in dirs if os.path.isdir(os.path.join(root, d))]
    data_by_chip = {}
    name_map = {
        det.getName().lower(): det.getName() for det in camera
    }  # we assume the directories have been lowered

    if not dirs:
        raise RuntimeError(f"No data found on path {root}")

    calib_types = set()
    for d in dirs:
        chip_name = os.path.basename(d)
        # Give informative error message if the detector name is not known
        # rather than a simple KeyError
        if chip_name not in name_map:
            detectors = [det for det in camera.getNameIter()]
            max_detectors = 10
            note_str = "knows"
            if len(detectors) > max_detectors:
                # report example subset
                note_str = "examples"
                detectors = detectors[:max_detectors]
            raise RuntimeError(
                f"Detector {chip_name} not known to supplied camera "
                f"{camera.getName()} ({note_str}: {','.join(detectors)})"
            )
        chip_id = camera[name_map[chip_name]].getId()
        data_by_chip[chip_name], calib_type = read_one_chip(root, chip_name, chip_id)
        calib_types.add(calib_type)
        if len(calib_types) != 1:  # set.add(None) has length 1 so None is OK here.
            raise ValueError(f"Error mixing calib types: {calib_types}")

    no_data = all([v == {} for v in data_by_chip.values()])
    if no_data:
        raise RuntimeError("No data to ingest")

    return data_by_chip, calib_type
