#!/usr/bin/env python
"""
HAL module for controlling a Marzhauser stage.

Hazen 04/17
"""
import re
import time

from PyQt5 import QtCore

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.baseClasses.stageModule as stageModule
import storm_control.sc_hardware.marzhauser.marzhauser as marzhauser

import storm_control.sc_library.parameters as params

class MarzhauserStageControl(object):
    """
    Control of MarzhauserStage
    """
    def __init__(self, stage = None, stage_functionality = None, configuration = None, **kwds):
        super().__init__(**kwds)
        self.stage = stage
        self.stage_functionality = stage_functionality

        # Create parameters
        self.parameters = params.StormXMLObject()

        self.parameters.add(params.ParameterSetBoolean(description = "Joystick Enabled?",
                                                       name = "joystick",
                                                       value = True))

        self.parameters.add(params.ParameterSetBoolean(description = "Stage position polling?",
                                                       name = "polling",
                                                       value = True))

        self.newParameters(self.parameters, initialization = True)

    


class MarzhauserStageFunctionality(stageModule.StageFunctionality):
    """
    These stages are nice because they respond quickly to commands
    and they also provide feedback about whether or not they are
    moving.
    """
    def __init__(self, update_interval = None, **kwds):
        super().__init__(**kwds)
        # self.querying = False

        # Each time this timer fires we'll 'query' the stage for it's
        # current position.
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.setInterval(update_interval)
        
        # Disable the single shot timing
        #self.updateTimer.setSingleShot(True)
        
        self.updateTimer.timeout.connect(self.handleUpdateTimer)
        self.updateTimer.start()

        # Connect to our own stagePosition signal in order to store
        # the current position.
        self.stagePosition.connect(self.handleStagePosition)
        
        # This thread will poll the serial port for responses from
        # the stage to the commands we're sending.
        self.polling_thread = MarzhauserPollingThread(device_mutex = self.device_mutex,
                                                      is_moving_signal = self.isMoving,
                                                      sleep_time = 100,
                                                      stage = self.stage,
                                                      stage_position_signal = self.stagePosition)
        self.polling_thread.startPolling()

    def goAbsolute(self, x, y):
        #
        # Debugging all removal of stage position queries.
        #
        super().goAbsolute(x,y)
        self.pos_dict["x"] = x
        self.pos_dict["y"] = y
        self.stagePosition.emit(self.pos_dict)

    def handleStagePosition(self, pos_dict):
        self.pos_dict = pos_dict
        #self.querying = False

    def handleUpdateTimer(self):
        """
        Query the stage for its current position.
        """
        #
        # The purpose of the self.querying flag is to prevent build up of
        # position update requests. If there is already one in process there
        # is no point in starting another one.
        #
        # if not self.querying:
        #     self.querying = True
        #     self.mustRun(task = self.stage.position)
        self.maybeRun(task = self.stage.position)

    def wait(self):
        self.updateTimer.stop()
        self.polling_thread.stopPolling()
        super().wait()


class MarzhauserPollingThread(QtCore.QThread):
    """
    Handles polling the Marzhauser stage for responses to 
    serial commands.
    """
    def __init__(self,
                 device_mutex = None,
                 is_moving_signal = None,
                 sleep_time = None,
                 stage = None,
                 stage_position_signal = None,
                 **kwds):
        super().__init__(**kwds)
        self.device_mutex = device_mutex
        self.is_moving_signal = is_moving_signal
        self.pos_dict = {}
        self.pos_regex = re.compile('([\d\-]+[\.][\d]+) ([\d\-]+[\.][\d]+)')
        self.sleep_time = sleep_time         
        self.stage = stage
        self.stage_position_signal = stage_position_signal

    def run(self):
        self.running = True
        while(self.running):
            responses = None
            self.device_mutex.lock()
            if (self.stage.tty.inWaiting() > 0):
                responses = self.stage.readline()
            self.device_mutex.unlock()

            if responses is None:
                continue
            
            # Parse response. The expectation is that it is one of two things:
            #
            # (1) A status string like "#@--" that indicates that the stage
            #     is or is not moving (statusaxis).
            #
            # (2) The current position "X.XX Y.YY ..".
            #

            time_str = str(time.time())
            for resp in responses.split("\r"):

                # The response was no response. Not sure where these come from.
                if (len(resp) == 0):
                    continue
                
                # Check for 'statusaxis' response form.
                if '@' in resp :
                    if (resp[:2] == "@@"):
                        self.is_moving_signal.emit(False)
                    else:
                        self.is_moving_signal.emit(True)
                    continue
                
                # Try and parse as a position.
                mre = self.pos_regex.match(resp)
                if mre:
                    try:
                        pos_dict = {"x" : float(mre.group(1)) * self.stage.unit_to_um,
                                    "y" : float(mre.group(2)) * self.stage.unit_to_um}
                    except ValueError:
                        pos_dict = {"x" : 1.000 * self.stage.unit_to_um,
                                    "y" : 1.000 * self.stage.unit_to_um}
                    self.stage_position_signal.emit(pos_dict)
                    continue

            # Sleep for ~ x milliseconds.
            self.msleep(self.sleep_time)

    def startPolling(self):
        self.start(QtCore.QThread.NormalPriority)

    def stopPolling(self):
        self.running = False
        self.wait()
        

