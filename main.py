#!/usr/bin/env python3

import asyncio
import json
import os
import threading
from queue import Queue


class Actor:
    """An actor with a mailbox and script to execute."""

    _next_id = 0
    _id_lock = threading.Lock()

    def __init__(self, script_path):
        with Actor._id_lock:
            self.id = Actor._next_id
            Actor._next_id += 1
        self.script_path = script_path
        self.mailbox = Queue()

    def __repr__(self):
        return f"Actor({self.id}, {self.script_path})"


def make_actor_print(actor):
    """Create a closure that prints with actor prefix.

    Args:
        actor: Actor instance

    Returns:
        Callable that takes *args, **kwargs and prints them with actor prefix
    """
    def print(*args, **kwargs):
        __builtins__.print(f"[Actor {actor.id}]", *args, **kwargs)
    return print


def make_recv(actor):
    """Create a closure that receives messages from actor's mailbox.

    Args:
        actor: Actor instance

    Returns:
        Async callable that awaits and returns deserialized message from mailbox
    """
    async def recv():
        # Run the blocking get() in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        json_msg = await loop.run_in_executor(None, actor.mailbox.get)
        # Deserialize from JSON to enforce isolation
        msg = json.loads(json_msg)
        return msg
    return recv


def make_cast_for_actor(actor):
    """Create a cast closure for a specific actor.

    Args:
        actor: The actor instance

    Returns:
        Callable that takes a message, serializes it to JSON, and sends to mailbox
    """
    def cast(message):
        # Serialize to JSON to enforce isolation (no shared state)
        json_msg = json.dumps(message)
        actor.mailbox.put(json_msg)
    return cast


def make_spawn(work_queue, all_actors):
    """Create a closure that spawns new actors.

    Args:
        work_queue: Queue where ready actors are placed for workers
        all_actors: Dict to track all actors by ID

    Returns:
        Callable that takes a script path, spawns an actor, and returns its cast function
    """
    def spawn(script_path):
        actor = Actor(script_path)
        all_actors[actor.id] = actor
        work_queue.put(actor)  # Put actor on work queue to be executed
        __builtins__.print(f"[System] Spawned {actor}")
        return make_cast_for_actor(actor)  # Return cast function for this actor
    return spawn


def worker(work_queue, worker_id, spawn_fn):
    """Worker thread that executes actors from the work queue.

    Args:
        work_queue: Queue of actors ready to be executed
        worker_id: ID of this worker thread
        spawn_fn: Spawn closure to pass to actors
    """
    while True:
        # Get next actor to execute
        actor = work_queue.get()

        if actor is None:  # Sentinel to exit
            break

        __builtins__.print(f"[Worker {worker_id}] Executing {actor}")

        # Read and execute the actor's script
        with open(actor.script_path) as f:
            actor_code = f.read()

        # Create namespace with standard library modules
        namespace = {
            "asyncio": asyncio,
            "__name__": "__main__",
        }

        # Execute the actor script (defines main function)
        exec(actor_code, namespace)

        # Get the main function and call it with injected closures
        main_func = namespace.get("main")
        if main_func is None:
            __builtins__.print(f"[Worker {worker_id}] ERROR: {actor} has no main() function")
            continue

        if not asyncio.iscoroutinefunction(main_func):
            __builtins__.print(f"[Worker {worker_id}] ERROR: {actor} main() must be async")
            continue

        # Run async main with injected closures (recv, spawn, print)
        asyncio.run(main_func(
            make_recv(actor),
            spawn_fn,
            make_actor_print(actor),
        ))

        __builtins__.print(f"[Worker {worker_id}] {actor} finished")


def main():
    # Setup
    num_workers = os.cpu_count() or 1
    print(f"Starting actor system with {num_workers} worker threads\n")

    # Create work queue and actor tracking
    work_queue = Queue()
    all_actors = {}

    # Create spawn function
    spawn_fn = make_spawn(work_queue, all_actors)

    # Create worker threads
    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker,
            args=(work_queue, i, spawn_fn),
            daemon=False
        )
        t.start()
        threads.append(t)

    # Spawn the initial parent actor
    print("[System] Spawning initial parent actor\n")
    spawn_fn("actor_parent.pya")

    # Wait for actors to spawn and process messages
    import time
    time.sleep(5)

    # Send sentinel values to workers to shut down
    print("\n[System] Shutting down workers...")
    for _ in range(num_workers):
        work_queue.put(None)

    # Wait for all workers to complete
    for t in threads:
        t.join()

    print(f"\n[System] All workers completed! Total actors spawned: {len(all_actors)}")


if __name__ == "__main__":
    main()
