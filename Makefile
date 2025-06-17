# Python Actor Theater 3000 Makefile

# Compiler and flags
CC = gcc
CFLAGS = -Wall -Wextra -std=c99
PYTHON_CFLAGS = $(shell python3-config --cflags)
PYTHON_LDFLAGS = $(shell python3-config --ldflags --embed)

# Target executable
TARGET = main

# Source files
SOURCES = main.c

# Object files
OBJECTS = $(SOURCES:.c=.o)

# Default target
all: $(TARGET)

# Build the main executable
$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -o $(TARGET) $(PYTHON_LDFLAGS) -lpthread

# Compile source files to object files
%.o: %.c
	$(CC) $(CFLAGS) $(PYTHON_CFLAGS) -c $< -o $@

# Debug build
debug: CFLAGS += -g -DDEBUG
debug: $(TARGET)

# Release build (optimized)
release: CFLAGS += -O2 -DNDEBUG
release: $(TARGET)

# Clean build artifacts
clean:
	rm -f $(OBJECTS) $(TARGET)

# Force rebuild
rebuild: clean all

# Run the program
run: $(TARGET)
	./$(TARGET)

# Check for Python development headers
check-python:
	@echo "Checking Python configuration..."
	@python3-config --cflags
	@python3-config --ldflags
	@echo "Python check complete."

# Help target
help:
	@echo "Available targets:"
	@echo "  all      - Build the project (default)"
	@echo "  debug    - Build with debug symbols"
	@echo "  release  - Build optimized release version"
	@echo "  clean    - Remove build artifacts"
	@echo "  rebuild  - Clean and build"
	@echo "  run      - Build and run the program"
	@echo "  check-python - Verify Python development setup"
	@echo "  help     - Show this help message"

# Declare phony targets
.PHONY: all debug release clean rebuild run check-python help
