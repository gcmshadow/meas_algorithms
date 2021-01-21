# This file is part of meas_algorithms.
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
#
"""Collection of small images (stamps), each centered on a bright star.
"""

__all__ = ["BrightStarStamp", "BrightStarStamps"]

from dataclasses import dataclass
from operator import ior
from functools import reduce
from typing import Optional

from lsst.daf.base import PropertyList
from lsst.geom import Box2I, Point2I, Extent2I
from lsst.afw import image as afwImage
from lsst.afw import geom as afwGeom
from lsst.afw import math as afwMath
from lsst.fits import math as afwFits
from .stamps import StampsBase, AbstractStamp


@dataclass
class BrightStarStamp(AbstractStamp):
    """Single stamp centered on a bright star, normalized by its
    annularFlux.

    Parameters
    ----------
    stamp_im : `lsst.afw.image.MaskedImage`
        Pixel data for this postage stamp
    gaiaGMag : `float`
        Gaia G magnitude for the object in this stamp
    gaiaId : `int`
        Gaia object identifier
    annularFlux : `Optional[float]`
        Flux in an annulus around the object
    """
    stamp_im: afwImage.MaskedImageF
    gaiaGMag: float
    gaiaId: int
    annularFlux: Optional[float] = None
    XY0: Point2I
    transform: Optional[afwGeom.TransformPoint2ToPoint2] = None

    @classmethod
    def factory(cls, stamp_im, metadata, idx, transform=None):
        """This method is needed to service the FITS reader.
        We need a standard interface to construct objects like this.
        Parameters needed to construct this object are passed in via
        a metadata dictionary and then passed to the constructor of
        this class.  This particular factory method requires keys:
        G_MAGS, GAIA_IDS, and ANNULAR_FLUXES.  They should each
        point to lists of values.

        Parameters
        ----------
        stamp_im : `lsst.afw.image.MaskedImage`
            Pixel data to pass to the constructor
        metadata : `dict`
            Dictionary containing the information
            needed by the constructor.
        idx : `int`
            Index into the lists in ``metadata``

        Returns
        -------
        brightstarstamp : `BrightStarStamp`
            An instance of this class
        """
        x0 = metadata.getArray('X0S')[idx]
        y0 = metadata.getArray('Y0S')[idx]
        return cls(stamp_im=stamp_im,
                   gaiaGMag=metadata.getArray('G_MAGS')[idx],
                   gaiaId=metadata.getArray('GAIA_IDS')[idx],
                   annularFlux=metadata.getArray('ANNULAR_FLUXES')[idx],
                   XY0=[x0, y0],
                   transform=transform)

    def measureAndNormalize(self, annulus, statsControl=afwMath.StatisticsControl(),
                            statsFlag=afwMath.stringToStatisticsProperty("MEAN"),
                            badMaskPlanes=('BAD', 'SAT', 'NO_DATA')):
        """Compute "annularFlux", the integrated flux within an annulus
        around an object's center, and normalize it.

        Since the center of bright stars are saturated and/or heavily affected
        by ghosts, we measure their flux in an annulus with a large enough
        inner radius to avoid the most severe ghosts and contain enough
        non-saturated pixels.

        Parameters
        ----------
        annulus : `lsst.afw.geom.spanSet.SpanSet`
            SpanSet containing the annulus to use for normalization.
        statsControl : `lsst.afw.math.statistics.StatisticsControl`, optional
            StatisticsControl to be used when computing flux over all pixels
            within the annulus.
        statsFlag : `lsst.afw.math.statistics.Property`, optional
            statsFlag to be passed on to ``afwMath.makeStatistics`` to compute
            annularFlux. Defaults to a simple MEAN.
        badMaskPlanes : `collections.abc.Collection` [`str`]
            Collection of mask planes to ignore when computing annularFlux.
        """
        stampSize = self.stamp_im.getDimensions()
        # create image with the same pixel values within annulus, NO_DATA
        # elsewhere
        maskPlaneDict = self.stamp_im.mask.getMaskPlaneDict()
        annulusImage = afwImage.MaskedImageF(stampSize, planeDict=maskPlaneDict)
        annulusMask = annulusImage.mask
        annulusMask.array[:] = 2**maskPlaneDict['NO_DATA']
        annulus.copyMaskedImage(self.stamp_im, annulusImage)
        # set mask planes to be ignored
        andMask = reduce(ior, (annulusMask.getPlaneBitMask(bm) for bm in badMaskPlanes))
        statsControl.setAndMask(andMask)
        # compute annularFlux
        annulusStat = afwMath.makeStatistics(annulusImage, statsFlag, statsControl)
        self.annularFlux = annulusStat.getValue()
        # normalize stamps
        self.stamp_im.image.array /= self.annularFlux
        return None


