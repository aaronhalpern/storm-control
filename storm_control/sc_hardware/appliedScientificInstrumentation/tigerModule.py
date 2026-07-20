#!/usr/bin/env python
"""
HAL module for controlling a Tiger controller.

Hazen 05/18
"""
import math
from PyQt5 import QtCore

import storm_control.sc_library.halExceptions as halExceptions

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.amplitudeModule as amplitudeModule
import storm_control.sc_hardware.baseClasses.filterWheelModule as filterWheelModule
import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.baseClasses.stageModule as stageModule
import storm_control.sc_hardware.baseClasses.stageZModule as stageZModule
import storm_control.sc_hardware.baseClasses.voltageZModule as voltageZModule

import storm_control.sc_hardware.appliedScientificInstrumentation.tiger as tiger


def parseFilterNames(settings):
    """
    Return a dictionary mapping user-friendly filter names to positions.
    """
    filter_names = {}
    if settings.has("filters"):
        for i, filter_name in enumerate(settings.get("filters").split(",")):
            filter_name = filter_name.strip()
            if filter_name in filter_names:
                raise halExceptions.HardwareException("Duplicate filter wheel filter name '" + filter_name + "'.")
            filter_names[filter_name] = i
    return filter_names


def parseFilterSequence(settings):
    """
    Parse the optional filter wheel sequence.

    The sequence may be specified as comma-separated integer positions or as
    names from the optional comma-separated filters list.
    """
    if not settings.has("sequence"):
        return None

    sequence = settings.get("sequence").strip()
    if len(sequence) == 0:
        return None

    filter_names = parseFilterNames(settings)
    positions = []
    for token in sequence.split(","):
        token = token.strip()
        if token in filter_names:
            positions.append(filter_names[token])
        else:
            try:
                positions.append(int(token))
            except ValueError:
                raise halExceptions.HardwareException("Unknown filter wheel sequence entry '" + token + "'.")
    return positions


class TigerLEDFunctionality(amplitudeModule.AmplitudeFunctionalityBuffered):
    def __init__(self, address = None, channel = None, ttl_mode = None, led = None, **kwds):
        """
        ttl_mode is the TTL control mode to use when filming. Usually this is mode 22, which
        requires firmware 3.30 and above. Note also that due to how this mode is implemented
        the power will only get updated when the shutter line goes high, so for always on you
        should include short pulses so that the power updates.
        """
        super().__init__(**kwds)
        self.address = address
        self.channel = channel
        self.cur_power = 0
        self.led = led
        self.on = False
        self.ttl_mode = ttl_mode

        # Make sure we are mode 0.
        self.mustRun(task = self.led.setTTLMode,
                     args = [self.address, 0])

    def onOff(self, power, state):
        self.mustRun(task = self.led.setLED,
                     args = [self.address, self.channel, power])
        self.on = state
    
    def output(self, power):
        if self.on:
            self.maybeRun(task = self.led.setLED,
                          args = [self.address, self.channel, power])

    def setFilmPower(self):
        #
        # Bypass the queue because we need to be sure that this
        # gets done before the film starts.
        #
        self.device_mutex.lock()
        self.led.setLED(self.address, self.channel, self.cur_power)
        self.device_mutex.unlock()

    def setFilmTTLMode(self, filming):
        #
        # Bypass the queue because we need to be sure that this
        # gets done before the film starts.
        #
        if (self.ttl_mode > 0):
            self.device_mutex.lock()
            if filming:
                self.led.setTTLMode(self.address, self.ttl_mode)
            else:
                self.led.setTTLMode(self.address, 0)
            self.device_mutex.unlock()
                    
    def startFilm(self, power):
        self.cur_power = power


