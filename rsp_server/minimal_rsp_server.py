# See LICENSE.txt
"""
This program implements the most important commands of gdb's Remote Serial Protocol (RSP)
while replaying and updating internal CPU state based on a trace file instead of actually
executing instructions as we go through them. The external effect is that you can have a
read-only session in gdb (i.e. exploratory w/o poking on registers of memory) but fairly
uncostrained. You can:
- observe execution
- setup break-points
- inspect memory and registers
- evaluate expressions
- etc.

APPLICATION: it is mostly geared to debugging execution traces generated by simulation in
batch mode (for example a slow RTL simulation of a CPU subsystem) where an interactive
gdb session would be extremely slow.

Also applicable to instruction set simulators with poor debugging support which can
benefit from debugging out of a trace.

Additionally as a side-effect benefit, reverse debugging is also supported for free (see
reverse-continue and reverse-next gdb commands).

A couple of trace converters are provided as examples:
    trace_utils -- spike_trace.py
                |- sifive_rtl_trace.py

Each one converts from respective format to an internal version as a list of dictionary entries
More formatters can be contributed as needed.

CpuState is the base class that allows updating state information (including surronding memory)
Must be speciallized for differnt CPUs (see RiscvCpuState as an specialization) at least to define
its registers. The class also keeps surrounding memory updated

CAVEATS:

The amount of state kept is a rich as the trace. sifive-rtl format for instance does not include
by default memory updates, so control flow can be inspected well but querying variables / memory
locations will give invalid information.


"""
import logging
import re
import socket
import sys
import threading
import traceback


from .cpu_state import CpuState
from .rsp_utils import swap_endianess, get_bytes_checksum, get_checksum


ALLOW_MULTIPLE_CONNECTIONS = False