class BrightStarStamps(StampsBase):
    """Collection of bright star stamps and associated metadata.

    Parameters
    ----------
    starStamps : `collections.abc.Sequence` [`BrightStarStamp`]
        Sequence of star stamps. Cannot contain both normalized and
        unnormalized stamps.
    innerRadius : `int`, optional
        Inner radius value, in pixels. This and ``outerRadius`` define the
        annulus used to compute the ``"annularFlux"`` values within each
        ``starStamp``. Must be provided if ``normalize`` is True.
    outerRadius : `int`, optional
        Outer radius value, in pixels. This and ``innerRadius`` define the
        annulus used to compute the ``"annularFlux"`` values within each
        ``starStamp``. Must be provided if ``normalize`` is True.
    nb90Rots : `int`, optional
        Number of 90 degree rotations required to compensate for detector
        orientation.
    metadata : `lsst.daf.base.PropertyList`, optional
        Metadata associated with the bright stars.
    use_mask : `bool`
        If `True` read and write mask data. Default `True`.
    use_variance : `bool`
        If ``True`` read and write variance data. Default ``False``.

    Raises
    ------
    ValueError
        Raised if one of the star stamps provided does not contain the
        required keys.
    AttributeError
        Raised if there is a mix-and-match of normalized and unnormalized
        stamps, stamps normalized with different annulus definitions, or if
        stamps are to be normalized but annular radii were not provided.


    Notes
    -----
    A butler can be used to read only a part of the stamps, specified by a
    bbox:

    >>> starSubregions = butler.get("brightStarStamps_sub", dataId, bbox=bbox)
    """

    def __init__(self, starStamps, innerRadius=None, outerRadius=None,
                 nb90Rots=None, metadata=None,
                 use_mask=True, use_variance=False):
        super().__init__(starStamps, metadata, use_mask, use_variance)
        # Ensure stamps contain a flux measurement if and only if they are
        # already expected to be normalized
        self._checkNormalization(False, innerRadius, outerRadius)
        self._innerRadius, self._outerRadius = innerRadius, outerRadius
        if innerRadius is not None and outerRadius is not None:
            self.normalized = True
        else:
            self.normalized = False
        self.nb90Rots = nb90Rots

    @classmethod
    def initAndNormalize(cls, starStamps, innerRadius, outerRadius,
                         metadata=None, use_mask=True, use_variance=False,
                         imCenter=None,
                         statsControl=afwMath.StatisticsControl(),
                         statsFlag=afwMath.stringToStatisticsProperty("MEAN"),
                         badMaskPlanes=('BAD', 'SAT', 'NO_DATA')):
        """Normalize a set of bright star stamps and initialize a
        BrightStarStamps instance.

        Since the center of bright stars are saturated and/or heavily affected
        by ghosts, we measure their flux in an annulus with a large enough
        inner radius to avoid the most severe ghosts and contain enough
        non-saturated pixels.

        Parameters
        ----------
        starStamps : `collections.abc.Sequence` [`BrightStarStamp`]
            Sequence of star stamps. Cannot contain both normalized and
            unnormalized stamps.
        innerRadius : `int`
            Inner radius value, in pixels. This and ``outerRadius`` define the
            annulus used to compute the ``"annularFlux"`` values within each
            ``starStamp``.
        outerRadius : `int`
            Outer radius value, in pixels. This and ``innerRadius`` define the
            annulus used to compute the ``"annularFlux"`` values within each
            ``starStamp``.
        metadata : `lsst.daf.base.PropertyList`, optional
            Metadata associated with the bright stars.
        use_mask : `bool`
            If `True` read and write mask data. Default `True`.
        use_variance : `bool`
            If ``True`` read and write variance data. Default ``False``.
        imCenter : `collections.abc.Sequence`, optional
            Center of the object, in pixels. If not provided, the center of the
            first stamp's pixel grid will be used.
        statsControl : `lsst.afw.math.statistics.StatisticsControl`, optional
            StatisticsControl to be used when computing flux over all pixels
            within the annulus.
        statsFlag : `lsst.afw.math.statistics.Property`, optional
            statsFlag to be passed on to ``afwMath.makeStatistics`` to compute
            annularFlux. Defaults to a simple MEAN.
        badMaskPlanes : `collections.abc.Collection` [`str`]
            Collection of mask planes to ignore when computing annularFlux.

        Raises
        ------
        ValueError
            Raised if one of the star stamps provided does not contain the
            required keys.
        AttributeError
            Raised if there is a mix-and-match of normalized and unnormalized
            stamps, stamps normalized with different annulus definitions, or if
            stamps are to be normalized but annular radii were not provided.
        """
        if imCenter is None:
            stampSize = starStamps[0].stamp_im.getDimensions()
            imCenter = stampSize[0]//2, stampSize[1]//2
        # Create SpanSet of annulus
        outerCircle = afwGeom.SpanSet.fromShape(outerRadius, afwGeom.Stencil.CIRCLE, offset=imCenter)
        innerCircle = afwGeom.SpanSet.fromShape(innerRadius, afwGeom.Stencil.CIRCLE, offset=imCenter)
        annulus = outerCircle.intersectNot(innerCircle)
        # Initialize (unnormalized) brightStarStamps instance
        bss = cls(starStamps, innerRadius=None, outerRadius=None,
                  metadata=metadata, use_mask=use_mask,
                  use_variance=use_variance)
        # Ensure no stamps had already been normalized
        bss._checkNormalization(True, innerRadius, outerRadius)
        bss._innerRadius, bss._outerRadius = innerRadius, outerRadius
        # Apply normalization
        for stamp in bss._stamps:
            stamp.measureAndNormalize(annulus, statsControl=statsControl, statsFlag=statsFlag,
                                      badMaskPlanes=badMaskPlanes)
        bss.normalized = True
        return bss

    def _refresh_metadata(self):
        """Refresh the metadata. Should be called before writing this object
        out.
        """
        # add full list of Gaia magnitudes, IDs, annularFlxes stamp origins
        # to shared metadata
        self._metadata["G_MAGS"] = self.getMagnitudes()
        self._metadata["GAIA_IDS"] = self.getGaiaIds()
        self._metadata["ANNULAR_FLUXES"] = self.getAnnularFluxes()
        self._metadata["NORMALIZED"] = self.normalized
        self._metadata["INNER_RADIUS"] = self._innerRadius
        self._metadata["OUTER_RADIUS"] = self._outerRadius
        self._metadata["X0S"] = [XY0[0] for XY0 in self.getXY0s()]
        self._metadata["Y0S"] = [XY0[1] for XY0 in self.getXY0s()]
        # if class instance contains number of rotations, save it to header
        if self.nb90Rots is not None:
            self._metadata["NB_90_ROTS"] = self.nb90Rots
        return None

    def writeFits(self, filename):
        """Write this object to a file.

        Parameters
        ----------
        filename : `str`
            Name of file to write
        """
        self._refresh_metadata()
        stamp_ims = self.getMaskedImages()
        self._metadata['HAS_MASK'] = self.use_mask
        self._metadata['HAS_VARIANCE'] = self.use_variance
        self._metadata['N_STAMPS'] = len(stamp_ims)
        # create primary HDU with global metadata
        fitsPrimary = afwFits.Fits(filename, "w")
        fitsPrimary.createEmpty()
        fitsPrimary.writeMetadata(self._metadata)
        fitsPrimary.closeFile()

        # add all pixel data optionally writing mask and variance information
        for i, (stamp, transform) in enumerate(zip(stamp_ims, self.getTransforms())):
            metadata = PropertyList()
            # EXTVER should be 1-based, the index from enumerate is 0-based
            metadata.update({'EXTVER': i+1, 'EXTNAME': 'IMAGE'})
            stamp.getImage().writeFits(filename, metadata=metadata, mode='a')
            if self.use_mask:
                metadata = PropertyList()
                metadata.update({'EXTVER': i+1, 'EXTNAME': 'MASK'})
                stamp.getMask().writeFits(filename, metadata=metadata, mode='a')
            if self.use_variance:
                metadata = PropertyList()
                metadata.update({'EXTVER': i+1, 'EXTNAME': 'VARIANCE'})
                stamp.getVariance().writeFits(filename, metadata=metadata, mode='a')
            # Write transform
            metadata.update({'EXTVER': i+1, 'EXTNAME': 'TRANSFORM'})
            self.getTransform().writeFits(filename, metadata=metadata, mode='a')
        return None

    @classmethod
    def readFits(cls, filename):
        """Build an instance of this class from a file.

        Parameters
        ----------
        filename : `str`
            Name of the file to read
        """
        return cls.readFitsWithOptions(filename, None)

    @classmethod
    def readFitsWithOptions(cls, filename, options):
        """Build an instance of this class with options.

        Parameters
        ----------
        filename : `str`
            Name of the file to read
        options : `PropertyList`
            Collection of metadata parameters
        """
        # extract necessary info from metadata
        metadata = afwFits.readMetadata(filename, hdu=0)
        f = afwFits.Fits(filename, 'r')
        nExtensions = f.countHdus()
        nStamps = metadata["N_STAMPS"]
        # check if a bbox was provided
        kwargs = {}
        if options and options.exists("llcX"):
            llcX = options["llcX"]
            llcY = options["llcY"]
            width = options["width"]
            height = options["height"]
            bbox = Box2I(Point2I(llcX, llcY), Extent2I(width, height))
            kwargs["bbox"] = bbox
        stamp_parts, transforms = {}, {}
        # We need to be careful because nExtensions includes the primary
        # header data unit
        for idx in range(nExtensions-1):
            md = afwFits.readMetadata(filename, hdu=idx+1)
            if md['EXTNAME'] in ('IMAGE', 'VARIANCE'):
                reader = afwImage.ImageFitsReader(filename, hdu=idx+1)
                stamp_parts.setdefault(md['EXTVER'], {})[md['EXTNAME'].lower()] = reader.read(**kwargs)
            elif md['EXTNAME'] == 'MASK':
                reader = afwImage.MaskFitsReader(filename, hdu=idx+1)
                stamp_parts.setdefault(md['EXTVER'], {})[md['EXTNAME'].lower()] = reader.read(**kwargs)
            elif md['EXTNAME'] == 'TRANSFORM':
                transforms[md['EXTVER']] = afwGeom.TransformPoint2ToPoint2.readFits(filename, hdu=idx+1)
            else:
                raise ValueError(f"Unknown extension type: {md['EXTNAME']}")
        if len(stamp_parts) != nStamps:
            raise ValueError(f'Number of stamps read ({len(stamp_parts)}) does not agree with the '
                             f'number of stamps recorded in the metadata ({nStamps}).')
        # construct stamps themselves
        stamps = []
        for k in range(nStamps):
            # Need to increment by one since EXTVER starts at 1
            maskedImage = afwImage.MaskedImageF(**stamp_parts[k+1])
            transform = transforms[k+1]
            stamps.append(BrightStarStamp.factory(maskedImage, metadata, k, transform=transform))
        if metadata["NORMALIZED"]:
            return cls(stamps,
                       innerRadius=metadata["INNER_RADIUS"], outerRadius=metadata["OUTER_RADIUS"],
                       metadata=metadata, use_mask=metadata['HAS_MASK'],
                       use_variance=metadata['HAS_VARIANCE'])
        else:
            return cls(stamps, metadata=metadata, use_mask=metadata['HAS_MASK'],
                       use_variance=metadata['HAS_VARIANCE'])

    def append(self, item, innerRadius=None, outerRadius=None):
        """Add an additional bright star stamp.

        Parameters
        ----------
        item : `BrightStarStamp`
            Bright star stamp to append.
        innerRadius : `int`, optional
            Inner radius value, in pixels. This and ``outerRadius`` define the
            annulus used to compute the ``"annularFlux"`` values within each
            ``BrightStarStamp``.
        outerRadius : `int`, optional
            Outer radius value, in pixels. This and ``innerRadius`` define the
            annulus used to compute the ``"annularFlux"`` values within each
            ``BrightStarStamp``.
        """
        if not isinstance(item, BrightStarStamp):
            raise ValueError(f"Can only add instances of BrightStarStamp, got {type(item)}.")
        if (item.annularFlux is None) == self.normalized:
            raise AttributeError("Trying to append an unnormalized stamp to a normalized BrightStarStamps "
                                 "instance, or vice-versa.")
        else:
            self._checkRadius(innerRadius, outerRadius)
        self._stamps.append(item)
        return None

    def extend(self, bss):
        """Extend BrightStarStamps instance by appending elements from another
        instance.

        Parameters
        ----------
        bss : `BrightStarStamps`
            Other instance to concatenate.
        """
        if not isinstance(bss, BrightStarStamps):
            raise ValueError('Can only extend with a BrightStarStamps object.  '
                             f'Got {type(bss)}.')
        self._checkRadius(bss._innerRadius, bss._outerRadius)
        self._stamps += bss._stamps

    def getMagnitudes(self):
        """Retrieve Gaia G magnitudes for each star.

        Returns
        -------
        gaiaGMags : `list` [`float`]
        """
        return [stamp.gaiaGMag for stamp in self._stamps]

    def getGaiaIds(self):
        """Retrieve Gaia IDs for each star.

        Returns
        -------
        gaiaIds : `list` [`int`]
        """
        return [stamp.gaiaId for stamp in self._stamps]

    def getAnnularFluxes(self):
        """Retrieve normalization factors for each star.

        These are computed by integrating the flux in annulus centered on the
        bright star, far enough from center to be beyond most severe ghosts and
        saturation. The inner and outer radii that define the annulus can be
        recovered from the metadata.

        Returns
        -------
        annularFluxes : `list` [`float`]
        """
        return [stamp.annularFlux for stamp in self._stamps]

    def getXY0s(self):
        """Retrieve the coordinates of the bottom-left pixel for each star.
        These correspond to that quantity before warping and rotations are
        applied.
        Returns
        -------
        XY0s : list[`tuple`]
        """
        return [stamp.XY0 for stamp in self._starStamps]

    def getTransforms(self):
        """Retrieve Transform from each star's initial stamp to the common
        model grid.
        Returns
        -------
        transforms : `list` [`TransformPoint2toPoint2`]
        """
        return [stamp.transform for stamp in self._starStamps]

    def selectByMag(self, magMin=None, magMax=None):
        """Return the subset of bright star stamps for objects with specified
        magnitude cuts (in Gaia G).

        Parameters
        ----------
        magMin : `float`, optional
            Keep only stars fainter than this value.
        magMax : `float`, optional
            Keep only stars brighter than this value.
        """
        subset = [stamp for stamp in self._stamps
                  if (magMin is None or stamp.gaiaGMag > magMin)
                  and (magMax is None or stamp.gaiaGMag < magMax)]
        # This is an optimization to save looping over the init argument when
        # it is already guaranteed to be the correct type
        instance = BrightStarStamps((),
                                    innerRadius=self._innerRadius, outerRadius=self._outerRadius,
                                    metadata=self._metadata)
        instance._stamps = subset
        return instance

    def _checkRadius(self, innerRadius, outerRadius):
        """Ensure provided annulus radius is consistent with that already
        present in the instance, or with arguments passed on at initialization.
        """
        if innerRadius != self._innerRadius or outerRadius != self._outerRadius:
            raise AttributeError("Trying to mix stamps normalized with annulus radii "
                                 f"{innerRadius, outerRadius} with those of BrightStarStamp instance\n"
                                 f"(computed with annular radii {self._innerRadius, self._outerRadius}).")

    def _checkNormalization(self, normalize, innerRadius, outerRadius):
        """Ensure there is no mixing of normalized and unnormalized stars, and
        that, if requested, normalization can be performed.
        """
        noneFluxCount = self.getAnnularFluxes().count(None)
        nStamps = len(self)
        nFluxVals = nStamps - noneFluxCount
        if noneFluxCount and noneFluxCount < nStamps:
            # at least one stamp contains an annularFlux value (i.e. has been
            # normalized), but not all of them do
            raise AttributeError(f"Only {nFluxVals} stamps contain an annularFlux value.\nAll stamps in a "
                                 "BrightStarStamps instance must either be normalized with the same annulus "
                                 "definition, or none of them can contain an annularFlux value.")
        elif normalize:
            # stamps are to be normalized; ensure annular radii are specified
            # and they have no annularFlux
            if innerRadius is None or outerRadius is None:
                raise AttributeError("For stamps to be normalized (normalize=True), please provide a valid "
                                     "value (in pixels) for both innerRadius and outerRadius.")
            elif noneFluxCount < nStamps:
                raise AttributeError(f"{nFluxVals} stamps already contain an annularFlux value. For stamps to"
                                     " be normalized, all their annularFlux must be None.")
        elif innerRadius is not None and outerRadius is not None:
            # Radii provided, but normalize=False; check that stamps
            # already contain annularFluxes
            if noneFluxCount:
                raise AttributeError(f"{noneFluxCount} stamps contain no annularFlux, but annular radius "
                                     "values were provided and normalize=False.\nTo normalize stamps, set "
                                     "normalize to True.")
        else:
            # At least one radius value is missing; ensure no stamps have
            # already been normalized
            if nFluxVals:
                raise AttributeError(f"{nFluxVals} stamps contain an annularFlux value. If stamps have "
                                     "been normalized, the innerRadius and outerRadius values used must "
                                     "be provided.")
        return None
