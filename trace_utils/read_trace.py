# see LICENSE.txt

import copy
import logging
import sys
from typing import List
from .trace_utils import hexstr_to_int


def normalize_trace(trace: List[dict]) -> List[dict]:
    """
    Convert a few items to decimal as it simplifies keeping the format
    of reverse trace entries the same with less formatting to create them
    """
    new_trace = []
    for trace_entry in trace:
        new_trace_entry = copy.deepcopy(trace_entry)
        # convert PC to decimal
        new_trace_entry["pc"] = hexstr_to_int(new_trace_entry["pc"])
        # convert values on register writes to decimal
        if (rw := new_trace_entry.get("rw")) is not None:
            new_rw = {}
            for reg_name, hex_value in rw:
                if reg_name.startswith("x"):  # register index is in decimal
                    new_rw[reg_name] = hexstr_to_int(hex_value)
            new_trace_entry["rw"] = new_rw
        new_trace.append(new_trace_entry)
    return new_trace


def read_trace(trace_file: str, trace_format: str) -> list:
    """
    Read a trace file depending on format specified and
    convert to internal format
    """
    if trace_format == "json":
        import json

        logging.info(f"Processing json trace {trace_file}")
        with open(trace_file, "r") as f:
            trace = json.load(f)
        return trace

    if trace_format == "spike":
        from .spike_trace import read_spike_trace

        logging.info("Processing spike log: {trace_file}")
        return read_spike_trace(trace_file)

    if trace_format == "sifive-rtl":
        from .sifive_rtl_trace import read_sifive_rtl_trace

        logging.info("Processing sifive rtl log: {trace_file}")
        return read_sifive_rtl_trace(trace_file)

    logging.error(f"Unhandled {trace_format=}")
    sys.exit(0)
