#! /usr/bin/env python

import lsst.daf.base as datap
import lsst.ctrl.events as events
import time

if __name__ == "__main__":
    print "starting...\n"
    externalEventTransmitter = events.EventTransmitter("lsst8.ncsa.uiuc.edu", "triggerIpdpEvent")

    root = datap.DataProperty.createPropertyNode("root");

    VISITID = datap.DataProperty("visitid", "fov391")

    root.addProperty(VISITID)

    externalEventTransmitter.publish("eventtype", root)

