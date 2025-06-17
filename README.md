# Python Actor Theater 3000

A C program that demonstrates concurrent execution of Python scripts using multiple OS threads and Python subinterpreters.

## Project Overview

This project implements a multi-threaded C application that demonstrates concurrent execution of Python scripts using multiple OS threads and Python subinterpreters. The architecture includes:

- **Main thread**: Runs the main Python interpreter executing `main.py` for signal handling
- **Worker threads**: Two separate OS threads, each running its own Python subinterpreter to execute different Python scripts (`a.py` and `b.py`) concurrently

The main interpreter has unique process-global responsibilities like signal handling, while the sub-interpreters run independently on separate threads.


## Usage
```bash
make
./main
```
