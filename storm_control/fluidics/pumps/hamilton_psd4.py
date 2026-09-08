#!/usr/bin/python
# ----------------------------------------------------------------------------------------
# A basic class for the control of the PSD4 syringe pump from Hamilton
# ----------------------------------------------------------------------------------------
# Jeff Moffitt
# 11/20/21
# jeffrey.moffitt@childrens.harvard.edu
#
# ----------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------------------------
import sys
import time
import serial

# Status/config codes the pump can report, and what each one means. Named
# here instead of built inline so the parser methods below just do a lookup.
MOVEMENT_STATUS_CODES = {'@': True, '`': False}
NUM_PORTS_BY_CODE = {'0': 3,
                     '1': 4,
                     '2': 3,
                     '3': 8,
                     '4': 4,
                     '6': 6}

class APump():
    def __init__(self,
                 parameters = False):

        # Define attributes
        self.com_port = parameters.get("pump_com_port", "COM3")
        self.pump_ID = parameters.get("pump_ID", "PSD4")
        self.verbose = parameters.get("verbose", True)
        self.simulate = parameters.get("simulate_pump", False)
        self.serial_verbose = parameters.get("serial_verbose", False)
        self.high_res_mode = parameters.get("high_res", True)
        self.syringe_volume = parameters.get("syringe_volume", 12.5)
        self.syringe_type = parameters.get("syringe_type", "standard")

        self.min_velocity_in_steps_s = 2
        self.max_velocity_in_steps_s = 10000
        self.min_stroke_in_steps = 0
        self.max_stroke_in_steps = None

        # Check syringe type
        if self.syringe_type == "standard":
            self.high_res_step = 24000.0
            self.low_res_step = 3000.0
        elif self.syringe_type == "smooth_flow":
            self.high_res_step = 192000.0
            self.low_res_step = 24000.0
        else:
            print("The provided syringe type for the PSD4 is not valid")
            assert False

        # Define the resolution mode
        if self.high_res_mode:
            self.max_stroke_in_steps = self.high_res_step
        else:
            self.max_stroke_in_steps = self.low_res_step

        self.steps_to_volume = self.syringe_volume/self.max_stroke_in_steps

        # Create serial port
        self.serial = serial.Serial(port = self.com_port,
                                    timeout=0.1)

        # Define initial pump status
        self.flow_status = "Stopped"
        self.speed = 0.0
        self.num_ports = 0

        # Last successfully parsed status, returned by getStatus() whenever a
        # poll fails to produce a valid response, so the GUI keeps showing the
        # last known state instead of the poll loop crashing (see getStatus)
        self.last_status = (False, 0.0, 0.0, 1)

        # Configure pump
        self.configurePump()
        self.identification = "PSD4"

        # Report configuration
        print("--------------------------------")
        print("Configured PSD4 Syringe Pump")
        print("   PSD4 Type: " + str(self.syringe_type))
        print("   Syringe Volume: " + str(self.syringe_volume) + " mL")
        print("   High Res Mode: " + str(self.high_res_mode))
        print("   Steps for Full Fill: " + str(self.max_stroke_in_steps))
        print("   Minimum Speed: " + str(self.min_velocity_in_steps_s * self.syringe_volume * (4/self.high_res_step) * 60 ) + " mL/min")

    # ------------------------------------------------------------------------------------
    # Response parsers — each takes the validated (response, end_pos) that
    # _sendAndParse() has already confirmed is long enough and has an
    # end-of-text marker, and pulls out the one value that call site needs.
    # ------------------------------------------------------------------------------------
    def _parseAcknowledge(self, response, end_pos):
        # Commands that don't return data — a validated response is itself
        # the confirmation, so there's nothing left to extract.
        return True

    def _parseIsMoving(self, response, end_pos):
        status_char = chr(response[2])
        return MOVEMENT_STATUS_CODES[status_char]

    def _parseNumPorts(self, response, end_pos):
        config_char = chr(response[3])
        return NUM_PORTS_BY_CODE[config_char]

    def _parsePositionInmL(self, response, end_pos):
        steps = float(response[3:end_pos].decode())
        return steps * self.steps_to_volume

    def _parseVelocityInmLPerMin(self, response, end_pos):
        steps_per_s = float(response[3:end_pos].decode())
        return steps_per_s * self.syringe_volume * 60 / (self.high_res_step / 4)

    def _parseValvePosition(self, response, end_pos):
        return int(response[3:end_pos].decode())

    # ------------------------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------------------------
    def initializePump(self):
        # A failure here means the pump genuinely isn't responding at startup,
        # so this should still halt initialization rather than silently
        # continuing (unlike a runtime poll failure, which is recoverable)
        if self._sendAndParse("/1ZR\r", self._parseAcknowledge) is None:
            raise RuntimeError("PSD4 pump did not respond to initialization on " + str(self.com_port))

    def configurePump(self):
        # Determine the port configuration
        num_ports = self._sendAndParse("/1?21000R\r", self._parseNumPorts)
        if num_ports is None:
            raise RuntimeError("PSD4 pump did not respond to configuration query on " + str(self.com_port))
        self.num_ports = num_ports

        # Set the resolution
        if self.high_res_mode:
            message = '/1N1R\r'
        else:
            message = '/1N0R\r'

        if self._sendAndParse(message, self._parseAcknowledge) is None:
            raise RuntimeError("PSD4 pump did not respond to resolution mode command on " + str(self.com_port))

    def getStatus(self):
        # Each sub-query below bails out on the first communication failure and
        # returns the last known-good status rather than raising or returning a
        # tuple built from a mix of fresh and missing values. This is what the
        # GUI's polling timer calls every couple of seconds indefinitely, so a
        # transient serial hiccup must degrade to "stale reading" here, not an
        # uncaught exception (which PyQt5 has no safe way to recover from when
        # it escapes a timer callback, and which would take down the whole app).

        # Determine if is moving
        is_moving = self._sendAndParse("/1Q\r", self._parseIsMoving)
        if is_moving is None:
            return self.last_status

        # Determine the syringe position and return in mL
        pos_in_mL = self._sendAndParse('/1?R\r', self._parsePositionInmL)
        if pos_in_mL is None:
            return self.last_status

        # Determine current speed
        vel_in_mLmin = self._sendAndParse('/1?2R\r', self._parseVelocityInmLPerMin)
        if vel_in_mLmin is None:
            return self.last_status

        # Determine valve numerical position
        valve_pos = self._sendAndParse('/1?24000R\r', self._parseValvePosition)
        if valve_pos is None:
            return self.last_status

        self.last_status = (is_moving, pos_in_mL, vel_in_mLmin, valve_pos)
        return self.last_status

    def setPort(self, port_id):
        # Check to see if it is within the number of ports
        if port_id >= self.num_ports:
            print("An invalid port was requested for the PSD4")
            return

        # Set the port
        message = "/1h2500" + str(port_id+1) + "R\r"
        if self._sendAndParse(message, self._parseAcknowledge) is None:
            print("PSD4 did not acknowledge the port change command")

    def close(self):
        self.serial.close()

    def setSpeed(self, fill_speed_in_mLmin):

        # Convert the requested speed to steps per s
        fill_speed_in_mLs = fill_speed_in_mLmin/60
        new_speed_value = int((fill_speed_in_mLs/self.syringe_volume) * (self.high_res_step/4))

        # Coerce to the hardware limits
        if new_speed_value < self.min_velocity_in_steps_s:
            new_speed_value = self.min_velocity_in_steps_s
            print("Coerced pump speed to lowest value")

        if new_speed_value > self.max_velocity_in_steps_s:
            new_speed_value = self.max_velocity_in_steps_s
            print("Coerced pump speed to highest value")

        message = '/1V' + str(new_speed_value) + 'R\r'
        if self._sendAndParse(message, self._parseAcknowledge) is None:
            print("PSD4 did not acknowledge the speed change command")

    def startFill(self, new_volume):
        # Define the volume
        new_step_pos = int(new_volume/self.steps_to_volume)

        # Coerce to the hardware limits
        if new_step_pos < self.min_stroke_in_steps:
            new_step_pos = self.min_stroke_in_steps
            print("Coerced pump fill to lowest value")

        if new_step_pos > self.max_stroke_in_steps:
            new_step_pos = self.max_stroke_in_steps
            print("Coerced pump fill to highest value")

        # Define and write the message
        message = '/1A' + str(new_step_pos) + 'R\r'
        if self._sendAndParse(message, self._parseAcknowledge) is None:
            print("PSD4 did not acknowledge the fill command")

    def stopFill(self):
        message = '/1TR\r'
        if self._sendAndParse(message, self._parseAcknowledge) is None:
            print("PSD4 did not acknowledge the stop command")

    # ------------------------------------------------------------------------------------
    # Discard Stale Bytes Waiting in the Input Buffer
    # ------------------------------------------------------------------------------------
    def flushInputBuffer(self):
        try:
            self.serial.reset_input_buffer()
        except serial.SerialException as error:
            # Port is already gone; read()/write() will surface the same error
            if self.verbose:
                print("Could not reset pump COM port input buffer: " + str(error))

    # ------------------------------------------------------------------------------------
    # Write a Command and Parse its Response
    #  Centralizes the write/read/validate sequence that every command above
    #  needs, so the length/end-of-text/decode checks (and the buffer flush
    #  that keeps write/read pairs in sync) only need to be gotten right once.
    #  Returns the value produced by parser(response, end_pos), or None if the
    #  exchange failed at any stage (short/timed-out read, truncated frame,
    #  or a value the parser couldn't make sense of).
    # ------------------------------------------------------------------------------------
    def _sendAndParse(self, message, parser):
        # See flushInputBuffer(): this runs before every write so that any
        # bytes left over from a previous truncated response can't
        # desynchronize this read.
        self.flushInputBuffer()

        self.write(message)
        response = self.read()

        # Status byte lives at index 2 and real data starts at index 3, so
        # anything shorter than that cannot be a valid frame (also covers the
        # timeout case where readline() returns b"" because nothing arrived)
        if len(response) < 4:
            if self.verbose:
                print("PSD4: no valid response to " + message.strip())
            return None

        end_pos = response.find('\x03'.encode())
        if end_pos == -1:
            # No end-of-text marker means the frame was truncated (e.g. the
            # serial read timed out mid-response); without this check a
            # missing marker silently became a "response[3:-1]" slice instead
            # of a detected failure, which could feed garbage into float()/int()
            if self.verbose:
                print("PSD4: truncated response to " + message.strip())
            return None

        try:
            return parser(response, end_pos)
        except (ValueError, UnicodeDecodeError, KeyError) as error:
            if self.verbose:
                print("PSD4: could not parse response to " + message.strip() + ": " + str(error))
            return None

    # ------------------------------------------------------------------------------------
    # Read from Serial Port
    # ------------------------------------------------------------------------------------
    def read(self):
       # response = self.serial.readline().decode()
        try:
            response = self.serial.readline()
        except serial.SerialException as error:
            # e.g. the COM port was closed/disconnected (cable, USB power
            # management, driver reset); return an empty response so callers
            # treat this exactly like a read timeout instead of crashing
            print("Error reading from pump COM port: " + str(error))
            response = b""

        if self.verbose:
            print("Received: " + str((response, "")))
        return response

    def write(self, message):
        try:
            self.serial.write(message.encode())
        except serial.SerialException as error:
            print("Error writing to pump COM port: " + str(error))
        if self.verbose:
            print("Wrote: " + message[:-1]) # Display all but final carriage return


#
# The MIT License
#
# Copyright (c) 2021 Moffitt Laboratory, Boston Children's Hospital
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
