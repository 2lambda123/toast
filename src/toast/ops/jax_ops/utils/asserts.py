import os
from .mutableArray import MutableJaxArray
import jax.numpy as jnp
from ....utils import Logger, Environment

use_debug_assert = ("TOAST_LOGLEVEL" in os.environ) and (os.environ["TOAST_LOGLEVEL"] in ["DEBUG", "VERBOSE"])
"""
Assert is used only if `TOAST_LOGLEVEL` is set to `DEBUG`.
"""

def assert_data_localization(function_name, use_accel, inputs, outputs):
    """
    Checks that the data position (GPU|CPU) is consistent with the `use_accel` flag.
    This function will send a warning in case of inconsisency if `TOAST_LOGLEVEL` is set to `DEBUG`.
    """
    if use_debug_assert:
        # checks if the data is on GPU
        gpu_input = any(isinstance(x, MutableJaxArray) or isinstance(x, jnp.ndarray) for x in inputs)
        gpu_output = any(isinstance(x, MutableJaxArray) or isinstance(x, jnp.ndarray) for x in outputs)

        if use_accel:
            # checks that at least some inputs the GPU
            if not gpu_input:
                if gpu_output:
                    msg = f"function '{function_name}' has NO input on GPU (only some output data) but is running with use_accel=True"
                else:
                    msg = f"function '{function_name}' has NO input on GPU but is running with use_accel=True"
                log = Logger.get()
                log.warning(msg)
                #raise RuntimeError("GPU localisation error")
        else:
            # checks that no data is on the GPU
            if gpu_input or gpu_output:
                msg = f"function '{function_name}' has an input on GPU but is running with use_accel=False"
                log = Logger.get()
                log.warning(msg)
                #raise RuntimeError("GPU localisation error")

