#! /usr/bin/env python

# event generator
# acts as orchestrator for DC2

import lsst.events as events
import lsst.mwi.data as datap

import sys

if __name__ == "__main__":
    brokernode = "lsst8.ncsa.uiuc.edu"
    if len(sys.argv) > 1:
        brokernode = sys.argv[1]
    if brokernode.find('.') < 0:
        brokernode += ".ncsa.uiuc.edu"
    print "brokernode =", brokernode
    x = events.EventTransmitter(brokernode, "triggerVisitEvent, mops1Event")

    for image in sys.stdin:
        d = image.split()
        
        root = datap.SupportFactory.createPropertyNode("root")
        exposureId = datap.DataProperty("exposureId", int( d[0] ))
        visitId = datap.DataProperty("visitId", int( d[0] ))
        ra = datap.DataProperty("FOVRA", float( d[1] ))
        dec = datap.DataProperty("FOVDec", float( d[2] ))
        filter = datap.DataProperty("filterName", d[3] )
        visitTime = datap.DataProperty("visitTime", float( d[4] ))

        root.addProperty(exposureId)
        root.addProperty(visitId)
        root.addProperty(ra)
        root.addProperty(dec)
        root.addProperty(filter)
        root.addProperty(visitTime)

        #print exposure, ra, dec, filter, float( d[4] )
        x.publish("log", root)
