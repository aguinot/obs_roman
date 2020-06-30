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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Test aggregator for obs_* packages.

The intention is for each obs package to have a single test class that inherits
from this collector class, thus "automatically" getting all new tests. If those
tests require setup that isn't defined in a given obs package, that obs package
will be broken until updated. This is intentional, as a way to prevent obs
packages from falling behind out of neglect.
"""

from lsst.log import Log

from . import butler_tests
from . import mapper_tests
from . import camera_tests

__all__ = ["ObsTests"]


class ObsTests(butler_tests.ButlerGetTests, mapper_tests.MapperTests,
               camera_tests.CameraTests):
    """Aggregator class for all of the obs_* test classes.

    Inherit from this class, then lsst.utils.tests.TestCase, in that order.

    Example subclass::

        class TestObsExample(lsst.obs.base.tests.ObsTests, lsst.utils.tests.TestCase):
            def setUp(self):
                self.setUp_tests(...)
                self.setUp_butler_get(...)
                self.setUp_mapper(...)
                self.setUp_camera(...)
    """

    def setUp_tests(self, butler, mapper, dataIds):
        """Set up the necessary shared variables used by multiple tests.

        Parameters
        ----------
        butler: lsst.daf.persistence.Butler
            A butler object, instantiated on the testdata repository for the
            obs package being tested.
        mapper: lsst.obs.CameraMapper
            A CameraMapper object for your camera, instantiated on the testdata
            repository the obs package being tested.
        dataIds: dict
            dictionary of (exposure name): (dataId of that exposure in the
            testdata repository), with unittest.SkipTest as the value for any
            exposures you do not have/do not want to test. It must contain a
            valid 'raw' dataId, in addition to 'bias','flat','dark', which may
            be set to SkipTest. For example::

                  self.dataIds = {'raw': {'visit': 1, 'filter': 'g'},
                                  'bias': {'visit': 1},
                                  'flat': {'visit': 1},
                                  'dark': unittest.SkipTest
                                 }
        """
        self.butler = butler
        self.mapper = mapper
        self.dataIds = dataIds
        self.log = Log.getLogger('ObsTests')

    def tearDown(self):
        del self.butler
        del self.mapper
        super(ObsTests, self).tearDown()
