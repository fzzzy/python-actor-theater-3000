# Python Actor Theater 3000

.PHONY: all test clean

all:
	uv run python src/main.py examples/simple/actor_simple_parent.pya

# Run all tests
test:
	uv run pytest src/ -v

clean:
	rm -rf __pycache__ .pytest_cache src/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete


