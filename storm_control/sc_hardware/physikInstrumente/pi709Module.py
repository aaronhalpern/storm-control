'''
PI voltage Z module

Alistair Boettiger, 07/19
adapted from Ludl (voltage controlled) Z stage functionality, George 02/18
not currently implemented -- it looks like I get all I need from mclVoltageZModule
possibly update for aesthetic quality later on.

Aaron update for pi709
connect to PI to enable analog control
check if closed loop is active
download pipython from below
https://github.com/PI-PhysikInstrumente/PIPython
activate hal
python setup.py install
'''

from PyQt5 import QtCore

import storm_control.sc_hardware.baseClasses.voltageZModule as voltageZModule

from pipython import GCSDevice, pitools 

class PiVoltageZ(voltageZModule.VoltageZ):
    """
    This is a taken from the Mad City Labs stage in analog control mode.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(module_params, qt_settings, **kwds)
        
        device_name = self.configuration.get("device_name")
        serial_number = self.configuration.get("serial_number")
        
        self.pidevice = GCSDevice(device_name)
        self.pidevice.ConnectUSB(serialnum = str(serial_number))
        
        try:
            print('\tconnected to PI device {}'.format(self.pidevice.qIDN().strip()))
        except:
            print('\tunable to connect to PI device')
        
        # set analog control active
        print('\tsetting analog control active')
        self.pidevice.SPA('Z', 0x06000500, 2)
        
        # check closed loop mode
        qsvo = self.pidevice.qSVO()
        if qsvo['Z'] == True:
            print('\tclosed loop feedback active')
        else:
            print('\t***WARNING closed loop inactive WARNING***')
    
    def shutDown(self):
        #self.pidevice.StopAll(noraise=True)
        #pitools.waitonready(self.pidevice)  # there are controllers that need some time to halt all axes
        self.pidevice.CloseConnection()
        

if __name__ == "__main__":

    with GCSDevice('E-709') as pidevice:
        pidevice.ConnectUSB(serialnum = '0121007897')
        print('PI device info: {}.'.format(pidevice.qIDN().strip()))
        
        print('Current position: {}'.format(pidevice.qPOS()['Z']))
        
        print('Current input mode')
        spa = pidevice.qSPA()
        mode = spa['Z'][100664576]
        if mode == 0:
            print('digital mode')
        elif mode == 2:
            print('analog mode')
        else:
            print('unknown mode')
        
        print('Closed loop mode: {}'.format(pidevice.qSVO()['Z']))
    
    # this should set it to analog control mode
    #pidevice.SPA('Z', 0x06000500, 2)