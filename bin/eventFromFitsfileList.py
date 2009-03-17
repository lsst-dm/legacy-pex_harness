#!/usr/bin/env python

import os, sys, re
import glob
import time
import eups
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.pex.policy as pexPolicy
import lsst.pex.logging as pexLog
import lsst.daf.base as dafBase
import lsst.ctrl.events as ctrlEvents
from lsst.ctrl.dc3pipe.MetadataStages import transformMetadata, validateMetadata

import lsst.pex.logging as logging

# Import EventFromInputfile from eventFromFitsfile.py so that we do not have to
# re-write that one.


# Constants
EXP_TIME = 15.
SLEW_TIME = 5.




# Verbosity/logging.
Verbosity = 4
logging.Trace_setVerbosity('dc3pipe', Verbosity)



def EventFromInputFileList(inputfile, 
                           datatypePolicy, 
                           expTime=15,
                           slweTime=5,
                           rootTopicName='triggerImageprocEvent', 
                           hostName='lsst8.ncsa.uiuc.edu'):
    """
    Generate events for the IPSD (and MOPS) pipeline by reading a list of visit
    directories and extracting the relevant information from the FITS files 
    therein.

    The two optional parameters are the exposure time of each exposure in a 
    visit (assumed constant) and the average slew time of the telescope. Both 
    are in seconds. The default to 15 seconds and 5 seconds respecively.

    The script sends one event for the first visit exposure, waits <exp time> 
    sec and then sends an event for the second exposure. At that point, it waits
    (<exp time> + <slew time>) sec before passing to the next visit.

    The input directory list is a simple text file listing visit directories one
    per line. Comments start with a '#' and are ignored. It is assumed that the 
    name of each directory in the file is a valid visitId. Also it is assumed 
    that each directory has the following structure:
        visitId/
                0/
                  raw-<visitId>-e000-c<ccdId>-a<ampId>.fits
                1/
                  raw-<visitId>-e001-c<ccdId>-a<ampId>.fits
    
    @param inputfile: name of the directory list file.
    @param datatypePolicy: Policy file for the input data.
    @param expTime: assume each exposure in a visit is expTime long (defualts to
           15 seconds for DC3). expTime is in seconds.
    @param slewTime: assume an average slew time of slewTime seconds (defualts 
           to 5 seconds for DC3). slewTime is in seconds.
    @param rootTopicName: root name for the event's topic. The final topic will 
           be rootTopicName+'0' or rootTopicName+'1' depending on whether the
           event refers to the first or second image of the visit.
    hostName: hostname of the event broker.
    
    @return None
    """
    # Create a metadata policy object.
    dc3pipeDir = eups.productDir('ctrl_dc3pipe')
    metadataPolicy = pexPolicy.Policy.createPolicy(os.path.join(dc3pipeDir, 
                        'pipeline', 'dc3MetadataPolicy.paf'))
    
    # Covenience function.
    def sendEvent(f):
        return(EventFromInputfile(f, datatypePolicy, metadataPolicy,
                                  rootTopicName, hostName))
    
    f = open(inputfile)
    for line in f:
        dirName = line.strip()
        if(line.startswith('#')):
            continue
        
        # Get the list of amp FITS files in each dir.
        fileList0 = glob.glob(os.path.join(dirName, '0', '*.fits'))
        fileList1 = glob.glob(os.path.join(dirName, '1', '*.fits'))
        
        # Simple sanity check.
        if(len(fileList0) != len(fileList1)):
            pexLog.Trace('dc3pipe.eventfrominputfilelist', 1, 
                         'Skipping %s: wrong file count in 0 and 1' \
                         %(dirName))
            continue
        
        # Now we just trust that the i-th file in 0 corresponds to the i-th file
        # in 1... Fortunately, we only need to send one event per image 
        # directory, since all images there are one MEF split into individual 
        # amps.
        sendEvent(fileList0[0])
        # Sleep some.
        time.sleep(expTime)
        # Next event.
        sendEvent(fileList1[0])
        # Sleep expTime + slewTime.
        time.sleep(expTime + slewTime)
    f.close()
    return
    


