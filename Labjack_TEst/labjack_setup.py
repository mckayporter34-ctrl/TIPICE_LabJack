# labjack_setup.py
import ctypes 
import os 
import LabJackPython
import u3

def get_u3():
    env_path = "/Users/mckayporter/TIPICE/"
    # Load libraries
    ctypes.CDLL(os.path.join(env_path, "libusb-1.0.0.dylib"), mode=ctypes.RTLD_GLOBAL)
    exo = ctypes.CDLL(os.path.join(env_path, "liblabjackusb.dylib"), mode=ctypes.RTLD_GLOBAL)
    # Inject driver
    LabJackPython.staticLib = exo
    return u3.U3()
