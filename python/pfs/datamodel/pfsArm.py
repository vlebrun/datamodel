import collections
import os

import numpy as np
try:
    import pyfits
except ImportError:
    pyfits = None
import matplotlib.pyplot as plt

from pfs.datamodel.pfsConfig import PfsConfig

class PfsArm(object):
    """A class corresponding to a single pfsArm file"""
    #
    # Flags for MASKs
    #
    flags = dict(NODATA = 0x1,          # this pixel contains no data
                 )

    fileNameFormat = "pfsArm-%06d-%1s%1d.fits"

    def __init__(self, visit, spectrograph, arm, pfsConfigId=None, pfsConfig=None):
        self.pfsConfigId = pfsConfigId
        self.visit = visit
        self.spectrograph = spectrograph
        self.arm = arm

        self.lam = []                   # arrays for each fibre
        self.flux = []
        self.mask = []
        self.sky = []
        self.covar = []

        self.pfsConfig = pfsConfig

    @property
    def pfsConfig(self):
        return self._pfsConfig

    @pfsConfig.setter
    def pfsConfig(self, pfsConfig):
        self._pfsConfig = pfsConfig

        if pfsConfig is not None:
            if self.pfsConfigId is None:
                self.pfsConfigId = pfsConfig.pfsConfigId
            else:
                self.checkPfsConfig()

    def read(self, dirName=".", pfsConfigs=None, setPfsConfig=True):
        """Read self's pfsArm file from directory dirName

        If provided, pfsConfigs is a dict of pfsConfig objects, indexed by pfsConfigId
        If setPfsConfig is False (default is True) set the pfsConfig field
        """
        if not pyfits:
            raise RuntimeError("I failed to import pyfits, so cannot read from disk")

        fileName = PfsArm.fileNameFormat % (self.visit, self.arm, self.spectrograph)
        fd = pyfits.open(os.path.join(dirName, fileName)) 
            
        for hduName in ["WAVELENGTH", "FLUX", "COVAR", "MASK", "SKY"]:
            hdu = fd[hduName]
            hdr, data = hdu.header, hdu.data

            if False:
                for k, v in hdr.items():
                    print "%8s %s" % (k, v)

            if data.ndim == 2:
                if hduName == "WAVELENGTH":
                    self.lam = data
                elif hduName == "FLUX":
                    self.flux = data
                elif hduName == "MASK":
                    self.mask = data
                elif hduName == "SKY":
                    self.sky = data
                else:
                    raise RuntimeError("Unexpected HDU %s reading %s" % (hduName, fileName))
            else:
                if hduName != "COVAR":
                    raise RuntimeError("Unexpected HDU %s reading %s" % (hduName, fileName))

                self.covar = data

            #print hdr["EXTNAME"], hdr["XTENSION"], data.dtype, data.shape

        hdu = fd["CONFIG"]
        hdr, data = hdu.header, hdu.data

        assert 'pfsConfigId' in data.names
        assert 'visit' in data.names
        assert len(data['visit']) == 1   # only one row in the table

        if data['visit'][0] != self.visit:
            raise RuntimeError("Filename corresponds to visit %d, but config gives %d" %
                               self.visit, data['visit'][0])

        self.pfsConfigId = data['pfsConfigId'][0]
        if self.pfsConfigId < 0:
            self.pfsConfigId = None

        if not setPfsConfig:
            self.pfsConfig = None
        else:                           # a good idea, but only if we can find the desired pfsConfig
            if pfsConfigs is None:
                pfsConfigs = {}         # n.b. won't be passed back to caller

            if self.pfsConfigId not in pfsConfigs:
                pfsConfigs[self.pfsConfigId] = PfsConfig(self.pfsConfigId)
                pfsConfigs[self.pfsConfigId].read(dirName)

            self.pfsConfig = pfsConfigs[self.pfsConfigId]

        self.checkPfsConfig()

    def checkPfsConfig(self):
        """Check if the PfsConfig is consistent with the PfsArm"""
        if self.pfsConfig is None:
            return

        if self.pfsConfigId != self.pfsConfig.pfsConfigId:
            raise RuntimeError("pfsConfigId == 0x%016x != pfsConfig.pfsConfigId == 0x%016x" %
                               (self.pfsConfigId, self.pfsConfig.pfsConfigId))
        #
        # the case pfsConfigId == 0 is special, and doesn't constrain the number of rows
        # so there's no point checking it
        #
        if self.pfsConfigId != 0 and \
           self.pfsConfig.ra is not None and len(self.flux) > 0 and \
           self.flux.shape[0] != self.pfsConfig.ra.shape[0]:
            raise RuntimeError("Mismatch between pfsArm and pfsConfig files")

    def write(self, dirName=".", fileName=None):
        if not pyfits:
            raise RuntimeError("I failed to import pyfits, so cannot read from disk")

        hdus = pyfits.HDUList()

        hdr = pyfits.Header()
        hdr.update()
        hdus.append(pyfits.PrimaryHDU(header=hdr))

        hdu = pyfits.ImageHDU(self.flux)
        hdu.name = "FLUX"
        hdus.append(hdu)

        hdu = pyfits.ImageHDU(self.covar)
        hdu.name = "COVAR"
        hdus.append(hdu)

        hdu = pyfits.ImageHDU(self.mask)
        hdu.name = "MASK"
        hdus.append(hdu)

        hdu = pyfits.ImageHDU(self.lam)
        hdu.name = "WAVELENGTH"
        hdus.append(hdu)

        hdu = pyfits.ImageHDU(self.sky)
        hdu.name = "SKY"
        hdus.append(hdu)

        hdu = pyfits.BinTableHDU.from_columns([
            pyfits.Column(name = 'pfsConfigId', format = 'K',
                          array=np.array([self.pfsConfigId], dtype=np.int64)),
            pyfits.Column(name = 'visit', format = 'J',
                          array=np.array([self.visit], dtype=np.int32))
        ])

        hdu.name = 'CONFIG'
        hdus.append(hdu)

        # clobber=True in writeto prints a message, so use open instead
        if fileName is None:
            fileName = self.fileNameFormat % (self.visit, self.arm, self.spectrograph)
        with open(os.path.join(dirName, fileName), "w") as fd:
            hdus.writeto(fd)

    def getFiberIdx(self, fiberId):
        """Convert a fiberId to a fiber index"""

        if self.pfsConfig is None:      # we don't know the fiberIds
            return fiberId - 1

        fiberIdxArr = np.where(self.pfsConfig.fiberId == fiberId)[0]
        if len(fiberIdxArr) == 0:
            raise IndexError("fiberId %d is not present in pfsArm" % (fiberId))

        return fiberIdxArr[0]

    def plot(self, fiberId=None, showFlux=None, showMask=False, showSky=False, showCovar=False,
             showPlot=True, labelFibers=True, title=None):
        """Plot some or all of the contents of the PfsArm

        If fiberId is None all fibres are shown; otherwise it can be a list or a single fiberId

        Default is to show the flux
        """

        if fiberId is None:
            if self.pfsConfig is None:
                fiberIds = range(1, len(self.flux)+1)
            else:
                fiberIds = self.pfsConfig.fiberId
        else:
            try:
                fiberId[0]
                fiberIds = fiberId
            except TypeError:
                fiberIds = [fiberId]

        show = dict(mask=showMask, sky=showSky, covar=showCovar)
        show.update(flux = not sum(show.values()) if showFlux is None else showFlux)

        xlabel = "Wavelength (nm)"
        if title is None:
            title = "%06d %d%s" % (self.visit, self.spectrograph, self.arm)
            if fiberId is not None:     # i.e. don't show all of them
                title += " fiber %s" % (", ".join(str(fid) for fid in fiberIds))

        for fiberId in fiberIds:
            fiberIdx = self.getFiberIdx(fiberId)
            for name, data in (["flux", self.flux],
                               ["mask", self.mask],
                               ["sky", self.sky]):
                if not show[name]:
                    continue

                plt.plot(self.lam[fiberIdx], data[fiberIdx], label=fiberId if labelFibers else None)

                plt.xlabel(xlabel)
                plt.title("%s %s" % (title, name))

                if name in ("flux"):
                    plt.axhline(0, ls=':', color='black')

                    if showPlot:
                        plt.show()

            if show["covar"]:
                for i in range(self.covar.shape[1]):
                    plt.plot(self.lam[fiberIdx], self.covar[fiberIdx][i], label="covar[%d]" % (i))

                plt.legend(loc='best')
                plt.title("%s %s" % (title, "covar"))
                    
                if showPlot:
                    plt.show()

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

