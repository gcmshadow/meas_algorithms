#
# LSST Data Management System
#
# Copyright 2008-2016  AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
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
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#
import unittest
import lsst.utils.tests

from lsst.meas.base import SincCoeffsD


class UtilsBinaryTester(lsst.utils.tests.ExecutablesTestCase):
    pass


if not SincCoeffsD.DISABLED_AT_COMPILE_TIME:
    EXECUTABLES = None
    UtilsBinaryTester.create_executable_tests(__file__, EXECUTABLES)


if __name__ == "__main__":
    unittest.main()
