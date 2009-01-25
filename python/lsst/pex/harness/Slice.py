#! /usr/bin/env python

from lsst.pex.harness.Queue import Queue
from lsst.pex.harness.Stage import Stage
from lsst.pex.harness.Clipboard import Clipboard
from lsst.pex.logging import Log, LogRec
from lsst.pex.harness import harnessLib as slice

import lsst.pex.policy as policy
import lsst.pex.exceptions as ex

import lsst.daf.base as dafBase
from lsst.daf.base import *

import lsst.ctrl.events as events
import lsst.pex.exceptions

import os
import sys
import traceback
import threading


"""
Slice represents a single parallel worker program.  
Slice executes the loop of Stages for processing a portion of an Image (e.g.,
single ccd or amplifier). The processing is synchonized with serial processing
in the main Pipeline via MPI communications.  This Python Slice class accesses 
the C++ Slice class via a python extension module to obtain access to the MPI 
environment. 
A Slice obtains its configuration by reading a policy file. 
Slice has a __main__ portion as it serves as the executable program
"spawned" within the MPI-2 Spawn of parallel workers in the C++ Pipeline 
implementation. 
"""

class Slice:
    '''Slice: Python Slice class implementation. Wraps C++ Slice'''

    #------------------------------------------------------------------------
    def __init__(self, runId="TEST", pipelinePolicyName=None):
        """
        Initialize the Slice: create an empty Queue List and Stage List;
        Import the C++ Slice  and initialize the MPI environment
        """
        self.queueList = []
        self.stageList = []
        self.stageClassList = []
        self.stagePolicyList = []
        self.sliceEventTopicList = []
        self.eventTopicList = []
        self.eventReceiverList = []
        self.shareDataList = []
        self.shutdownTopic = "triggerShutdownEvent_slice"
        self._runId = runId
        self.pipelinePolicyName = pipelinePolicyName
        self.cppSlice = slice.Slice()
        self.cppSlice.setRunId(runId)
        self.cppSlice.initialize()
        self._rank = self.cppSlice.getRank()
        self.universeSize = self.cppSlice.getUniverseSize()


    def __del__(self):
        """
        Delete the Slice object: cleanup 
        """
        self.log.log(Log.DEBUG, 'Python Slice being deleted')

    def configureSlice(self):
        """
        Configure the slice via reading a Policy file 
        """

        if(self.pipelinePolicyName == None):
            self.pipelinePolicyName = "pipeline_policy.paf"
        dictName = "pipeline_dict.paf"
        p = policy.Policy.createPolicy(self.pipelinePolicyName)

        # Check for activemqBroker 
        if (p.exists('activemqBroker')):
            self.activemqBroker = p.getString('activemqBroker')
        else:
            self.activemqBroker = "lsst8.ncsa.uiuc.edu"   # default value

        eventSystem = events.EventSystem.getDefaultEventSystem()
        eventSystem.createTransmitter(self.activemqBroker, "LSSTLogging")
        events.EventLog.createDefaultLog(self._runId, self._rank)

        # Check for localLogMode 
        if (p.exists('localLogMode')):
            self.localLogMode = p.getString('localLogMode')
        else:
            self.localLogMode = "No"   # default value


        ## Current way 
        root =  Log.getDefaultLog()

        if (self.localLogMode == "Yes"):
            self.log = self.cppSlice.initializeLogger(root, True)
        else:
            self.cppSlice.initializeLogger(root, False)
            self.log = root;

        ## New way 
        ## root =  Log.getDefaultLog()

        ## if (self.localLogMode == "Yes"):
            ## self.cppSlice.initializeLogger(root, True)
        ## else:
            ## self.cppSlice.initializeLogger(root, False)
        ## self.log =  Log.getDefaultLog()

        # self.log.log(Log.INFO, "Back 2 in Python");

        log = Log(self.log, "Slice.configureSlice")
        lr = LogRec(log, Log.INFO)
        lr << "Initialized the Log Destination in C++, back in Python"
        lr << LogRec.endr


        # set up the logger
        # self.log = Log(Log.getDefaultLog(), "pex.harness.slice")
        # self.log.setThreshold(Log.DEBUG)

        psUniv  = dafBase.PropertySet()
        psRunid = dafBase.PropertySet()
        psRank  = dafBase.PropertySet()
        psUniv.setInt("universeSize", self.universeSize)
        psRunid.setString("runID", self._runId)
        psRank.setInt("rank", self._rank)

        log = Log(self.log, "configurePipeline")
        lr = LogRec(log, Log.INFO)
        lr << "Initial Log Test in Slice " << psRank  << psUniv   << psRunid
        lr << LogRec.endr

        lr = LogRec(log, Log.INFO)
        lr << "Initialized logger for rank " + str(self._rank)
        lr << "universeSize " + str(self.universeSize)
        lr << LogRec.endr

        # Check for eventTimeout
        if (p.exists('eventTimeout')):
            self.eventTimeout = p.getInt('eventTimeout')
        else:
            self.eventTimeout = 10000000   # default value

        # Check if inter-Slice communication, i.e., data sharing, is on
        self.isDataSharingOn = False;
        if (p.exists('shareDataOn')):
            self.isDataSharingOn = p.getBool('shareDataOn', self.isDataSharingOn)

        psSharing  = dafBase.PropertySet()
        psSharing.setBool("isDataSharingOn", self.isDataSharingOn)

        lr = LogRec(log, Log.INFO)
        lr << psSharing
        lr << LogRec.endr

        # Process Application Stages
        fullStageList = p.getArray("appStage")

        lr = LogRec(log, Log.INFO)
        lr << "Read Stage list"
        count = 1
        fullStageNameList = [ ]
        for item in fullStageList:
            fullStageNameList.append(item.getString("stageName"))
            psAppStage  = dafBase.PropertySet()
            psAppStage.setString("appStage" + str(count), item.getString("stageName"))
            lr << psAppStage
            count += 1
        lr << LogRec.endr

        # filePolicy = open('pipeline.policy', 'r')
        # fullStageList = filePolicy.readlines()
        self.nStages = len(fullStageList)

        for astage in fullStageNameList:
            fullStage = astage.strip()
            tokenList = astage.split('.')
            classString = tokenList.pop()
            classString = classString.strip()

            package = ".".join(tokenList)

            # For example  package -> lsst.pex.harness.App1Stage  classString -> App1Stage
            AppStage = __import__(package, globals(), locals(), [classString], -1)
            StageClass = getattr(AppStage, classString)
            self.stageClassList.append(StageClass)

        lr = LogRec(log, Log.INFO)
        lr << "Imported Stages"
        lr << LogRec.endr

        # Process Event Topics
        self.eventTopicList = [ ]
        self.sliceEventTopicList = [ ]
        for item in fullStageList:
            self.eventTopicList.append(item.getString("eventTopic"))
            self.sliceEventTopicList.append(item.getString("eventTopic"))

        # Process Share Data Schedule
        self.shareDataList = []
        for item in fullStageList:
            shareDataStage = False
            if (item.exists('shareData')):
                shareDataStage = item.getBool('shareData', False)
            self.shareDataList.append(shareDataStage)

        lr = LogRec(log, Log.INFO)
        lr << "Read event trigger topics"
        count = 1
        for item in self.eventTopicList:
            psTopic  = dafBase.PropertySet()
            psTopic.setString("eventTopic" + str(count), item)
            lr << psTopic
            count += 1
        lr << LogRec.endr

        count = 0
        for item in self.eventTopicList:
            newitem = item + "_slice"
            self.sliceEventTopicList[count] = newitem
            count += 1

        # Make a List of corresponding eventReceivers for the eventTopics
        # eventReceiverList    
        for topic in self.sliceEventTopicList:
            eventReceiver = events.EventReceiver(self.activemqBroker, topic)
            self.eventReceiverList.append(eventReceiver)

        # Process Stage Policies
        self.stagePolicyList = [ ]
        for item in fullStageList:
            self.stagePolicyList.append(item.getString("stagePolicy"))

        # Process topology policy
        if (p.exists('topology')):
            # Retrieve the topology policy and set it in C++
            topologyPolicy = p.get('topology')
            self.cppSlice.setTopology(topologyPolicy);
            # Diagnostic print
            self.topology   =  topologyPolicy.getString('type')
            lr = LogRec(log, Log.INFO)
            lr << "Read topology"
            psTop0  = dafBase.PropertySet()
            psTop0.setString("topology_type", self.topology)
            lr << psTop0
            lr << LogRec.endr
            # Calculate this Slice's neighbors 
            self.cppSlice.calculateNeighbors();
            neighborString = self.cppSlice.getNeighbors();
            lr = LogRec(log, Log.INFO)
            lr << "Calculated Slice neighbors"
            psTop  = dafBase.PropertySet()
            psTop.setString("xleft xright yleft yright", neighborString)
            lr << psTop
            lr << LogRec.endr


        lr = LogRec(log, Log.INFO)
        lr << "End configureSlice"
        lr << LogRec.endr

    def initializeQueues(self):
        """
        Initialize the Queue List
        """
        for iQueue in range(1, self.nStages+1+1):
            queue = Queue()
            self.queueList.append(queue)

    def initializeStages(self):
        """
        Initialize the Stage List
        """
        for iStage in range(1, self.nStages+1):
            # Make a Policy object for the Stage Policy file
            policyFileName = self.stagePolicyList[iStage-1]
            # Make an instance of the specifies Application Stage
            # Use a constructor with the Policy as an argument
            StageClass = self.stageClassList[iStage-1]
            if (policyFileName != "None"):
                stagePolicy = policy.Policy.createPolicy(policyFileName)
                stageObject = StageClass(iStage, stagePolicy)
            else:
                stageObject = StageClass(iStage)
            # stageObject.setLog(self.log);
            inputQueue  = self.queueList[iStage-1]
            outputQueue = self.queueList[iStage]
            stageObject.initialize(outputQueue, inputQueue)
            stageObject.setRank(self._rank)
            stageObject.setUniverseSize(self.universeSize)
            stageObject.setRun(self._runId)
            self.stageList.append(stageObject)

    def startInitQueue(self):
        """
        Place an empty Clipboard in the first Queue
        """
        clipboard = Clipboard()
        queue1 = self.queueList[0]
        queue1.addDataset(clipboard)

    def postOutputClipboard(self, iStage):
        """
        Place an empty Clipboard in the output queue for designated stage
        """
        clipboard = Clipboard()
        queue2 = self.queueList[iStage]
        queue2.addDataset(clipboard)

    def transferClipboard(self, iStage):
        """
        Move the Clipboard from the input queue to output queue for the designated stage
        """
        # clipboard = Clipboard()
        queue1 = self.queueList[iStage-1]
        queue2 = self.queueList[iStage]
        clipboard = queue1.getNextDataset()
        queue2.addDataset(clipboard)

    def startStagesLoop(self): 
        """
        Execute the Stage loop. The loop progressing in step with 
        the analogous stage loop in the central Pipeline by means of
        MPI Bcast and Barrier calls.
        """

        looplog = Log(self.log, "Slice.startStageLoop", Log.INFO);
        proclog = Log(self.log, "Slice.tryProcess", Log.INFO);

        visitcount = 0
        while True:
            visitcount += 1
            loopnum  = dafBase.PropertySet()
            loopnum.setInt("loopnum", visitcount)

            LogRec(looplog, Log.INFO) \
                       << "Starting Stage Loop" \
                       << loopnum << LogRec.endr

            lr = LogRec(looplog, Log.INFO)
            lr << "Visit loop number " + str(visitcount)
            lr << LogRec.endr


            self.cppSlice.invokeShutdownTest()

            LogRec(looplog, Log.INFO) \
                       << "Tested for Shutdown" << LogRec.endr

            self.startInitQueue()    # place an empty clipboard in the first Queue

            self.errorFlagged = 0
            for iStage in range(1, self.nStages+1):

                psStage  = dafBase.PropertySet()
                psStage.setInt("iStage", iStage);

                LogRec(looplog, Log.INFO) \
                       << "Top Stage Loop" << loopnum  << psStage << LogRec.endr

                lr = LogRec(looplog, Log.INFO)
                lr << "Visit loop number " + str(visitcount) + " iStage " + str(iStage)
                lr << LogRec.endr

                stageObject = self.stageList[iStage-1]

                self.handleEvents(iStage)

                if(self.isDataSharingOn):
                    self.syncSlices(iStage) 

                self.tryProcess(iStage, stageObject)
                LogRec(looplog, Log.INFO) \
                       << "Bottom Stage Loop" << loopnum << psStage << LogRec.endr

            else:
                LogRec(looplog, Log.INFO) \
                       << "Completed Stage Loop" \
                       << loopnum << LogRec.endr

            # If no error/exception was flagged, 
            # then clear the final Clipboard in the final Queue

            if self.errorFlagged == 0:
                LogRec(looplog, Log.INFO) \
                    << "Retrieving final Clipboard for deletion" << LogRec.endr
                finalQueue = self.queueList[self.nStages]
                finalClipboard = finalQueue.getNextDataset()
                finalClipboard.close()
                del finalClipboard
                LogRec(looplog, Log.INFO) \
                    << "Deleted final Clipboard" << LogRec.endr
            else:
                LogRec(looplog, Log.INFO) \
                    << "Error Flagged" << LogRec.endr
                

        LogRec(looplog, Log.INFO) \
            << "End startStagesLoop" << LogRec.endr

    def shutdown(self): 
        """
        Shutdown the Slice execution
        """
        shutlog = Log(self.log, "Slice.shutdown", Log.INFO);
        LogRec(shutlog, Log.INFO) << "Shutting down Slice" << LogRec.endr
        self.cppSlice.shutdown()

    def syncSlices(self, iStage):
        """
        If needed, performs interSlice communication prior to Stage process
        """
        synclog = Log(self.log, "Slice.syncSlices", Log.INFO);

        psStage  = dafBase.PropertySet()
        psStage.setInt("iStage", iStage);

        lr = LogRec(synclog, Log.INFO)
        lr << "Start syncSlices"
        lr << psStage
        lr << LogRec.endr

        if(self.shareDataList[iStage-1]):
            lr = LogRec(synclog, Log.INFO)
            lr << "Sharing Clipboard data"
            lr << LogRec.endr
            queue = self.queueList[iStage-1]
            clipboard = queue.getNextDataset()
            sharedKeys = clipboard.getSharedKeys()
            
            psLength = dafBase.PropertySet()
            psLength.setInt("Length of shared keys list", len(sharedKeys));

            lr = LogRec(synclog, Log.INFO)
            lr << "Obtained shared keys"
            lr << psLength
            lr << LogRec.endr

            for skey in sharedKeys:

                psKey = dafBase.PropertySet()
                psKey.setString("shared key", skey);
                lr = LogRec(synclog, Log.INFO)
                lr << "Executing C++ syncSlices : "
                lr << psKey
                lr << LogRec.endr

                psPtr = clipboard.get(skey)
                newPtr = self.cppSlice.syncSlices(psPtr)
                 
                psValuesFromNeighbors = dafBase.PropertySet()
                valuesFromNeighbors = newPtr.toString(False)
                psValuesFromNeighbors.setString("Result", valuesFromNeighbors)

                neighborList = self.cppSlice.getNeighborList()

                for element in neighborList:
                    neighborKey = skey + "-" + str(element)
                    psKey = "neighbor-" + str(element)
                    propertySetPtr = newPtr.getAsPropertySetPtr(psKey)
                    psDebug = dafBase.PropertySet()
                    testString = propertySetPtr.toString(False)
                    psDebug.setString("Result2", testString)
                    clipboard.put(neighborKey, propertySetPtr, False);
                    lr = LogRec(synclog, Log.INFO)
                    lr << "Element in neighborList "
                    lr << neighborKey
                    lr << LogRec.endr
                    lr = LogRec(synclog, Log.INFO)
                    lr << "Result2 String "
                    lr << testString
                    lr << LogRec.endr
                    

                # neighborKey = skey + "-N" 
                # clipboard.put(neighborKey, neighborkeyPtrType, False);
                lr = LogRec(synclog, Log.INFO)
                lr << "Executed C++ syncSlices : "
                lr << psKey
                lr << "---------------"
                lr << psValuesFromNeighbors
                lr << LogRec.endr


            queue.addDataset(clipboard)

        lr = LogRec(synclog, Log.INFO)
        lr << "End syncSlices"
        lr << psStage
        lr << LogRec.endr

    def tryProcess(self, iStage, stage):
        """
        Executes the try/except construct for Stage process() call 
        """
        # Important try - except construct around stage process() 

        proclog = Log(self.log, "Slice.tryProcess", Log.INFO);

        stageObject = self.stageList[iStage-1]
        proclog.log(Log.INFO, "Getting process signal from Pipeline")
        self.cppSlice.invokeBcast(iStage)
        proclog.log(Log.INFO, "Starting process")

        # Important try - except construct around stage process() 
        try:
            # If no error/exception has been flagged, run process()
            # otherwise, simply pass along the Clipboard 
            if (self.errorFlagged == 0):
                stageObject.process()
            else:
                self.transferClipboard(iStage)
  
        ### raise lsst.pex.exceptions.LsstException("Terrible Test Exception")
        except lsst.pex.exceptions.LsstCppException, e:
            t = e.args[0].getTraceback()

            lr = LogRec(proclog, Log.FATAL)
            lr << "Exception traceback: " + "File = " + t[0]._file \
               << "Line = "  + t[0]._line + "Func = " + t[0]._func \
               << "Message = " + t[0]._msg \
               << LogRec.endr

            # Flag that an exception occurred to guide the framework to skip processing
            self.errorFlagged = 1
            # Post the cliphoard that the Stage failed to transfer to the output queue
            self.postOutputClipboard(iStage)

        except Exception, e:

            # Use str(e) or  e.args[0].what() for message  
            lr = LogRec(proclog, Log.FATAL)
            lr << "Exception " + "args[0] = " + e.args[0] \
               << "Message = " + str(e) \
               << LogRec.endr

            # Flag that an exception occurred to guide the framework to skip processing
            self.errorFlagged = 1
            # Post the cliphoard that the Stage failed to transfer to the output queue
            self.postOutputClipboard(iStage)

        proclog.log(Log.INFO, "Ending process")
        proclog.log(Log.INFO, "Getting end of process signal from Pipeline")
        self.cppSlice.invokeBarrier(iStage)

    def handleEvents(self, iStage):
        """
        Handles Events: transmit or receive events as specified by Policy
        """
        log = Log(self.log, "Slice.handleEvents");

        psStage  = dafBase.PropertySet()
        psStage.setInt("iStage", iStage);

        lr = LogRec(log, Log.INFO)
        lr << "Start handleEvents"
        lr << psStage
        lr << LogRec.endr
        
        thisTopic = self.eventTopicList[iStage-1]

        psTopic  = dafBase.PropertySet()
        psTopic.setString("Topic", thisTopic);

        lr = LogRec(log, Log.INFO)
        lr << "Processing topic"
        lr << psTopic
        lr << LogRec.endr

        if (thisTopic != "None"):
            sliceTopic = self.sliceEventTopicList[iStage-1]
            # x = events.EventReceiver(self.activemqBroker, sliceTopic)
            x  = self.eventReceiverList[iStage-1]

            log.log(Log.INFO, 'waiting on receive...')
            inputParamPropertySetPtr = x.receive(self.eventTimeout)

            self.populateClipboard(inputParamPropertySetPtr, iStage, thisTopic)

            log.log(Log.INFO, 'Received event; added payload to clipboard')
        else:
            log.log(Log.INFO, 'No event to handle')

        lr = LogRec(log, Log.INFO)
        lr << "End handleEvents"
        lr << psStage
        lr << LogRec.endr

    def populateClipboard(self, inputParamPropertySetPtr, iStage, eventTopic):
        """
        Place the event payload onto the Clipboard
        """
        log = Log(self.log, "Slice.populateClipboard");
        log.log(Log.DEBUG,'Python Pipeline populateClipboard');

        queue = self.queueList[iStage-1]
        clipboard = queue.getNextDataset()

        # Slice does not disassemble the payload of the event. 
        # It knows nothing of the contents. 
        # It simply places the payload on the clipboard with key of the eventTopic
        clipboard.put(eventTopic, inputParamPropertySetPtr)
        # LogRec(log, Log.DEBUG) << 'Added PropertySetPtrType to clipboard ' \
        #             << inputParamPropertySetPtr                            \
        #            << LogRec.endr

        queue.addDataset(clipboard)

    #------------------------------------------------------------------------
    def getRun(self):
        """
        get method for the runId
        """
        return self._runId

    #------------------------------------------------------------------------
    def setRun(self, run):
        """
        set method for the runId
        """
        self._runId = run

if (__name__ == '__main__'):
    """
    Slice Main execution 
    """

    pySlice = Slice()

    pySlice.configureSlice()   

    pySlice.initializeQueues()     

    pySlice.initializeStages()   

    pySlice.startInitQueue()

    pySlice.startStagesLoop()

    pySlice.shutdown()