class PfsArmSet(object):
    """Manipulate a set of pfsArms corresponding to a single visit"""
    def __init__(self, visit, spectrograph, arms=['b', 'r', 'n'], pfsConfigId=None, pfsConfig=None,
                 pfsConfigs={}):
        self.pfsConfigs = pfsConfigs
        self.pfsConfigId = pfsConfigId
        self.visit = visit
        self.spectrograph = spectrograph
        self.arms = arms

        if pfsConfig:
            if self.pfsConfigId:
                if self.pfsConfigId != pfsConfig.pfsConfigId:
                    raise RuntimeError("pfsConfigId == 0x%08x != pfsConfig.pfsConfigId == 0x%08x" %
                                       (self.pfsConfigId, pfsConfig.pfsConfigId))
            else:
                self.pfsConfigId = pfsConfig.pfsConfigId

            self.pfsConfigs[self.pfsConfigId] = pfsConfig

        if self.pfsConfigId in self.pfsConfigs:
            self.pfsConfig = self.pfsConfigs[self.pfsConfigId]
        else:
            self.pfsConfig = None

        self.data = collections.OrderedDict()
        for arm in self.arms:
            self.data[arm] = PfsArm(visit, spectrograph, arm, self.pfsConfigId, self.pfsConfig)

    def read(self, dirName="."):
        for arm in self.arms:
            self.data[arm].read(dirName, pfsConfigs=self.pfsConfigs)

            if not self.pfsConfig:
                self.pfsConfig = self.data[arm].pfsConfig

    def getFiberIdx(self, fiberId):
        return self.data.values()[0].getFiberIdx(fiberId)

    def plot(self, fiberId=1, showFlux=None, showMask=False, showSky=False, showCovar=False,
             showPlot=True):
        """Plot some or all of the contents of the PfsArms

        Default is to show the flux
        """
        show = dict(mask=showMask, sky=showSky, covar=showCovar)
        show.update(flux = not sum(show.values()) if showFlux is None else showFlux)

        fiberIdx = self.getFiberIdx(fiberId)

        xlabel = "Wavelength (nm)"
        title = "%06d %d fiber %d" % (self.visit, self.spectrograph, fiberId)

        for name in ["flux", "mask", "sky"]:
            if not show[name]:
                continue

            for arm in self.data.values():
                plt.plot(arm.lam[fiberIdx], getattr(arm, name)[fiberIdx], label=arm.arm, labelFibers=False)

            plt.title("%s %s" % (title, name))
            plt.xlabel(xlabel)
            plt.legend(loc='best')

            if name in ("flux"):
                plt.axhline(0, ls=':', color='black')

            if showPlot:
                plt.show()

        if show["covar"]:
            for arm in self.data.values():
                for i in range(arm.covar[fiberIdx].shape[0]):
                    plt.plot(arm.lam[fiberIdx], arm.covar[fiberIdx][i],
                             label="%s covar[%d]" % (arm.arm, i))
            plt.xlabel(xlabel)
            plt.legend(loc='best')

            plt.title("%s %s" % (title, "covar"))
            if showPlot:
                plt.show()
