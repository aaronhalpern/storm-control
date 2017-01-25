#
# A very simple test of Steve.
#

from PyQt5 import QtCore
import time

import pytestqt

import storm_control.sc_library.hdebug as hdebug
import storm_control.sc_library.parameters as params

import storm_control.steve.steve as steve

def test_steve_starts(qtbot):

    parameters = params.parameters("./steve_xml/test_default.xml")
    hdebug.startLogging(parameters.get("directory") + "logs/", "steve")
    mainw = steve.Window(parameters)
    mainw.show()

    qtbot.addWidget(mainw)

    # Run for about 0.5 seconds.
    qtbot.wait(500)