def EventFromInputfile(inputfile, 
                       datatypePolicy, 
                       metadataPolicy,
                       rootTopicName='triggerImageprocEvent', 
                       hostName='lsst8.ncsa.uiuc.edu'):
    # For DC3a, inputfile is a .fits file on disk
    metadata = afwImage.readMetadata(inputfile)

    # First, transform the input metdata
    transformMetadata(metadata, datatypePolicy, metadataPolicy, 'Keyword')

    # To be consistent...
    if not validateMetadata(metadata, metadataPolicy):
        pexLog.Trace('dc3pipe.eventfrominputfilelist', 1, 
                     'Unable to create event from %s' % (inputfile))
        return False
        

    # Create event policy, using defaults from input metadata
    event = dafBase.PropertySet()
    event.copy('visitId',     metadata, 'visitId')
    event.copy('ccdId',       metadata, 'ccdId')
    event.copy('ampId',       metadata, 'ampId')
    event.copy('exposureId',  metadata, 'exposureId')
    event.copy('datasetId',   metadata, 'datasetId')
    event.copy('filter',      metadata, 'filter')
    event.copy('expTime',     metadata, 'expTime')
    event.copy('ra',          metadata, 'ra')
    event.copy('decl',        metadata, 'decl')
    event.copy('equinox',     metadata, 'equinox')
    event.copy('airmass',     metadata, 'airmass')
    event.copy('dateObs',     metadata, 'dateObs')

    if event.getInt('exposureId') == 0:
        eventTransmitter = ctrlEvents.EventTransmitter(hostName, topicName+'0')
    elif event.getInt('exposureId') == 1:
        eventTransmitter = ctrlEvents.EventTransmitter(hostName, topicName+'1')

    eventTransmitter.publish(event)
    # print('Sending event for file %s' %(inputfile))
    return True


if __name__ == "__main__":
    USAGE = '''
usage: eventFromFitsFileList.py <dir_list_file> <policy_file> [<exp time>] [<slew time>]
    
Generate events for the IPSD (and MOPS) pipeline by reading a list of visit
directories and extracting the relevant information from the FITS files therein.

The two optional parameters are the exposure time of each exposure in a visit
(assumed constant) and the average slew time of the telescope. Both are in 
seconds. The default to 15 seconds and 5 seconds respecively.

The script sends one event for the first visit exposure, waits <exp time> sec 
and then sends an event for the second exposure. At that point, it waits 
(<exp time> + <slew time>) sec before passing to the next visit.

The input directory list is a simple text file listing visit directories one per
line. Comments start with a '#' and are ignored. It is assumed that the name of 
each directory in the file is a valid visitId. Also it is assumed that each 
directory has the following structure:
    visitId/
            0/
              raw-<visitId>-e000-c<ccdId>-a<ampId>.fits
            1/
              raw-<visitId>-e001-c<ccdId>-a<ampId>.fits
'''
    
    
    if(len(sys.argv) not in (3, 4, 5)):
        sys.stderr.write(USAGE)
        sys.exit(1)
    
    inputDirectoryList = sys.argv[1]
    datatypePolicy = pexPolicy.Policy.createPolicy(sys.argv[2])
    expTime = EXP_TIME
    slewTime = SLEW_TIME
    if(len(sys.argv) == 4):
        try:
            expTime = int(sys.argv[4])
        except:
            pass
    if(len(sys.argv) == 5):
        try:
            slewTime = int(sys.argv[4])
        except:
            pass
    
    # Extract broker info etc.
    pipelinePolicy = dafBase.PropertySet()
    if pipelinePolicy.exists('hostName'):
        hostName  = pipelinePolicy.getString('hostName')
    else:
        hostName = 'lsst8.ncsa.uiuc.edu'
    if pipelinePolicy.exists('topicName'):
        topicName = pipelinePolicy.getString('topicName')
    else:
        topicName = 'triggerImageprocEvent'
    
    EventFromInputFileList(inputDirectoryList, datatypePolicy, expTime, 
                           slewTime, topicName, hostName)
        