class MinimalRspServer:
    """
    TCP/IP server that replies to RSP requests from gdb
    pretending to be a real target when in reality is just interpreting
    a trace file
    """

    def __init__(
        self,
        trace: dict,
        cpu_state: CpuState,
        host: str = "localhost",
        port: int = 1234,
    ):
        self.trace = trace
        self.rev_trace = [{} for _ in trace]
        self.cpu_state = cpu_state
        self.trace_idx = 0
        self.host = host
        self.port = port
        self.breakpoints = set()  # Set of breakpoints (PC values)
        self.cont_thread = -1
        self.state_query_thread = -1

    def start(self):
        """Start the RSP server and listen for incoming GDB connections."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen(1)
        logging.info("RSP Server listening on %s:%s", self.host, self.port)

        if ALLOW_MULTIPLE_CONNECTIONS:
            while self.cpu_state.running:
                client_socket, addr = server_socket.accept()
                logging.info("Connection from %s", addr)
                client_thread = threading.Thread(
                    target=self.handle_client, args=(client_socket,)
                )
                client_thread.start()
        else:
            try:
                client_socket, addr = server_socket.accept()
                logging.info("Connection from %s", addr)
                self.handle_client(client_socket)
            except KeyboardInterrupt:
                print("...Ctrl-C detected. Exiting...")
                sys.exit(0)

        logging.info("CPU no longer in running state")

    def handle_client(self, client_socket):
        """Handle incoming RSP commands from GDB."""
        try:
            while True:
                command, checksum_ok = self._recv_packet(client_socket)
                if not command:
                    break
                if not checksum_ok:
                    logging.error("checksum NOT OK")
                if checksum_ok:
                    self._send(client_socket, "+")
                    response = self.handle_command(command)
                    if response is not None:
                        self._send_packet(client_socket, response)
                else:
                    self._send(client_socket, "-")
        except Exception as e:
            traceback.print_exc()
            logging.error("Error: %s", e)
        finally:
            client_socket.close()
            logging.info("Client disconnected")

    def _step_inner(self):
        if self.trace_idx >= len(self.trace):
            self.stop()
            return False
        entry = self.trace[self.trace_idx]
        rev_entry = self.cpu_state.update(entry)
        self.rev_trace[self.trace_idx] = rev_entry
        self.trace_idx += 1
        return True

    def _reverse_step_inner(self):
        if self.trace_idx <= 0:
            self.stop()
            return False
        self.trace_idx -= 1
        rev_entry = self.rev_trace[self.trace_idx]
        self.cpu_state.update(rev_entry)
        return True

    def _step(self):
        self._step_inner()
        if self.cpu_state.pc() in self.breakpoints:
            return "S05"  # Signal 5 (TRAP)
        return "S05"  # Signal 5 (TRAP)

    def _cont(self):
        while self._step_inner():
            if self.cpu_state.pc() in self.breakpoints:
                return "S05"  # Just signal that we stopped at a breakpoint
        self.stop()
        return "W00"  # we stopped at the end of the trace.

    def _reverse_step(self):
        self._reverse_step_inner()
        if self.cpu_state.pc() in self.breakpoints:
            return "S05"  # Signal 5 (TRAP)
        return "S05"  # Signal 5 (TRAP)

    def _reverse_cont(self):
        while self._reverse_step_inner():
            if self.cpu_state.pc() in self.breakpoints:
                return "S05"  # Just signal that we stopped at a breakpoint
        self.stop()
        return "W00"  # we stopped at the end of the trace.

    def handle_command(self, command):
        """Handle RSP commands from GDB."""
        if command.startswith("qSupported"):
            return (
                "qXfer:features:read-;swbreak-;hwbreak+;vContSupported+;"
                + "multiprocess-;QStartNoAckMode-;ReverseContinue+;ReverseStep+"
            )

        if command == "?":  # Reason for the stop
            return "S05"  # Signal 5 (TRAP) indicates a breakpoint

        if command == "g":  # Return register values
            return "".join(
                swap_endianess(f"{reg:016x}")
                for reg in self.cpu_state.registers
            )

        if command.startswith("G"):  # Write registers
            reg_values = command[1:]
            for i in range(self.cpu_state.NUM_REGISTERS):
                regval = swap_endianess(reg_values[i * 16 : (i + 1) * 16])
                self.cpu_state.registers[i] = int(regval, 16)
            return "OK"

        if command.startswith("p"):  # Read register
            if match := re.match(r"p([0-9a-fA-F]+)", command):
                reg_num = int(match.group(1), 16)
                if reg_num < self.cpu_state.NUM_REGISTERS:
                    value = self.cpu_state.registers[reg_num]
                else:
                    logging.warning(
                        "Unrecognized register number %s on read", reg_num
                    )
                    value = 0
                return swap_endianess(f"{value:016x}")
        elif command.startswith("P"):  # Read register
            if match := re.match(r"P([0-9a-fA-F]+)=([0-9a-fA-F]+)", command):
                reg_num = int(match.group(1), 16)
                value = int(swap_endianess(match.group(2)), 16)
                if reg_num < self.cpu_state.NUM_REGISTERS:
                    self.cpu_state.registers[reg_num] = value
                else:
                    logging.warning(
                        "Unrecognized register number %s on write", reg_num
                    )
                return "OK"
        elif command.startswith("m"):  # Read memory
            if match := re.match(r"m([0-9a-fA-F]+),([0-9a-fA-F]+)", command):
                hex_addr = match.group(1)
                length = int(match.group(2), 16)
                return self.cpu_state.get_mem(hex_addr, length)
        elif command.startswith("M"):  # Write memory
            if match := re.match(
                r"M([0-9a-fA-F]+),([0-9a-fA-F]+):([0-9a-fA-F]+)", command
            ):
                hex_addr = match.group(1)
                length = int(match.group(2), 16)
                hex_data = match.group(3)
                self.cpu_state.set_mem(hex_addr, hex_data, length)
                return "OK"
        elif command.startswith("c"):  # Continue execution
            return self._cont()
        elif command.startswith("s"):  # Step execution
            return self._step()
        elif command.startswith("bc"):  # back continue execution
            return self._reverse_cont()
        elif command.startswith("bs"):  # back step
            return self._reverse_step()
        elif command.startswith("D"):  # Detach
            self.stop()
            return "OK"
        elif command.startswith(
            "H"
        ):  # Hc or Hg to set thread id for c/g operations
            if command[1] == "c":
                self.cont_thread = int(command[2:])
                return "OK"
            if command[1] == "g":
                self.state_query_thread = int(command[2:])
                return "OK"
            # fallthru
        elif command == "qC":
            return str(self.cont_thread)
        elif command.startswith("Z"):  # Insert a breakpoint
            if match := re.match(r"Z([0-9]),([0-9a-fA-F]+),([0-9])", command):
                _z_type = int(match.group(1))
                addr = int(match.group(2), 16)
                _mode = int(match.group(3))
                self.breakpoints.add(addr)
                return "OK"
        elif command.startswith("z"):  # Remove a breakpoint
            if match := re.match(r"z([0-9]),([0-9a-fA-F]+),([0-9])", command):
                _z_type = int(match.group(1))
                addr = int(match.group(2), 16)
                _mode = int(match.group(3))
                self.breakpoints.discard(addr)
                return "OK"
        elif (
            command == "qSymbol::"
        ):  # we are given the chance to query symbols, no need
            return "OK"
        elif command == "vMustReplyEmpty":
            return ""  # just reply empty
        elif command == "qAttached":
            return "1"  # Yes, GDB is attached to this process
        elif command.startswith("vCont"):
            return self._handle_vcont(command)

        logging.warning("Unknown command: %s", command)
        return ""

    def _handle_vcont(self, command):
        if command == "vCont?":  # GDB asking for supported actions
            return "vCont;c;s"  # We support continue (c) and step (s)
        actions = command[6:].split(";")  # Extract vCont;c;s:-1
        response = "OK"  # Store the response for the final action
        for action in actions:
            if not action:
                continue  # Skip if empty
            action_type, *thread_id = action.split(":")
            if not thread_id:
                thread_id = "-1"  # Default to all threads
            if action_type == "s":  # Single-step
                response = self._step()
            elif action_type == "c":  # Continue
                response = self._cont()
        return response

    def _recv_packet(self, client_socket):
        """Receive an RSP packet from the client."""
        data = b""
        res_ok = False
        cumm_rx = b""
        while True:
            byte = client_socket.recv(1)
            if not byte:
                return None, res_ok
            cumm_rx += byte
            if byte == b"$":
                data = b""
            elif byte == b"#":
                rx_checksum = client_socket.recv(2)  # Read the 2-byte checksum
                cumm_rx += rx_checksum
                packet_checksum = int(rx_checksum, 16)
                computed_checksum = get_bytes_checksum(data)
                res_ok = packet_checksum == computed_checksum
                logging.debug("<- %s", cumm_rx.decode("utf-8"))
                break
            else:
                data += byte
        return data.decode("utf-8"), res_ok

    def _send(self, client_socket, data: str):
        client_socket.sendall(data.encode("utf-8"))
        logging.debug("-> %s", data)

    def _send_packet(self, client_socket, data: str):
        """Send an RSP packet to the client."""
        if data is None:
            return
        checksum = get_checksum(data)
        self._send(client_socket, f"${data}#{checksum:02x}")

    def stop(self):
        """Stop the server."""
        self.cpu_state.running = False
