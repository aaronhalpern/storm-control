@rem activate the HAL python enviroment
cd C:\Users\Josh\Aaron\storm-control\storm_control
call activate halenv

@rem in case there is a residual voltage on the piezo AO, reset it to zero:
python piezo_AO_zero.py

@rem You can select which configuration to file to load when starting HAL
@rem note that HAL will not start if the camera (andor or hamamatsu) is not selected properly
@rem to select proper file below, remove the "@rem" to uncomment a line and add a @rem to comment out

@rem python hal4000\hal4000.py "hal4000\xml\scope1_Aaron_190619_None.xml"
@rem python hal4000\hal4000.py "hal4000\xml\scope1_Aaron_190619_Ham.xml"
python hal4000\hal4000.py "hal4000\xml\scope1_Aaron_190619_Andor.xml"
@rem python hal4000\hal4000.py "hal4000\xml\none_config.xml"
@rem python hal4000\hal4000.py "hal4000\xml\scope1_Andor_Only.xml"

pause