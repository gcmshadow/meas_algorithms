#
# LSST Data Management System
#
# Copyright 2008-2017  AURA/LSST.
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

__all__ = ["BaseSourceSelectorConfig", "BaseSourceSelectorTask", "sourceSelectorRegistry",
           "ColorLimit", "MagnitudeLimit", "SignalToNoiseLimit", "MagnitudeErrorLimit",
           "RequireFlags", "RequireUnresolved",
           "ScienceSourceSelectorConfig", "ScienceSourceSelectorTask",
           "ReferenceSourceSelectorConfig", "ReferenceSourceSelectorTask",
           ]

import abc
import numpy as np
import astropy.units as u
import pandas
import astropy.table

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase

from IPython.core.debugger import Tracer


class BaseSourceSelectorConfig(pexConfig.Config):
    pass


class BaseSourceSelectorTask(pipeBase.Task, metaclass=abc.ABCMeta):
    """Base class for source selectors

    Source selectors are classes that perform a selection on a catalog
    object given a set of criteria or cuts. They return the selected catalog
    and can optionally set a specified Flag field in the input catalog to
    identify if the source was selected.

    Register all source selectors with the sourceSelectorRegistry using:
        sourceSelectorRegistry.register(name, class)

    Attributes
    ----------
    usesMatches : `bool`
        A boolean variable specify if the inherited source selector uses
        matches to an external catalog, and thus requires the ``matches``
        argument to ``run()``.
    """

    ConfigClass = BaseSourceSelectorConfig
    _DefaultName = "sourceSelector"
    usesMatches = False

    def __init__(self, **kwargs):
        pipeBase.Task.__init__(self, **kwargs)

    def run(self, sourceCat, sourceSelectedField=None, matches=None, exposure=None):
        """Select sources and return them.

        The input catalog must be contiguous in memory.

        Parameters:
        -----------
        sourceCat : `lsst.afw.table.SourceCatalog` or `pandas.DataFrame`
                    or `astropy.table.Table`
            Catalog of sources to select from.
        sourceSelectedField : `str` or None
            Name of flag field in sourceCat to set for selected sources.
            If set, will modify sourceCat in-place.
        matches : `list` of `lsst.afw.table.ReferenceMatch` or None
            List of matches to use for source selection.
            If usesMatches is set in source selector this field is required.
            If not, it is ignored.
        exposure : `lsst.afw.image.Exposure` or None
            The exposure the catalog was built from; used for debug display.

        Return
        ------
        struct : `lsst.pipe.base.Struct`
            The struct contains the following data:

            - sourceCat : `lsst.afw.table.SourceCatalog` or `pandas.DataFrame`
                          or `astropy.table.Table`
                The catalog of sources that were selected.
                (may not be memory-contiguous)
            - selected : `numpy.ndarray` of `bool``
                Boolean array of sources that were selected, same length as
                sourceCat.

        Raises
        ------
        RuntimeError
            Raised if ``sourceCat`` is not contiguous.
        """
        if hasattr(sourceCat, 'isContiguous'):
            # Check for continuity on afwTable catalogs
            if not sourceCat.isContiguous():
                raise RuntimeError("Input catalogs for source selection must be contiguous.")

        result = self.selectSources(sourceCat=sourceCat,
                                    exposure=exposure,
                                    matches=matches)

        if sourceSelectedField is not None:
            if isinstance(sourceCat, (pandas.DataFrame, astropy.table.Table)):
                sourceCat[sourceSelectedField] = result.selected
            else:
                source_selected_key = \
                    sourceCat.getSchema()[sourceSelectedField].asKey()
                # TODO: Remove for loop when DM-6981 is completed.
                for source, flag in zip(sourceCat, result.selected):
                    source.set(source_selected_key, bool(flag))
        return pipeBase.Struct(sourceCat=sourceCat[result.selected],
                               selected=result.selected)

    @abc.abstractmethod
    def selectSources(self, sourceCat, matches=None, exposure=None):
        """Return a selection of sources selected by some criteria.

        Parameters
        ----------
        sourceCat : `lsst.afw.table.SourceCatalog` or `pandas.DataFrame`
                    or `astropy.table.Table`
            Catalog of sources to select from.
            This catalog must be contiguous in memory.
        matches : `list` of `lsst.afw.table.ReferenceMatch` or None
            A list of lsst.afw.table.ReferenceMatch objects
        exposure : `lsst.afw.image.Exposure` or None
            The exposure the catalog was built from; used for debug display.

        Return
        ------
        struct : `lsst.pipe.base.Struct`
            The struct contains the following data:

            - selected : `numpy.ndarray` of `bool``
                Boolean array of sources that were selected, same length as
                sourceCat.
        """
        raise NotImplementedError("BaseSourceSelectorTask is abstract")


