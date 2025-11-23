#!/usr/bin/env python3

from concurrent import interpreters
import datetime
import os
import json
import signal
import sys
import time
import threading
from queue import Queue
import uuid


def timestamp():
    """Return current timestamp string for logging."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# Global interpreter pool for reuse across multiple runs (e.g., between tests)
_global_interp_pool: "Queue[interpreters.Interpreter]" = Queue()

# Pre-populate the pool with one interpreter per core
# Pre-import asyncio to warm up each interpreter
_num_cores = os.cpu_count() or 1
for _ in range(_num_cores):
    interp = interpreters.create()
    interp.exec("import asyncio")
    _global_interp_pool.put(interp)


class Actor:
    """An actor with its own subinterpreter, mailbox, and state."""

    def __init__(self, script_path, actor_id, run_id, from_subinterps_queue, interp=None):
        self.id = actor_id
        self.run_id = run_id
        self.script_path = script_path
        self.from_subinterps_queue = from_subinterps_queue
        self.mailbox_queue = interpreters.create_queue()
        self.status_queue = interpreters.create_queue()
        self.interp = interp if interp is not None else interpreters.create()
        self.state = "ready"

        self._bootstrap()

    def _bootstrap(self):
        """Initialize the subinterpreter with crank_one_tick and actor runtime."""
        self.interp.prepare_main(
            from_subinterps_queue=self.from_subinterps_queue,
            mailbox_queue=self.mailbox_queue,
            status_queue=self.status_queue
        )

        bootstrap_code = f"""
# Queue objects are already bound via prepare_main()
# from_subinterps_queue, mailbox_queue, status_queue are available
import asyncio
from concurrent import interpreters
import json
import uuid


ACTOR_ID = {self.id}
SCRIPT_PATH = "{self.script_path}"

# Actor state
pending_future = None
user_task = None
loop = None
spawn_requests = {{}}  # request_id → cast function


def spawn(script_path):
    \"\"\"Spawn a new actor and return a cast function for it.\"\"\"
    import os
    request_id = str(uuid.uuid4())

    # Resolve script path relative to current script's directory
    if not os.path.isabs(script_path):
        script_dir = os.path.dirname(os.path.abspath(SCRIPT_PATH))
        script_path = os.path.join(script_dir, script_path)

    signal = f"{{ACTOR_ID}}:SPAWN:{{request_id}}:{{script_path}}"
    from_subinterps_queue.put(signal)

    def make_cast(rid):
        def cast(message):
            json_msg = json.dumps(message)
            signal = f"{{ACTOR_ID}}:CAST:{{rid}}:{{json_msg}}"
            from_subinterps_queue.put(signal)
        return cast

    return make_cast(request_id)

async def recv():
    \"\"\"Receive a message from this actor's mailbox.\"\"\"
    global pending_future

    # Try immediate delivery
    try:
        obj = mailbox_queue.get_nowait()
        return json.loads(obj)
    except interpreters.QueueEmpty:
        pass

    pending_future = asyncio.Future()
    signal = f"{{ACTOR_ID}}:BLOCKED"
    from_subinterps_queue.put(signal)
    return await pending_future

def print(*args, **kwargs):
    \"\"\"Print with actor ID prefix by sending signal to main.\"\"\"
    import io
    import builtins
    import json

    output = io.StringIO()
    builtins.print(f"[Actor {{ACTOR_ID}}]", *args, **kwargs, file=output)
    formatted_output = output.getvalue().rstrip('\\n')

    signal = f"{{ACTOR_ID}}:PRINT:{{json.dumps(formatted_output)}}"
    from_subinterps_queue.put(signal)

def crank_one_tick():
    \"\"\"Execute one iteration of the actor's event loop.

    Returns:
        "ready" - Actor made progress, reschedule
        "blocked" - Actor waiting for message
        "done" - Actor completed
    \"\"\"
    global pending_future, user_task, loop

    if user_task is None:
        with open(SCRIPT_PATH) as f:
            user_code = f.read()

        namespace = {{}}
        exec(user_code, namespace)
        user_main = namespace.get('main')

        if user_main is None:
            status_queue.put("done")
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user_task = loop.create_task(user_main(recv, spawn, print))

    # Check if we can fulfill a pending recv
    if pending_future and not pending_future.done():
        try:
            obj = mailbox_queue.get_nowait()
            msg = json.loads(obj)
            pending_future.set_result(msg)
            pending_future = None
        except interpreters.QueueEmpty:
            status_queue.put("blocked")
            return

    # Drain event loop - process everything ready
    loop.run_until_complete(asyncio.sleep(0))

    if user_task.done():
        status_queue.put("done")
    elif pending_future is not None:
        status_queue.put("blocked")
    else:
        status_queue.put("ready")