class TigerFilterWheelFunctionality(filterWheelModule.FilterWheelFunctionalityBuffered):
    """
    FW-1000/TGFW filter wheel support.

    Normal HAL filter wheel changes use MP moves. During films this can preload
    P0..P7 protocol positions so external TTL pulses on TRIG IN advance the
    wheel without per-frame serial traffic.
    """
    def __init__(self,
                 filter_wheel = None,
                 protocol_length = 8,
                 protocol_positions = None,
                 restore_on_stop = True,
                 wheel = 0,
                 **kwds):
        super().__init__(**kwds)
        self.filter_wheel = filter_wheel
        self.protocol_length = protocol_length
        self.protocol_positions = protocol_positions
        self.restore_on_stop = restore_on_stop
        self.wheel = wheel

        self.film_start_position = None

    def checkProtocolPositions(self, positions):
        if (len(positions) == 0):
            raise halExceptions.HardwareException("Filter wheel protocol sequence is empty.")
        if (len(positions) > self.protocol_length):
            raise halExceptions.HardwareException("Filter wheel protocol sequence has more than {0:d} entries.".format(self.protocol_length))
        for position in positions:
            self.checkPosition(position)

    def getProtocolPositions(self):
        if self.protocol_positions is not None:
            positions = self.protocol_positions
        else:
            positions = [self.current_position]
        self.checkProtocolPositions(positions)
        return positions

    def setCurrentPosition(self, position):
        self.checkPosition(position)
        self.maybeRun(task = self.filter_wheel.fwMove,
                      args = [self.wheel, position])
        self.current_position = position

    def startFilm(self):
        positions = self.getProtocolPositions()
        self.film_start_position = self.current_position

        self.device_mutex.lock()
        self.filter_wheel.fwHalt()
        self.filter_wheel.fwLoadProtocol(self.wheel,
                                         positions,
                                         protocol_length = self.protocol_length)
        self.filter_wheel.fwGoProtocol(0)
        self.device_mutex.unlock()

        self.current_position = positions[0]

    def stopFilm(self):
        self.device_mutex.lock()
        self.filter_wheel.fwHalt()
        if self.restore_on_stop and (self.film_start_position is not None):
            self.filter_wheel.fwMove(self.wheel, self.film_start_position)
            self.current_position = self.film_start_position
        self.device_mutex.unlock()

        self.film_start_position = None


class TigerStageFunctionality(stageModule.StageFunctionalityNF):
    """
    According to the documentation, this stage has a maximum velocity of 7.5mm / second.
    """
    def __init__(self, velocity = None, **kwds):
        super().__init__(**kwds)
        self.max_velocity = 1.0e+3 * velocity # Maximum velocity in um/s

        self.mustRun(task = self.stage.setVelocity,
                     args = [velocity, velocity])
        
#        self.stage.setVelocity(velocity, velocity)

    def calculateMoveTime(self, dx, dy):
        time_estimate = math.sqrt(dx*dx + dy*dy)/self.max_velocity + 1.0
        #print("> stage move time estimate is {0:.3f} seconds".format(time_estimate))
        return time_estimate


class TigerVoltageZFunctionality(voltageZModule.VoltageZFunctionality):
    """
    External voltage control of piezo Z stage.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
    
class TigerZStageFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    The z sign convention of this stage is the opposite from the expected
    so we have to adjust.
    """
    def __init__(self, update_interval = None, velocity = None, **kwds):
        super().__init__(**kwds)

        self.maximum = self.getParameter("maximum")
        self.minimum = self.getParameter("minimum")

        # Set initial z velocity.
        self.mustRun(task = self.z_stage.zSetVelocity,
                     args = [velocity])
        
        # This timer to restarts the update timer after a move. It appears
        # that if you query the position during a move the stage will stop
        # moving.
        self.restart_timer = QtCore.QTimer()
        self.restart_timer.setInterval(2000)
        self.restart_timer.timeout.connect(self.handleRestartTimer)
        self.restart_timer.setSingleShot(True)

        # Each time this timer fires we'll query the z stage position. We need
        # to do this as the user might use the controller to directly change
        # the stage z position.
        self.update_timer = QtCore.QTimer()
        self.update_timer.setInterval(update_interval)
        self.update_timer.timeout.connect(self.handleUpdateTimer)
        self.update_timer.start()
        
    def goAbsolute(self, z_pos):
        # We have to stop the update timer because if it goes off during the
        # move it will stop the move.
        self.update_timer.stop()
        super().goAbsolute(z_pos)
        self.restart_timer.start()

    def goRelative(self, z_delta):
        z_pos = -1.0*self.z_position + z_delta
        self.goAbsolute(z_pos)        

    def handleRestartTimer(self):
        self.update_timer.start()
        
    def handleUpdateTimer(self):
        self.mustRun(task = self.position,
                     ret_signal = self.zStagePosition)

    def position(self):
        self.z_position = self.z_stage.zPosition()["z"]
        return -1.0*self.z_position

    def zero(self):
        self.mustRun(task = self.z_stage.zZero)
        self.zStagePosition.emit(0.0)
    
    def zMoveTo(self, z_pos):
        return -1.0*super().zMoveTo(-z_pos)
    
        