sourceSelectorRegistry = pexConfig.makeRegistry(
    doc="A registry of source selectors (subclasses of "
        "BaseSourceSelectorTask)",
)


class BaseLimit(pexConfig.Config):
    """Base class for selecting sources by applying a limit

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.

    This provides the `maximum` and `minimum` fields in the Config, and
    a method to apply the limits to an array of values calculated by the
    subclass.
    """
    minimum = pexConfig.Field(dtype=float, optional=True, doc="Select objects with value greater than this")
    maximum = pexConfig.Field(dtype=float, optional=True, doc="Select objects with value less than this")

    def apply(self, values):
        """Apply the limits to an array of values

        Subclasses should calculate the array of values and then
        return the result of calling this method.

        Parameters
        ----------
        values : `numpy.ndarray`
            Array of values to which to apply limits.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        selected = np.ones(len(values), dtype=bool)
        with np.errstate(invalid="ignore"):  # suppress NAN warnings
            if self.minimum is not None:
                selected &= values > self.minimum
            if self.maximum is not None:
                selected &= values < self.maximum
        return selected


class ColorLimit(BaseLimit):
    """Select sources using a color limit

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.

    We refer to 'primary' and 'secondary' flux measurements; these are the
    two components of the color, which is:

        instFluxToMag(cat[primary]) - instFluxToMag(cat[secondary])
    """
    primary = pexConfig.Field(dtype=str, doc="Name of column with primary flux measurement")
    secondary = pexConfig.Field(dtype=str, doc="Name of column with secondary flux measurement")

    def apply(self, catalog):
        """Apply the color limit to a catalog

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog` or `pandas.DataFrame`
                  or `astropy.table.Table`
            Catalog of sources to which the limit will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        primary = _getFieldFromCatalog(catalog, self.primary)
        secondary = _getFieldFromCatalog(catalog, self.secondary)

        primary = (primary*u.nJy).to_value(u.ABmag)
        secondary = (secondary*u.nJy).to_value(u.ABmag)
        color = primary - secondary
        return BaseLimit.apply(self, color)


class FluxLimit(BaseLimit):
    """Select sources using a flux limit

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    fluxField = pexConfig.Field(dtype=str, default="slot_CalibFlux_instFlux",
                                doc="Name of the source flux field to use.")

    def apply(self, catalog):
        """Apply the flux limits to a catalog

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the limit will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        flagField = self.fluxField + "_flag"
        selected = np.logical_not(_getFieldFromCatalog(catalog, flagField, isFlag=True))
        flux = _getFieldFromCatalog(catalog, self.fluxField)

        selected &= BaseLimit.apply(self, flux)
        return selected


class MagnitudeLimit(BaseLimit):
    """Select sources using a magnitude limit

    Note that this assumes that a zero-point has already been applied and
    the fluxes are in AB fluxes in Jansky. It is therefore principally
    intended for reference catalogs rather than catalogs extracted from
    science images.

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    fluxField = pexConfig.Field(dtype=str, default="flux",
                                doc="Name of the source flux field to use.")

    def apply(self, catalog):
        """Apply the magnitude limits to a catalog

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the limit will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        flagField = self.fluxField + "_flag"
        selected = np.logical_not(_getFieldFromCatalog(catalog, flagField, isFlag=True))
        flux = _getFieldFromCatalog(catalog, self.fluxField)

        # Tracer()()
        magnitude = (flux*u.nJy).to_value(u.ABmag)
        selected &= BaseLimit.apply(self, magnitude)
        return selected


class SignalToNoiseLimit(BaseLimit):
    """Select sources using a flux signal-to-noise limit

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    fluxField = pexConfig.Field(dtype=str, default="flux",
                                doc="Name of the source flux field to use.")
    errField = pexConfig.Field(dtype=str, default="flux_err",
                               doc="Name of the source flux error field to use.")

    def apply(self, catalog):
        """Apply the signal-to-noise limits to a catalog

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the limit will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        flagField = self.fluxField + "_flag"
        selected = np.logical_not(_getFieldFromCatalog(catalog, flagField, isFlag=True))
        flux = _getFieldFromCatalog(catalog, self.fluxField)
        err = _getFieldFromCatalog(catalog, self.errField)

        signalToNoise = flux/err
        selected &= BaseLimit.apply(self, signalToNoise)
        return selected


class MagnitudeErrorLimit(BaseLimit):
    """Select sources using a magnitude error limit

    Because the magnitude error is the inverse of the signal-to-noise
    ratio, this also works to select sources by signal-to-noise when
    you only have a magnitude.

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    magErrField = pexConfig.Field(dtype=str, default="mag_err",
                                  doc="Name of the source flux error field to use.")

    def apply(self, catalog):
        """Apply the magnitude error limits to a catalog

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the limit will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        return BaseLimit.apply(self, catalog[self.magErrField])


class RequireFlags(pexConfig.Config):
    """Select sources using flags

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    good = pexConfig.ListField(dtype=str, default=[],
                               doc="List of source flag fields that must be set for a source to be used.")
    bad = pexConfig.ListField(dtype=str, default=[],
                              doc="List of source flag fields that must NOT be set for a source to be used.")

    def apply(self, catalog):
        """Apply the flag requirements to a catalog

        Returns whether the source is selected.

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the requirements will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        selected = np.ones(len(catalog), dtype=bool)
        for flag in self.good:
            selected &= catalog[flag]
        for flag in self.bad:
            selected &= ~catalog[flag]
        return selected


class RequireUnresolved(BaseLimit):
    """Select sources using star/galaxy separation

    This object can be used as a `lsst.pex.config.Config` for configuring
    the limit, and then the `apply` method can be used to identify sources
    in the catalog that match the configured limit.
    """
    name = pexConfig.Field(dtype=str, default="base_ClassificationExtendedness_value",
                           doc="Name of column for star/galaxy separation")

    def setDefaults(self):
        """Set default

        ``base_ClassificationExtendedness_value < 0.5`` means unresolved.
        """
        self.maximum = 0.5

    def apply(self, catalog):
        """Apply the flag requirements to a catalog

        Returns whether the source is selected.

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the requirements will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        value = catalog[self.name]
        return BaseLimit.apply(self, value)


class RequireIsolated(pexConfig.Config):
    """Select sources based on whether they are isolated

    This object can be used as a `lsst.pex.config.Config` for configuring
    the column names to check for "parent" and "nChild" keys.

    Note that this should only be run on a catalog that has had the
    deblender already run (or else deblend_nChild does not exist).
    """
    parentName = pexConfig.Field(dtype=str, default="parent",
                                 doc="Name of column for parent")
    nChildName = pexConfig.Field(dtype=str, default="deblend_nChild",
                                 doc="Name of column for nChild")

    def apply(self, catalog):
        """Apply the isolation requirements to a catalog

        Returns whether the source is selected.

        Parameters
        ----------
        catalog : `lsst.afw.table.SourceCatalog`
            Catalog of sources to which the requirements will be applied.

        Returns
        -------
        selected : `numpy.ndarray`
            Boolean array indicating for each source whether it is selected
            (True means selected).
        """
        selected = ((catalog[self.parentName] == 0)
                    & (catalog[self.nChildName] == 0))
        return selected


class ScienceSourceSelectorConfig(pexConfig.Config):
    """Configuration for selecting science sources"""
    doFluxLimit = pexConfig.Field(dtype=bool, default=False, doc="Apply flux limit?")
    doFlags = pexConfig.Field(dtype=bool, default=False, doc="Apply flag limitation?")
    doUnresolved = pexConfig.Field(dtype=bool, default=False, doc="Apply unresolved limitation?")
    doSignalToNoise = pexConfig.Field(dtype=bool, default=False, doc="Apply signal-to-noise limit?")
    doIsolated = pexConfig.Field(dtype=bool, default=False, doc="Apply isolated limitation?")
    fluxLimit = pexConfig.ConfigField(dtype=FluxLimit, doc="Flux limit to apply")
    flags = pexConfig.ConfigField(dtype=RequireFlags, doc="Flags to require")
    unresolved = pexConfig.ConfigField(dtype=RequireUnresolved, doc="Star/galaxy separation to apply")
    signalToNoise = pexConfig.ConfigField(dtype=SignalToNoiseLimit, doc="Signal-to-noise limit to apply")
    isolated = pexConfig.ConfigField(dtype=RequireIsolated, doc="Isolated criteria to apply")

    def setDefaults(self):
        pexConfig.Config.setDefaults(self)
        self.flags.bad = ["base_PixelFlags_flag_edge", "base_PixelFlags_flag_saturated", "base_PsfFlux_flags"]
        self.signalToNoise.fluxField = "base_PsfFlux_instFlux"
        self.signalToNoise.errField = "base_PsfFlux_instFluxErr"


@pexConfig.registerConfigurable("science", sourceSelectorRegistry)
class ScienceSourceSelectorTask(BaseSourceSelectorTask):
    """Science source selector

    By "science" sources, we mean sources that are on images that we
    are processing, as opposed to sources from reference catalogs.

    This selects (science) sources by (optionally) applying each of a
    magnitude limit, flag requirements and star/galaxy separation.
    """
    ConfigClass = ScienceSourceSelectorConfig

    def selectSources(self, sourceCat, matches=None, exposure=None):
        """Return a selection of sources selected by specified criteria.

        Parameters
        ----------
        sourceCat : `lsst.afw.table.SourceCatalog`
            Catalog of sources to select from.
            This catalog must be contiguous in memory.
        matches : `list` of `lsst.afw.table.ReferenceMatch` or None
            Ignored in this SourceSelector.
        exposure : `lsst.afw.image.Exposure` or None
            The exposure the catalog was built from; used for debug display.

        Return
        ------
        struct : `lsst.pipe.base.Struct`
            The struct contains the following data:

            - selected : `array` of `bool``
                Boolean array of sources that were selected, same length as
                sourceCat.
        """
        selected = np.ones(len(sourceCat), dtype=bool)
        if self.config.doFluxLimit:
            selected &= self.config.fluxLimit.apply(sourceCat)
        if self.config.doFlags:
            selected &= self.config.flags.apply(sourceCat)
        if self.config.doUnresolved:
            selected &= self.config.unresolved.apply(sourceCat)
        if self.config.doSignalToNoise:
            selected &= self.config.signalToNoise.apply(sourceCat)
        if self.config.doIsolated:
            selected &= self.config.isolated.apply(sourceCat)

        self.log.info("Selected %d/%d sources", selected.sum(), len(sourceCat))

        return pipeBase.Struct(selected=selected)


class ReferenceSourceSelectorConfig(pexConfig.Config):
    doMagLimit = pexConfig.Field(dtype=bool, default=False, doc="Apply magnitude limit?")
    doFlags = pexConfig.Field(dtype=bool, default=False, doc="Apply flag limitation?")
    doUnresolved = pexConfig.Field(dtype=bool, default=False, doc="Apply unresolved limitation?")
    doSignalToNoise = pexConfig.Field(dtype=bool, default=False, doc="Apply signal-to-noise limit?")
    doMagError = pexConfig.Field(dtype=bool, default=False, doc="Apply magnitude error limit?")
    magLimit = pexConfig.ConfigField(dtype=MagnitudeLimit, doc="Magnitude limit to apply")
    flags = pexConfig.ConfigField(dtype=RequireFlags, doc="Flags to require")
    unresolved = pexConfig.ConfigField(dtype=RequireUnresolved, doc="Star/galaxy separation to apply")
    signalToNoise = pexConfig.ConfigField(dtype=SignalToNoiseLimit, doc="Signal-to-noise limit to apply")
    magError = pexConfig.ConfigField(dtype=MagnitudeErrorLimit, doc="Magnitude error limit to apply")
    colorLimits = pexConfig.ConfigDictField(keytype=str, itemtype=ColorLimit, default={},
                                            doc="Color limits to apply; key is used as a label only")


@pexConfig.registerConfigurable("references", sourceSelectorRegistry)
class ReferenceSourceSelectorTask(BaseSourceSelectorTask):
    """Reference source selector

    This selects reference sources by (optionally) applying each of a
    magnitude limit, flag requirements and color limits.
    """
    ConfigClass = ReferenceSourceSelectorConfig

    def selectSources(self, sourceCat, matches=None, exposure=None):
        """Return a selection of reference sources selected by some criteria.

        Parameters
        ----------
        sourceCat : `lsst.afw.table.SourceCatalog`
            Catalog of sources to select from.
            This catalog must be contiguous in memory.
        matches : `list` of `lsst.afw.table.ReferenceMatch` or None
            Ignored in this SourceSelector.
        exposure : `lsst.afw.image.Exposure` or None
            The exposure the catalog was built from; used for debug display.

        Return
        ------
        struct : `lsst.pipe.base.Struct`
            The struct contains the following data:

            - selected : `array` of `bool``
                Boolean array of sources that were selected, same length as
                sourceCat.
        """
        selected = np.ones(len(sourceCat), dtype=bool)
        if self.config.doMagLimit:
            selected &= self.config.magLimit.apply(sourceCat)
        if self.config.doFlags:
            selected &= self.config.flags.apply(sourceCat)
        if self.config.doUnresolved:
            selected &= self.config.unresolved.apply(sourceCat)
        if self.config.doSignalToNoise:
            selected &= self.config.signalToNoise.apply(sourceCat)
        if self.config.doMagError:
            selected &= self.config.magError.apply(sourceCat)
        for limit in self.config.colorLimits.values():
            selected &= limit.apply(sourceCat)

        self.log.info("Selected %d/%d references", selected.sum(), len(sourceCat))

        return pipeBase.Struct(selected=selected)


def _getFieldFromCatalog(catalog, field, isFlag=False):
    """
    Get a field from a catalog, for `lsst.afw.table` catalogs or
    `pandas.DataFrame` or `astropy.table.Table` catalogs.

    Parameters
    ----------
    catalog : `lsst.afw.table.SourceCatalog` or `pandas.DataFrame`
              or `astropy.table.Table`
        Catalog of sources to extract field array
    field : `str`
        Name of field
    isFlag : `bool`, optional
        Is this a flag column?  If it does not exist, return array
        of False.

    Returns
    -------
    array : `np.ndarray`
        Array of field values from the catalog.
    """
    found = False
    if isinstance(catalog, (pandas.DataFrame, astropy.table.Table)):
        if field in catalog.columns:
            found = True
            # Sequences must be converted to numpy arrays
            arr = np.array(catalog[field])
    else:
        if field in catalog.schema:
            found = True
            arr = catalog[field]

    if isFlag and not found:
        arr = np.zeros(len(catalog), dtype=bool)
    elif not found:
        raise KeyError(f"Could not find field {field} in catalog.")

    return arr
