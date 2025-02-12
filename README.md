# RSP (Remote Serial Protocol) Trace Server

Implements an RSP server that replays a trace

## Introduction

This program implements the most important commands of gdb's Remote Serial Protocol (RSP)
while updating internal CPU state and surrounding memory based on a trace file that is
're-played' instead of actually executing instructions in simulation. The external effect
is that you can have a read-only session in gdb (i.e. exploratory w/o poking on registers
of memory) but fairly uncostrained. For instance you can:
- observe execution instruction flow.
- setup break-points and run until they hit.
- inspect memory and registers.
- evaluate expressions.
- etc.

Since we are running out of a trace instead of directly executing or simulating instructions, we can also debug *bckwards*.

## Application

It is mostly geared towards debugging execution traces generated by simulation in batch
mode (for example a slow RTL simulation of a CPU subsystem) where an interactive
gdb session would be (potentially extrememely) slow or require a considereable setup in
comparison to the most common scenario of running the simulation in batch mode.

Also applicable to instruction set simulators with poor debugging support which can
benefit from debugging out of a trace with more powerful tools as long as they speak RSP, like gdb.

Additionally as a side benefit, reverse debugging is also supported for free (see
`reverse-continue` and `reverse-next` gdb commands) which allow more freedom while inspecting
state around a specific execution point in either direction in time.

A couple of trace converters are provided as examples:
```
    trace_utils +---  spike_trace.py
                |--- sifive_rtl_trace.py
```
Each one converts from respective format to an internal version as a list of dictionary entries.
More formatters can be contributed as needed.

`CpuState` is the base class that allows updating state information (including surronding memory)
Must be speciallized for differnt CPUs (see RiscvCpuState as an specialization) at least to define
its registers. The class also keeps surrounding memory updated

## Caveats

1. The amount of state kept is a rich as the trace. sifive-rtl format for instance does not include
   by default memory updates (I could be wrong), so control flow can be inspected well but querying
   variables / memory locations will give invalid information.

2. Gdb assumes the program is loaded in memory while performing a session (performs some queries) so
   a `load program.elf` is required to transfer relevant sections to remote target state, where
   `program.elf` is the file that contains the application binary in ELF format.

4. gdb has native support for traces in binary format. Conversion to that format is a possible
   direction of work for the future to be explored. The current approach is simple, portable
   (RSP is supported by gdb and lldb for instance) and gets the job done with a high degree of
   functionality for the time being.

## Example Session
```
terminal 1:
    $ ./rsp_trace_server.py spike_trace.log -f spike --port 1234
    ...
    INFO: Creating a new server
    INFO: RSP Server listening on localhost:1234

terminal 2:
    $ gdb
    (gdb) file program.elf
    (gdb) target remote localhost:1234        <-- connect to the serer that runs the trace
    (gdb) load program.elf                    <-- load program m=binary in remote memory
    (gdb) b main   <-- break at the start of main
    (gdb) c        <-- get into main
    (gdb) n        <-- next line
    (gdb) n        <-- next line
    (gdb) p var1   <-- inspect a variable
    (gdb) rn       <-- reverse-next, go back one line/step in time (see also reverse-cont/rc)
    (gdb) c        <-- continue
```
