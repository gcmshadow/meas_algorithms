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

import itertools
import unittest

from lsst.meas.algorithms import LoadReferenceObjectsTask, getRefFluxField
import lsst.utils.tests


class TrivialLoader(LoadReferenceObjectsTask):
    """Minimal subclass of LoadReferenceObjectsTask to allow instantiation
    """

    def loadSkyCircle(self, ctrCoord, radius, filterName):
        pass


class TestLoadReferenceObjects(lsst.utils.tests.TestCase):
    """Test case for LoadReferenceObjectsTask abstract base class

    Only methods with concrete implementations are tested (hence not loadSkyCircle)
    """

    def testMakeMinimalSchema(self):
        """Make a schema and check it."""
        for filterNameList in (["r"], ["foo", "_bar"]):
            for (addIsPhotometric, addIsResolved, addIsVariable,
                 coordErrDim, addProperMotion, properMotionErrDim,
                 addParallax, addParallaxErr) in itertools.product(
                    (False, True), (False, True), (False, True),
                    (-1, 0, 1, 2, 3, 4), (False, True), (-1, 0, 1, 2, 3, 4),
                    (False, True), (False, True)):
                argDict = dict(
                    filterNameList=filterNameList,
                    addIsPhotometric=addIsPhotometric,
                    addIsResolved=addIsResolved,
                    addIsVariable=addIsVariable,
                    coordErrDim=coordErrDim,
                    addProperMotion=addProperMotion,
                    properMotionErrDim=properMotionErrDim,
                    addParallax=addParallax,
                    addParallaxErr=addParallaxErr,
                )
                if coordErrDim not in (0, 2, 3) or \
                        (addProperMotion and properMotionErrDim not in (0, 2, 3)):
                    with self.assertRaises(ValueError):
                        LoadReferenceObjectsTask.makeMinimalSchema(**argDict)
                else:
                    refSchema = LoadReferenceObjectsTask.makeMinimalSchema(**argDict)
                    self.assertTrue("coord_ra" in refSchema)
                    self.assertTrue("coord_dec" in refSchema)
                    self.assertTrue("centroid_x" in refSchema)
                    self.assertTrue("centroid_y" in refSchema)
                    self.assertTrue("hasCentroid" in refSchema)
                    for filterName in filterNameList:
                        fluxField = filterName + "_flux"
                        self.assertIn(fluxField, refSchema)
                        self.assertNotIn("x" + fluxField, refSchema)
                        fluxErrField = fluxField + "Err"
                        self.assertIn(fluxErrField, refSchema)
                        self.assertEqual(getRefFluxField(refSchema, filterName), filterName + "_flux")
                    self.assertEqual("resolved" in refSchema, addIsResolved)
                    self.assertEqual("variable" in refSchema, addIsVariable)
                    self.assertEqual("photometric" in refSchema, addIsPhotometric)
                    self.assertEqual("photometric" in refSchema, addIsPhotometric)
                    self.assertEqual("epoch" in refSchema, addProperMotion or addParallax)
                    self.assertEqual("coord_raErr" in refSchema, coordErrDim > 0)
                    self.assertEqual("coord_decErr" in refSchema, coordErrDim > 0)
                    self.assertEqual("coord_ra_dec_Cov" in refSchema, coordErrDim == 3)
                    self.assertEqual("pm_ra" in refSchema, addProperMotion)
                    self.assertEqual("pm_dec" in refSchema, addProperMotion)
                    self.assertEqual("pm_raErr" in refSchema, addProperMotion and properMotionErrDim > 0)
                    self.assertEqual("pm_decErr" in refSchema, addProperMotion and properMotionErrDim > 0)
                    self.assertEqual("pm_flag" in refSchema, addProperMotion)
                    self.assertEqual("pm_ra_dec_Cov" in refSchema,
                                     addProperMotion and properMotionErrDim == 3)
                    self.assertEqual("parallax" in refSchema, addParallax)
                    self.assertEqual("parallaxErr" in refSchema, addParallax and addParallaxErr)
                    self.assertEqual("parallax_flag" in refSchema, addParallax)


class TestMemory(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
