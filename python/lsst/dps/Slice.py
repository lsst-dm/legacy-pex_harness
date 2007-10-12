#! /usr/bin/env python

from Queue import Queue
from Stage import Stage
from Clipboard import Clipboard

import lsst.mwi.policy as policy

import lsst.mwi.data as datap

import lsst.events as events

import os


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
    def __init__(self):
        """
        Initialize the Slice: create an empty Queue List and Stage List;
        Import the C++ Slice  and initialize the MPI environment
        """
        self.queueList = []
        self.stageList = []
        self.stageClassList = []
        self.sliceEventTopicList = []
        self.eventTopicList = []
        import slice
        self.cppSlice = slice.Slice()
        self.cppSlice.initialize()
        self.universeSize = self.cppSlice.getUniverseSize()
        self._rank = self.cppSlice.getRank()
        self.LOGFILE = open("SlicePython_" + str(self._rank) + ".log","w")
        self.LOGFILE.write("Python Slice " + str(self._rank) + " __init__ : Opened log \n")
        self.LOGFILE.write("Python Slice "  + str(self._rank) + "__init__ : universeSize is ")
        self.LOGFILE.write(str(self.universeSize))
        self.LOGFILE.write("\n")
        self.LOGFILE.flush()


    def __del__(self):
        """
        Delete the Slice object: cleanup 
        """
        print 'Python Slice being deleted'

    def configureSlice(self):
        """
        Configure the slice via reading a Policy file 
        """
        self.eventHost = "lsst8.ncsa.uiuc.edu"
        # self.eventTopic = "slicedata"

        policyFileName = "policy/pipeline_policy.json"
        p = policy.Policy.createPolicy(policyFileName)

        # Process Application Stages
        fullStageList = p.getArray("appStages")

        self.LOGFILE.write("appStages")
        self.LOGFILE.write("\n")
        for item in fullStageList:
            self.LOGFILE.write(item)
            self.LOGFILE.write("\n")
        self.LOGFILE.write("end appStages")
        self.LOGFILE.write("\n")

        # filePolicy = open('pipeline.policy', 'r')
        # fullStageList = filePolicy.readlines()
        self.nStages = len(fullStageList)

        for astage in fullStageList:
            fullStage = astage.strip()
            tokenList = astage.split('.')
            classString = tokenList.pop()
            classString = classString.strip()

            package = ''
            for item in tokenList:
                package += item
                package += '/'
            package = package.rstrip('/')

            # For example  package -> lsst.dps.App1Stage  classString -> App1Stage
            AppStage = __import__(package, globals(), locals(), [classString], -1)
            StageClass = getattr(AppStage, classString)
            self.stageClassList.append(StageClass)

        # Process Event Topics
        self.eventTopicList = p.getArray("eventTopics")
        self.sliceEventTopicList = p.getArray("eventTopics")

        self.LOGFILE.write("eventTopics")
        self.LOGFILE.write("\n")

        count = 0
        for item in self.eventTopicList:
            newitem = item + "_slice"
            self.sliceEventTopicList[count] = newitem
            count += 1

        for item in self.sliceEventTopicList:
            self.LOGFILE.write(item)
            self.LOGFILE.write("\n")
        self.LOGFILE.write("end eventTopics")
        self.LOGFILE.write("\n")


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
            StageClass = self.stageClassList[iStage-1]
            stageObject = StageClass(iStage)
            inputQueue  = self.queueList[iStage-1]
            outputQueue = self.queueList[iStage]
            stageObject.initialize(outputQueue, inputQueue)
            stageObject.setRank(self._rank)
            stageObject.setUniverseSize(self.universeSize)
            self.stageList.append(stageObject)

    def startInitQueue(self):
        """
        Place an empty Clipboard in the first Queue
        """
        clipboard = Clipboard()
        queue1 = self.queueList[0]
        queue1.addDataset(clipboard)

    def startStagesLoop(self): 
        """
        Execute the Stage loop. The loop progressing in step with 
        the analogous stage loop in the central Pipeline by means of
        MPI Bcast and Barrier calls.
        """
        for iStage in range(1, self.nStages+1):

            self.handleEvents(iStage)

            stageObject = self.stageList[iStage-1]
            self.cppSlice.invokeBcast(iStage)
            stageObject.process()
            self.cppSlice.invokeBarrier(iStage)

        else:
            print 'Python Slice The for loop is over'


    def shutdown(self): 
        """
        Shutdown the Slice execution
        """
        self.cppSlice.shutdown()

    def handleEvents(self, iStage):
        """
        Handles Events: transmit or receive events as specified by Policy
        """
        print 'Python Slice handleEvents : rank %i iStage %i' % (self._rank, iStage)
        
        thisTopic = self.eventTopicList[iStage-1]

        if (thisTopic != "None"):
            sliceTopic = self.sliceEventTopicList[iStage-1]
            x = events.EventReceiver(self.eventHost, sliceTopic)

            print 'Python Slice handleEvents rank : ',self._rank, ' - waiting on receive...\n'
            inputParamPropertyPtrType = x.receive(800000)
            print 'Python Slice handleEvents rank : ',self._rank,' - received event.\n'

            self.populateClipboard(inputParamPropertyPtrType, iStage, thisTopic)

            print 'Python Slice handleEvents rank : ',self._rank,' Added DataPropertyPtrType to clipboard '
        else:
            print 'Python Slice handleEvents : rank %i iStage %i : No event to handle' % (self._rank, iStage)

    def populateClipboard(self, inputParamPropertyPtrType, iStage, eventTopic):
        """
        Place the event payload onto the Clipboard
        """
        print 'Python Slice populateClipboard'

        queue = self.queueList[iStage-1]
        clipboard = queue.getNextDataset()

        # Slice does not disassemble the payload of the event. 
        # It knows nothing of the contents. 
        # It simply places the payload on the clipboard with key of the eventTopic
        clipboard.put(eventTopic, inputParamPropertyPtrType)
        print 'Python Slice populateClipboard rank : ',self._rank,' Added DataPropertyPtrType to clipboard '

        queue.addDataset(clipboard)

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
