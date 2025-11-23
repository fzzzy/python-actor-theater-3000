#!/usr/bin/env python3
"""Test static tree actor structure (root -> 2 branches -> 4 leaves)."""

import pytest
import main


def test_tree_static_structure(capsys):
    """Test that tree creates correct structure: 1 root + 2 branches + 4 leaves."""

    main.main(["main.py", "examples/tree_static/actor_root_tree.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "ROOT starting" in output
    assert "ROOT spawning 2 branches..." in output
    assert "ROOT finished spawning" in output
    assert "ROOT finished" in output

    assert output.count("BRANCH started") == 2
    assert output.count("BRANCH spawning 2 leaves...") == 2
    assert output.count("BRANCH finished spawning") == 2

    assert output.count("LEAF started") == 4
    assert output.count("LEAF finished") == 4

    assert "Starting actor system" in output
    assert "Spawning initial parent actor: examples/tree_static/actor_root_tree.pya" in output

    assert "[System] All actors completed!" in output
    assert "[System] All workers completed! Total actors spawned: 7" in output
    assert "[System] Cleanup complete!" in output


def test_tree_static_actor_count(capsys):
    """Test that exactly 7 actors are spawned in the tree."""

    main.main(["main.py", "examples/tree_static/actor_root_tree.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Total actors spawned: 7" in output

    assert output.count("[System] Processing SPAWN from actor") >= 2
    assert "actor_branch.pya" in output

    assert "actor_leaf.pya" in output


def test_tree_static_completion(capsys):
    """Test that tree static example completes successfully."""

    main.main(["main.py", "examples/tree_static/actor_root_tree.pya"], timeout=10)

    captured = capsys.readouterr()
    assert "[System] Cleanup complete!" in captured.out


def test_tree_static_all_finish(capsys):
    """Test that all actors finish successfully."""

    main.main(["main.py", "examples/tree_static/actor_root_tree.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "actor_root_tree.pya) finished" in output
    assert output.count("actor_branch.pya) finished") == 2
    assert output.count("actor_leaf.pya) finished") == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])