"""

        self.interp.exec(bootstrap_code)

    def crank_one_tick(self):
        """Execute one tick of this actor's event loop.

        Returns:
            "ready", "blocked", or "done"
        """
        self.interp.exec("crank_one_tick()")

        status = self.status_queue.get_nowait()
        return status

    def cleanup_namespace(self):
        """Clean up the interpreter's global namespace for reuse.

        Deletes all global variables that were added since initialization,
        allowing the interpreter to be reused for a new actor.

        Returns:
            The cleaned interpreter object.
        """
        cleanup_code = """
initial_globals = {'__builtins__', '__doc__', '__loader__', '__name__', '__package__', '__spec__'}
current_globals = set(globals().keys())
names_to_delete = current_globals - initial_globals

# Delete each added name
for name in names_to_delete:
    try:
        del globals()[name]
    except:
        pass
"""
        try:
            self.interp.exec(cleanup_code)
        except Exception as e:
            print(f"[System] Error cleaning namespace for {self}: {e}")

        return self.interp

    def destroy(self):
        """Destroy this actor's subinterpreter.
        """
        try:
            self.interp.close()
        except Exception as e:
            print(f"[System] Error destroying interpreter for {self}: {e}")

    def __repr__(self):
        return f"Actor({self.id}, {self.script_path})"


def worker(work_queue, worker_id, all_actors, interp_pool, spawn_requests, from_subinterps_queue, next_actor_id):
    """Worker thread that executes actors from the work queue.

    Args:
        work_queue: Queue of actors ready to run
        worker_id: ID of this worker thread
        all_actors: Dict of all actors by ID
        interp_pool: Queue of available interpreters for reuse
        spawn_requests: Dict mapping request_id → actor_id
        from_subinterps_queue: Queue for receiving signals from subinterpreters
        next_actor_id: List with one element [next_id] for tracking actor IDs
    """
    while True:
        # Get next actor to execute
        actor = work_queue.get()
        if actor is None:
            break

        print(f"[{timestamp()}] [Worker {worker_id}] Executing {actor}")
        actor.state = "running"

        try:
            status = actor.crank_one_tick()
        except Exception as e:
            print(f"[{timestamp()}] [Worker {worker_id}] ERROR in {actor}: {e}")
            actor.state = "dead"
            # On error, destroy the interpreter (don't return to pool)
            actor.destroy()
            continue

        if status == "ready":
            actor.state = "ready"
            work_queue.put(actor)
        elif status == "blocked":
            # Check if messages arrived while we were running (level-triggered check)
            try:
                obj = actor.mailbox_queue.get_nowait()
                actor.mailbox_queue.put(obj)
                actor.state = "ready"
                work_queue.put(actor)
            except interpreters.QueueEmpty:
                actor.state = "blocked"
        elif status == "done":
            print(f"[{timestamp()}] [Worker {worker_id}] {actor} finished")
            actor.state = "dead"


def process_one_signal(subsignal, all_actors, work_queue, spawn_requests, pending_messages, from_subinterps_queue, next_actor_id, interp_pool):
    """Process a single signal from a subinterpreter.

    Returns:
        (should_continue, dead_actor_id)
        - should_continue: False if SHUTDOWN, True otherwise
        - dead_actor_id: None if signal was from alive actor, actor_id if from dead actor (for cleanup)
    """
    if subsignal == "SHUTDOWN":
        return (False, None)

    parts = subsignal.split(":", 2)
    actor_id_str, action = parts[0], parts[1]
    actor_id = int(actor_id_str)
    payload = parts[2] if len(parts) > 2 else ""

    actor = all_actors.get(actor_id)
    is_dead = actor and actor.state == "dead"

    if action == "PRINT":
        print_output = json.loads(payload) if payload else ""
        print(print_output)

    elif action == "BLOCKED":
        if actor and actor.state != "dead":
            actor.state = "blocked"

    elif action == "SPAWN":
        payload_parts = payload.split(":", 1)
        request_id, script_path = payload_parts[0], payload_parts[1]

        print(f"[{timestamp()}] [System] Processing SPAWN from actor {actor_id}: {script_path}")
        print(f"[{timestamp()}] [System] SPAWN request_id: {request_id[:8]}...")

        parent_actor = all_actors.get(actor_id)
        if not parent_actor:
            print(f"[{timestamp()}] [System] ERROR: Parent actor {actor_id} not found")
            return (True, None)

        new_actor_id = next_actor_id[0]
        next_actor_id[0] += 1

        try:
            interp = interp_pool.get_nowait()
            print(f"[{timestamp()}] [System] Reusing interpreter from pool for actor {new_actor_id}")
            new_actor = Actor(script_path, new_actor_id, parent_actor.run_id, from_subinterps_queue, interp)
        except Exception:
            new_actor = Actor(script_path, new_actor_id, parent_actor.run_id, from_subinterps_queue)

        all_actors[new_actor.id] = new_actor
        work_queue.put(new_actor)

        spawn_requests[request_id] = new_actor.id
        print(f"[{timestamp()}] [System] Registered request_id {request_id[:8]}... → actor {new_actor.id}")

        if request_id in pending_messages:
            messages = pending_messages.pop(request_id)
            print(f"[{timestamp()}] [System] Delivering {len(messages)} pending messages to actor {new_actor.id}")
            for json_msg in messages:
                new_actor.mailbox_queue.put(json_msg)

        print(f"[{timestamp()}] [System] Spawned {new_actor} (parent was actor {actor_id})")

    elif action == "CAST":
        payload_parts = payload.split(":", 1)
        request_id, json_msg = payload_parts[0], payload_parts[1]

        print(f"[{timestamp()}] [System] CAST from actor {actor_id} with request_id: {request_id[:8]}...")

        target_id = spawn_requests.get(request_id)
        if target_id is None:
            print(f"[{timestamp()}] [System] Actor not yet created for request_id {request_id[:8]}..., queueing message")
            if request_id not in pending_messages:
                pending_messages[request_id] = []
            pending_messages[request_id].append(json_msg)
            return (True, None)

        target = all_actors.get(target_id)
        if target is None:
            print(f"[{timestamp()}] [System] ERROR: Actor {target_id} not found")
            return (True, None)

        target.mailbox_queue.put(json_msg)

        if target.state == "blocked":
            target.state = "ready"
            work_queue.put(target)
        elif target.state == "ready" or target.state == "running":
            pass
        elif target.state == "dead":
            print(f"[{timestamp()}] [System] WARNING: Message delivered to dead actor {target_id}")

    return (True, actor_id if is_dead else None)


def signal_processor(all_actors, work_queue, spawn_requests, pending_messages, from_subinterps_queue, next_actor_id, interp_pool):
    """Process signals from subinterpreters.

    Args:
        all_actors: Dict of all actors by ID
        work_queue: Queue to reschedule actors
        spawn_requests: Dict mapping request_id → actor_id
        pending_messages: Dict mapping request_id → list of pending messages
        from_subinterps_queue: Queue for receiving signals from subinterpreters
        next_actor_id: List with one element [next_id] for tracking actor IDs
        interp_pool: Queue of available interpreters for reuse
    """
    dead_actors_pending_cleanup = set()

    while True:
        try:
            subsignal = from_subinterps_queue.get_nowait()
        except interpreters.QueueEmpty:
            if dead_actors_pending_cleanup:
                print(f"[{timestamp()}] [System] Processing deferred cleanup for {len(dead_actors_pending_cleanup)} actors")
                for actor_id in dead_actors_pending_cleanup:
                    actor = all_actors.get(actor_id)
                    if actor:
                        try:
                            interp = actor.cleanup_namespace()
                            interp_pool.put(interp)
                            print(f"[{timestamp()}] [System] Cleaned up {actor} and returned to pool")
                        except Exception as e:
                            print(f"[{timestamp()}] [System] Error cleaning {actor} for reuse: {e}")
                            actor.destroy()
                dead_actors_pending_cleanup.clear()

            time.sleep(0.000001)
            continue

        should_continue, dead_actor_id = process_one_signal(
            subsignal, all_actors, work_queue, spawn_requests, pending_messages,
            from_subinterps_queue, next_actor_id, interp_pool
        )

        if not should_continue:
            break

        if dead_actor_id is not None:
            dead_actors_pending_cleanup.add(dead_actor_id)


def main(argv=None, timeout=None):
    """Run the actor system with the specified script.

    Args:
        argv: Command line arguments (defaults to sys.argv)
        timeout: Optional timeout in seconds. If set, raises TimeoutError if execution exceeds this.
    """
    if argv is None:
        argv = sys.argv

    if timeout is not None:
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Execution exceeded {timeout} seconds timeout")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

    if len(argv) < 2:
        print("Usage: python main.py <actor_script.pya>")
        print("\nDescription:")
        print("  Runs the Python actor system with the specified actor script.")
        print("\nArguments:")
        print("  actor_script.pya    Path to the initial actor script to execute")
        print("\nExample:")
        print("  python main.py actor_root_chain.pya")
        sys.exit(1)

    actor_script = argv[1]

    if not os.path.exists(actor_script):
        print(f"Error: Actor script '{actor_script}' not found.")
        sys.exit(1)

    run_id = str(uuid.uuid4())  # Unique ID for this run to isolate between test runs
    from_subinterps_queue = interpreters.create_queue()  # Queue for signals from subinterpreters
    next_actor_id = [0]  # Mutable list so signal_processor can increment it

    # Setup
    num_workers = os.cpu_count() or 1
    print(f"[{timestamp()}] Starting actor system with {num_workers} worker threads\n")

    # Create work queue and actor tracking
    # Use global interpreter pool for reuse across test runs
    work_queue = Queue()
    all_actors = {}
    spawn_requests = {}  # request_id → actor_id
    pending_messages = {}  # request_id → list of messages that arrived before actor was created

    # Start signal processor thread
    signal_thread = threading.Thread(
        target=signal_processor,
        args=(all_actors, work_queue, spawn_requests, pending_messages, from_subinterps_queue, next_actor_id, _global_interp_pool),
        daemon=False
    )
    signal_thread.start()

    # Create worker threads
    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker,
            args=(work_queue, i, all_actors, _global_interp_pool, spawn_requests, from_subinterps_queue, next_actor_id),
            daemon=False
        )
        t.start()
        threads.append(t)

    # Spawn the initial parent actor
    print(f"[{timestamp()}] [System] Spawning initial parent actor: {actor_script}\n")
    root_actor_id = next_actor_id[0]
    next_actor_id[0] += 1
    root_actor = Actor(actor_script, root_actor_id, run_id, from_subinterps_queue)
    all_actors[root_actor.id] = root_actor
    work_queue.put(root_actor)

    # Wait for all actors to finish
    print(f"[{timestamp()}] [System] Waiting for all actors to complete...")
    iterations = 0
    while True:
        time.sleep(0.001)  # Check every 1ms - CRITICAL: yield to other threads
        iterations += 1

        # Check if all actors are dead AND signal queue is empty (no pending spawns)
        all_dead = all(actor.state == "dead" for actor in all_actors.values())
        try:
            subsignal = from_subinterps_queue.get_nowait()
            # There's a signal in the queue - put it back and keep waiting
            from_subinterps_queue.put(subsignal)
            queue_empty = False
        except interpreters.QueueEmpty:
            queue_empty = True

        if all_dead and queue_empty:
            break

        # Debug: print non-dead actors every 200 iterations (2 seconds)
        if iterations % 200 == 0:
            non_dead = [(actor.id, actor.state) for actor in all_actors.values() if actor.state != "dead"]
            print(f"[{timestamp()}] [System] Still waiting... Non-dead actors: {non_dead}, queue_empty: {queue_empty}")

    print(f"[{timestamp()}] [System] All actors completed!")

    # Drain any remaining signals from the queue before shutdown
    print(f"[{timestamp()}] [System] Draining signal queue...")

    # Process any remaining signals
    while True:
        try:
            subsignal = from_subinterps_queue.get_nowait()
            # Process remaining PRINT signals
            if ":" in subsignal:
                parts = subsignal.split(":", 2)
                if len(parts) >= 2:
                    action = parts[1]
                    if action == "PRINT" and len(parts) > 2:
                        print_output = json.loads(parts[2]) if parts[2] else ""
                        print(print_output)
        except interpreters.QueueEmpty:
            break

    # Shutdown
    print(f"[{timestamp()}] [System] Shutting down threads...")

    # Stop signal processor
    from_subinterps_queue.put("SHUTDOWN")
    signal_thread.join()

    # Stop workers
    for _ in range(num_workers):
        work_queue.put(None)

    for t in threads:
        t.join()

    print(f"\n[{timestamp()}] [System] All workers completed! Total actors spawned: {len(all_actors)}")
    print(f"[{timestamp()}] [System] Interpreter pool size: {_global_interp_pool.qsize()}")

    # Now clean up all actors (destroy subinterpreters and queues)
    print(f"[{timestamp()}] [System] Cleaning up actors...")
    for actor in all_actors.values():
        actor.destroy()

    print(f"[{timestamp()}] [System] Cleanup complete!")

    # Cancel alarm if it was set
    if timeout is not None:
        signal.alarm(0)


if __name__ == "__main__":
    main()
