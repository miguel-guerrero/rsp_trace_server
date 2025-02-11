Contents of this folder:

- cpu_state.py
  - Handles CPU estate changes as we transverse the trace (ether forward or backwards)
- riscv_cpu_state.py
  - Specialization of the above for a generic RISC-V cpu to show how this can be extended to other CPUs
- minimal_rsp_server.py
  - Implements RSP server functionality (understands RSP protocol initiated by gdb) and replies appropriately
    updating CPU state as per the contents of the associated trace, instead of simulating or running what is
    asked for.
- rsp_utils.py
  - Collecion of utilities
