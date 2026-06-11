
import os, sys


#---------------------------------<< set working directory >>---------------------------------
base_path = ""
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_path)

print(f"Current working directory: {os.getcwd()}")

#---------------------------------<< set working directory >>---------------------------------