# See LICENSE.txt
"""Derives from CpuState, customizes some values for RISC-V 64"""

from .cpu_state import CpuState


class RiscvCpuState(CpuState):
    """
    Keeps and updates the state of the CPU based on a log entry
    Customized for a Risc-V CPU
    """

    PC_REG = 32
    NUM_REGISTERS = PC_REG + 1

    def __init__(self, init_pc: int = 0):
        super().__init__(init_pc)

    def name(self) -> str:
        return "riscv-64"
