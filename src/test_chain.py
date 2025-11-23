#!/usr/bin/env python3
"""Test chain actor communication (root -> branch -> leaf)."""

import pytest
import main


def test_chain_three_actors(capsys):
    """Test chain of three actors: root -> branch -> leaf."""

    main.main(["main.py", "examples/chain/actor_root_chain.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "ROOT starting" in output
    assert "ROOT spawning 1 branch..." in output
    assert "ROOT sending message to branch..." in output
    assert "ROOT finished" in output

    assert "BRANCH started, waiting for message..." in output
    assert "BRANCH received: hello from root" in output
    assert "BRANCH spawning 1 leaf..." in output
    assert "BRANCH sending message to leaf..." in output
    assert "BRANCH finished" in output

    assert "LEAF started, waiting for message..." in output
    assert "LEAF received: hello from branch (got: hello from root)" in output
    assert "LEAF finished" in output

    assert "Starting actor system" in output
    assert "Spawning initial parent actor: examples/chain/actor_root_chain.pya" in output

    assert "[System] Processing SPAWN from actor" in output
    assert "actor_branch_recv.pya" in output
    assert "parent was actor" in output

    assert "actor_leaf_recv.pya" in output

    assert "examples/chain/actor_root_chain.pya) finished" in output
    assert "actor_branch_recv.pya) finished" in output
    assert "actor_leaf_recv.pya) finished" in output

    assert "[System] All actors completed!" in output
    assert "[System] All workers completed! Total actors spawned: 3" in output
    assert "[System] Cleanup complete!" in output


def test_chain_message_passing(capsys):
    """Test that messages are correctly passed through the chain."""

    main.main(["main.py", "examples/chain/actor_root_chain.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "ROOT sending message to branch..." in output

    assert "BRANCH received: hello from root" in output
    assert "BRANCH sending message to leaf..." in output

    assert "LEAF received: hello from branch (got: hello from root)" in output


def test_chain_completion(capsys):
    """Test that chain example completes successfully."""

    main.main(["main.py", "examples/chain/actor_root_chain.pya"], timeout=10)

    captured = capsys.readouterr()
    assert "[System] Cleanup complete!" in captured.out


def test_chain_actor_count(capsys):
    """Test that exactly 3 actors are spawned in the chain."""

    main.main(["main.py", "examples/chain/actor_root_chain.pya"], timeout=10)

    captured = capsys.readouterr()
    output = captured.out

    assert "Total actors spawned: 3" in output

    assert "ROOT starting" in output
    assert "BRANCH started" in output
    assert "LEAF started" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])