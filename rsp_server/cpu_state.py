"""
Contains CpuState class which tracks main cpu architecture
defining parameters and common helper methods
"""

# See LICENSE.txt

from abc import abstractmethod
import logging
from .rsp_utils import hexstr_to_int


# value to return when reading uninitialized memory
UNSET_MEM_VALUE = 0xCA


def _format_non_init(x: list) -> str:

    result = []

    def emit(base, run) -> str:
        result.append(f"{base:x}..{base+run:x}" if run >= 1 else f"{base:x}")

    prev = None
    for hex_addr in x:
        assert isinstance(hex_addr, str)
        addr = int(hex_addr, 16)
        if prev is None:
            base, run = addr, 0
            prev = base
        else:
            if addr == prev + 1:
                run += 1
            else:
                emit(base, run)
                base, run = addr, 0
            prev = addr
    emit(base, run)
    return ", ".join(result)


class CpuState:
    """
    Keeps and updates the state of the CPU based on a log entry
    """

    # number of register in gdb machine def for this CPU as return by 'g'
    NUM_REGISTERS = 0

    # integer index for PC register in gdb machine def for this CPU
    PC_REG = 0

    def __init__(self, init_pc: int):
        self.memory = (
            {}
        )  # Memory is represented as a dictionary of bytes {address: value}
        self.registers = [0] * self.NUM_REGISTERS
        self.set_pc(init_pc)  # Initial program counter
        self.running = True

    @abstractmethod
    def name(self) -> str:
        """must be overridden"""

    def pc(self) -> int:
        """return contents of PC register"""
        return self.registers[self.PC_REG]

    def set_pc(self, value: int) -> int:
        """sets the contents of PC register"""
        self.registers[self.PC_REG] = value

    def set_mem(self, hex_addr: str, hexstr: str, length=-1):
        """
        Given a hex_addr and hex data string, set corresponding bytes in memory
        hex_str is a sequence if bytes in hex ascii in little endian. E.g.
            "1F1112" -> 31, 17, 18 from lower to higher address
        """
        assert length < 0 or length == len(hexstr) // 2
        assert len(hexstr) % 2 == 0
        addr = hexstr_to_int(hex_addr)
        for offs in range(len(hexstr) // 2):
            self.memory[addr + offs] = hexstr_to_int(hexstr[offs : offs + 2])

    def get_mem(self, hex_addr: str, num_bytes: int, verbose=True) -> str:
        """
        Given a hex_addr (e.g. 'ab10') and length in bytes (e.g. 3) return
        hex data string from memory the format of the returned hex_str as as
        in 'set_mem' (e.g. 'aabbcc' where 'aa' == *ab10, 'bb' == *ab11 etc.)
        """
        addr = hexstr_to_int(hex_addr)
        data_arr = []
        non_init = []
        for i in range(num_bytes):
            if (new_byte := self.memory.get(addr + i)) is None:
                new_byte = UNSET_MEM_VALUE
                non_init.append(f"{addr + i:x}")
            data_arr.append(new_byte)
        if verbose and len(non_init) > 0:
            logging.info(
                "Accessing un-init addr: %s", _format_non_init(non_init)
            )
        return "".join(f"{data_byte:02x}" for data_byte in data_arr)

    def update(self, trace_entry: dict) -> dict:
        """
        Update CPU state based on trace entry contents, also return a reverse
        trace entry used to keep a reverse trace that can reconstruct the
        current state (before this update) from the next one (afer this update)
        """
        # prepare a reverse trace entry to allow to recover the initial
        # steate before the update
        rev_trace_entry = {}
        # pc update
        # save current value in reverse trace
        rev_trace_entry["pc"] = self.pc()
        self.set_pc(trace_entry["pc"])  # update value
        # register writes
        if (rw := trace_entry.get("rw")) is not None:
            rev_trace_entry["rw"] = {}
            for reg, value in rw.items():
                if reg.startswith("x"):  # register index is in decimal
                    reg_number = int(reg[1:])
                    rev_trace_entry["rw"][reg] = self.registers[reg_number]
                    self.registers[reg_number] = value
                else:
                    logging.debug("Ignoring update to register %s", reg)
        # memory writes
        if (mw := trace_entry.get("mw")) is not None:
            rev_trace_entry["mw"] = []
            for mem_addr, hex_value in mw:
                num_bytes = len(hex_value) // 2
                rev_trace_entry["mw"].append(
                    [
                        mem_addr,
                        self.get_mem(mem_addr, num_bytes, verbose=False),
                    ]
                )
                self.set_mem(mem_addr, hex_value)
        # reverse trace entry contains how to recover the initial state
        # after update
        return rev_trace_entry
