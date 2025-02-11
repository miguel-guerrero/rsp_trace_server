#!/bin/bash
ISA=rv64imafdc
make ISA=$ISA
spike --log-commits --isa=$ISA -l --log=spike.log pk main