class MarzhauserStage(stageModule.StageModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        configuration = module_params.get("configuration")
        self.stage = marzhauser.MarzhauserRS232(baudrate = configuration.get("baudrate"),
                                                port = configuration.get("port"))
        
        if self.stage.getStatus():

            # Set (maximum) stage velocity.
            velocity = configuration.get("velocity")
            self.stage.setVelocity(velocity, velocity)
            self.stage_functionality = MarzhauserStageFunctionality(device_mutex = QtCore.QMutex(),
                                                                    stage = self.stage,
                                                                    update_interval = 500)
            # Create parameters
            self.parameters = params.StormXMLObject()

            self.parameters.add(params.ParameterSetBoolean(description = "Joystick Enabled?",
                                                           name = "joystick",
                                                           value = True))

            self.parameters.add(params.ParameterSetBoolean(description = "Stage position polling?",
                                                           name = "polling",
                                                           value = True))

            self.newParameters(self.parameters, initialization = True)

        else:
            self.stage = None
            
    def getParameters(self):
            return self.parameters
    
    def newParameters(self, parameters, initialization = False):

        if initialization:
            changed_p_names = parameters.getAttrs()
        else:
            changed_p_names = params.difference(parameters, self.parameters)

        p = parameters
        for pname in changed_p_names:

            # Update our current parameters.
            self.parameters.setv(pname, p.get(pname))

            # Enable or disable joystick.
            if (pname == "joystick"):
                #print('set the joystick to ' + str(p.get("joystick")))
                self.stage_functionality.mustRun(task = self.stage.joystickOnOff,
                                         args = [p.get("joystick")])

            elif (pname == "polling"):
                #print('set the polling to ' + str(p.get("polling")))
                if p.get("polling"):
                    self.stage_functionality.polling_thread.startPolling()
                else:
                    self.stage_functionality.polling_thread.stopPolling()

            else:
                print(">> Warning", str(pname), " is not a valid parameter for the marzhauser stage")


    def processMessage(self, message):
        if self.stage is None:
            return

        if message.isType("configuration"):
            if message.sourceIs("tcp_control"):
                self.tcpConnection(message.getData()["properties"]["connected"])

            elif message.sourceIs("mosaic"):
                self.pixelSize(message.getData()["properties"]["pixel_size"])
        
        # send our parameters to HAL?
        if message.isType("configure1"):
            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
                                                   data = {"parameters" : self.getParameters()}))
                                                
        elif message.isType("new parameters"):
            hardwareModule.runHardwareTask(self,
                                           message,
                                           lambda : self.updateParameters(message))
                                           
        elif message.isType("get functionality"):
            self.getFunctionality(message)
            
        elif message.isType("start film"):
            self.startFilm(message)

        elif message.isType("stop film"):
            self.stopFilm(message)        

        elif message.isType("tcp message"):
            self.tcpMessage(message)                                        
    
    
    def getFunctionality(self, message):
        if (message.getData()["name"] == self.module_name):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : self.stage_functionality}))

    def updateParameters(self, message):
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"old parameters" : self.getParameters().copy()}))
        p = message.getData()["parameters"].get(self.module_name)
        self.newParameters(p)
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"new parameters" : self.getParameters()}))

   
    # do we need to remake stop to add marz_stage to the settings?
    def stopFilm(self, message):
        
        if self.parameters.get('joystick'):
            print(self.parameters.get('joystick'))
            self.stage_functionality.mustRun(task = self.stage.joystickOnOff,
                                            args = [True])
                                            
        pos_dict = self.stage_functionality.getCurrentPosition()
        pos_string = "{0:.2f},{1:.2f}".format(pos_dict["x"], pos_dict["y"])
        pos_param = params.ParameterCustom(name = "stage_position",
                                           value = pos_string)
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"acquisition" : [pos_param]}))
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"parameters" : self.getParameters()}))
    