#
# Inherit from stageModule.StageModule instead of the base class so we don't
# have to duplicate most of the stage stuff, particularly the TCP control.
#
class TigerController(stageModule.StageModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.controller_mutex = QtCore.QMutex()
        self.functionalities = {}
        self.filter_wheel_functionalities = []

        # These are used for the Z piezo stage.
        self.z_piezo_configuration = None
        self.z_piezo_functionality = None

        configuration = module_params.get("configuration")
        self.controller = tiger.Tiger(baudrate = configuration.get("baudrate"),
                                      port = configuration.get("port"))
        
        if self.controller.getStatus():

            # Note: We are not checking whether the devices that the user requested
            #       are actually available, we're just assuming that they know what
            #       they are doing.
            #
            devices = configuration.get("devices")
            for dev_name in devices.getAttrs():

                # XY stage.
                if (dev_name == "xy_stage"):
                    settings = devices.get(dev_name)

                    # We do this so that the superclass works correctly.
                    self.stage = self.controller

                    self.stage_functionality = TigerStageFunctionality(device_mutex = self.controller_mutex,
                                                                       stage = self.stage,
                                                                       update_interval = 500,
                                                                       velocity = settings.get("velocity", 7.5))
                    self.functionalities[self.module_name + "." + dev_name] = self.stage_functionality

                elif (dev_name == "z_piezo"):
                    self.z_piezo_configuration = devices.get(dev_name)

                elif (dev_name == "z_stage"):
                    settings = devices.get(dev_name)
                    z_stage_fn = TigerZStageFunctionality(device_mutex = self.controller_mutex,
                                                          parameters = settings,
                                                          update_interval = 500,
                                                          velocity = settings.get("velocity", 1.0),
                                                          z_stage = self.controller)
                    self.functionalities[self.module_name + "." + dev_name] = z_stage_fn

                elif (dev_name.startswith("led")):
                    settings = devices.get(dev_name)
                    led_fn = TigerLEDFunctionality(address = settings.get("address"),
                                                   channel = settings.get("channel"),
                                                   device_mutex = self.controller_mutex,
                                                   maximum = 100,
                                                   ttl_mode = configuration.get("ttl_mode", -1),
                                                   led = self.controller)
                    self.functionalities[self.module_name + "." + dev_name] = led_fn

                elif (dev_name.startswith("filter_wheel")):
                    settings = devices.get(dev_name)
                    protocol_positions = parseFilterSequence(settings)
                    fw_fn = TigerFilterWheelFunctionality(device_mutex = self.controller_mutex,
                                                         filter_wheel = self.controller,
                                                         maximum = settings.get("maximum", 6),
                                                         protocol_length = settings.get("protocol_length", 8),
                                                         protocol_positions = protocol_positions,
                                                         restore_on_stop = settings.get("restore_on_stop", True),
                                                         wheel = settings.get("wheel", 0))
                    self.functionalities[self.module_name + "." + dev_name] = fw_fn
                    self.filter_wheel_functionalities.append(fw_fn)

                else:
                    raise halExceptions.HardwareException("Unknown device " + str(dev_name))

        else:
            self.controller = None
    
    def cleanUp(self, qt_settings):
        if self.controller is not None:
            if self.z_piezo_functionality is not None:
                self.z_piezo_functionality.goAbsolute(
                    self.z_piezo_functionality.getMinimum())
            
            for fn in self.functionalities.values():
                if hasattr(fn, "wait"):
                    fn.wait()
            self.controller.shutDown()

    def getFunctionality(self, message):
        if message.getData()["name"] in self.functionalities:
            fn = self.functionalities[message.getData()["name"]]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : fn}))

    def handleResponse(self, message, response):
        if message.isType("get functionality"):
            if (message.getData()["extra data"] == "z_piezo"):
                self.z_piezo_functionality = TigerVoltageZFunctionality(
                    ao_fn = response.getData()["functionality"],
                    parameters = self.z_piezo_configuration.get("parameters"),
                    microns_to_volts = self.z_piezo_configuration.get("microns_to_volts"))
                
                # Configure controller for voltage Z control.
                self.controller_mutex.lock()
                axis = self.z_piezo_configuration.get("axis")
                mode = self.z_piezo_configuration.get("mode")
                self.controller.zConfigurePiezo(axis, mode)
                self.controller_mutex.unlock()
        
                # Add to dictionary of available functionalities.
                self.functionalities[self.module_name + ".z_piezo"] = self.z_piezo_functionality
            
    def processMessage(self, message):
        if message.isType("configure1"):
            if self.z_piezo_configuration is not None:
                self.sendMessage(halMessage.HalMessage(
                    m_type = "get functionality",
                    data = {"name" : self.z_piezo_configuration.get("ao_fn_name"),
                            "extra data" : "z_piezo"}))
            
        elif message.isType("get functionality"):
            self.getFunctionality(message)
            
        if message.isType("configuration"):
            if message.sourceIs("tcp_control"):
                if self.stage_functionality is not None:
                    self.tcpConnection(message.getData()["properties"]["connected"])

            elif message.sourceIs("mosaic"):
                if self.stage_functionality is not None:
                    self.pixelSize(message.getData()["properties"]["pixel_size"])

        elif message.isType("start film"):
            self.startFilm(message)

        elif message.isType("stop film"):
            self.stopFilm(message)
            
        elif message.isType("tcp message"):
            if self.stage_functionality is not None:
                self.tcpMessage(message)

    def startFilm(self, message):
        if self.stage_functionality is not None:
            super().startFilm(message)
        #
        # Need to use runHardwareTask() here so that we can be sure that the
        # Tiger peripherals will be in the correct state before we start filming.
        #
        if self.shouldRunFilmHardware(message):
            hardwareModule.runHardwareTask(self, message, self.startTigerFilmHardware)

    def shouldRunFilmHardware(self, message):
        return message.getData()["film settings"].runShutters()

    def startTigerFilmHardware(self):
        self.startLED()
        self.startFilterWheels()

    def startLED(self):
        #
        # Set TTL mode for one functionality sets the mode for all functionalities,
        # assuming there is only a single LED driver card.
        #
        set_ttl = False
        for fn_name in self.functionalities:
            if ("led" in fn_name):
                if not set_ttl:
                    self.functionalities[fn_name].setFilmTTLMode(True)
                    set_ttl = True
                self.functionalities[fn_name].setFilmPower()

    def startFilterWheels(self):
        for fn in self.filter_wheel_functionalities:
            fn.startFilm()
                    
    def stopFilm(self, message):
        if self.stage_functionality is not None:
            super().stopFilm(message)
        hardwareModule.runHardwareTask(self, message, self.stopTigerFilmHardware)

    def stopTigerFilmHardware(self):
        self.stopFilterWheels()
        self.stopLED()

    def stopFilterWheels(self):
        for fn in self.filter_wheel_functionalities:
            fn.stopFilm()

    def stopLED(self):
        for fn_name in self.functionalities:
            if ("led" in fn_name):
                self.functionalities[fn_name].setFilmTTLMode(False)
                break
