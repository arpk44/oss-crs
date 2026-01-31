import os
import psutil
import multiprocessing

required_cpus = 16
required_memory = 64

cpu_count = os.cpu_count() # checks CPU count
memory_count = psutil.virtual_memory().total / (1024 ** 3) # checks memory left on the computer

if cpu_count < required_cpus or memory_count == 0:
    print("Machine does not have adequare resources!\nOnly CPU cores and memory is available.\nPlease edit eample_configs/crs-libfuzzer/config-resource.yaml.")
