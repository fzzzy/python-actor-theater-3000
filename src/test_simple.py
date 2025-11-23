#!/usr/bin/env python3
"""Test simple parent-child actor communication."""

import pytest
import main


def test_simple_parent_child(capsys):
    """Test simple parent spawns child and sends one message."""

    main.main(["main.py", "examples/simple/actor_simple_parent.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Parent starting, spawning child..." in output
    assert "Parent sending message..." in output
    assert "Parent finished" in output
    assert "received message: hello" in output
    assert "Child finished" in output

    assert "Starting actor system" in output
    assert "Spawning initial parent actor" in output
    assert "[System] Processing SPAWN from actor" in output
    assert "parent was actor" in output
    assert "examples/simple/actor_simple_parent.pya) finished" in output
    assert "[System] All actors completed!" in output
    assert "[System] All workers completed! Total actors spawned: 2" in output
    assert "[System] Cleanup complete!" in output


def test_simple_completion(capsys):
    """Test that simple example completes successfully."""

    main.main(["main.py", "examples/simple/actor_simple_parent.pya"], timeout=10)

    captured = capsys.readouterr()
    assert "[System] Cleanup complete!" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])