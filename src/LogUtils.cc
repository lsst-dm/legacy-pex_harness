// -*- lsst-c++ -*-
/** \file LogUtils.cc
  *
  * \ingroup harness
  *
  * \brief   LogUtils class is a utilities class for creation of the Pipeline and Slice logging.
  *
  * \author  Greg Daues, NCSA
  */
#include <cstring>
#include <sstream>

#include "lsst/pex/harness/LogUtils.h"

#include "lsst/ctrl/events.h"
#include "lsst/ctrl/events/EventSystem.h"
#include "lsst/ctrl/events/EventLog.h"

using namespace std;

using lsst::ctrl::events::EventSystem;
using lsst::ctrl::events::EventLog;
using lsst::pex::logging::Log;

namespace lsst {
namespace pex {
namespace harness {

/** 
 * Constructor.
 */
LogUtils::LogUtils() 
    : pipelineLog(Log::getDefaultLog(),"harness"), _evbHost(""), outlog(0) 
{ }

/** Destructor.
 */
LogUtils::~LogUtils(void) {
    delete outlog;
}

/** Initialize the logger "pipelineLog" to be used globally in the Pipeline class.
 *  Add an ofstream  Destination to the default logger if the localLogMode is True
 * local file is on
 */
void LogUtils::initializeLogger(bool isLocalLogMode,  //!< A flag for writing logs to local files
                                const std::string& name,
                                const std::string& runId,
                                const std::string& logdir
                                ) {
    std::stringstream logfileBuffer;
    std::string logfile;

    if (logdir.length() > 0) { 
        logfileBuffer << logdir;
        logfileBuffer << "/";
    }

    logfileBuffer << "Pipeline.log";
    logfileBuffer >> logfile;

    if(isLocalLogMode) {
        /* Make output file stream   */
        outlog =  new ofstream(logfile.c_str());
    }

    /* Create LSSTLogging transmitter here. (Moved from setupHarnessLogging in TracingLog.cc 
       Need to re-check this for MPI SLices. */ 
    if (_evbHost.length() > 0) { 
        EventSystem& eventSystem = EventSystem::getDefaultEventSystem();
        eventSystem.createTransmitter(_evbHost, "LSSTLogging");
    }

    boost::shared_ptr<TracingLog> 
        lp(setupHarnessLogging(std::string(runId), -1, _evbHost, name,
                               outlog, "harness.pipeline"));
                               
    pipelineLog = *lp;

    pipelineLog.format(Log::INFO, 
                       "Pipeline Logger initialized for pid=%d", getpid());
    if (outlog) 
        pipelineLog.format(Log::INFO, "replicating messages to %s", logfile.c_str());
}

/** Initialize the logger "sliceLog" to be used globally in the Slice class. 
 *  Add an ofstreamDestination to the default logger if the localLogMode is True
 */
void LogUtils::initializeSliceLogger(bool isLocalLogMode, //!< A flag for writing logs to local files
                                const std::string& name,
                                const std::string& runId,
                                const std::string& logdir,
                                const int rank
                            ) {

    std::string logfile;
    if(isLocalLogMode) {
        /* Make a log file name coded to the rank    */
        std::stringstream logfileBuffer;

        if (logdir.length() > 0) {
            logfileBuffer << logdir;
            logfileBuffer << "/";
        }

        logfileBuffer << "Slice";
        logfileBuffer << rank;
        logfileBuffer << ".log";

        logfileBuffer >> logfile;

        /* Make output file stream   */
        outlog =  new ofstream(logfile.c_str());
    }

    
    boost::shared_ptr<TracingLog>
        lp(setupHarnessLogging(std::string(runId), rank, _evbHost,
                               name, outlog, "harness.slice"));
    pipelineLog = *lp;

    pipelineLog.format(Log::INFO, "Slice Logger initialized for pid=%d", getpid());

    if (outlog)
        pipelineLog.format(Log::INFO,
                        "replicating messages to %s", logfile.c_str());
}


}
}
}
