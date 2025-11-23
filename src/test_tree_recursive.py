#!/usr/bin/env python3
"""Test recursive binary tree actor structure."""

import pytest
import main


def test_tree_recursive_structure(capsys):
    """Test that recursive tree creates binary tree with depth 0, 1, 2."""

    main.main(["main.py", "examples/tree_recursive/actor_tree_root.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Starting binary tree spawn test" in output
    assert "Creating root actor (depth 0, max_depth 2)" in output
    assert "Expected actors: 1 + 2 + 4 = 7 total" in output
    assert "Root spawned" in output
    assert "Tree spawn test complete" in output

    assert "Spawning 2 children at depth 1" in output  # From depth 0 actor
    assert output.count("Spawning 2 children at depth 2") == 2  # From 2 depth 1 actors
    assert output.count("Spawned 2 children from depth") == 3  # depth 0 and 2x depth 1

    assert output.count("Leaf node at depth 2 (max depth reached)") == 4

    assert output.count("finished") >= 7  # At least 7 tree actors finish

    assert "Starting actor system" in output
    assert "Spawning initial parent actor: examples/tree_recursive/actor_tree_root.pya" in output
    assert "[System] All actors completed!" in output
    assert "[System] Cleanup complete!" in output


def test_tree_recursive_actor_count(capsys):
    """Test that exactly 8 actors are spawned (1 root spawner + 7 tree actors)."""

    main.main(["main.py", "examples/tree_recursive/actor_tree_root.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Total actors spawned: 8" in output

    assert output.count("actor_tree.pya") >= 7  # At least 7 tree actors spawned


def test_tree_recursive_message_passing(capsys):
    """Test that depth messages are correctly passed through the tree."""

    main.main(["main.py", "examples/tree_recursive/actor_tree_root.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Actor started, waiting for depth message..." in output
    assert "Received message:" in output

    assert "'depth': 0" in output or "depth: 0" in output or "depth=0" in output
    assert "'max_depth': 2" in output or "max_depth: 2" in output or "max_depth=2" in output


def test_tree_recursive_completion(capsys):
    """Test that recursive tree example completes successfully."""

    main.main(["main.py", "examples/tree_recursive/actor_tree_root.pya"], timeout=10)

    captured = capsys.readouterr()
    assert "[System] Cleanup complete!" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])