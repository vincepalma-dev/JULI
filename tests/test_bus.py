import asyncio
import threading

from juli.bus import AgentMessage, MessageBus


def test_delivers_events_published_from_another_thread():
    bus = MessageBus()

    async def main():
        queue = bus.subscribe_async()
        worker = threading.Thread(target=lambda: bus.publish(AgentMessage("Coder", "from a thread")))
        worker.start()
        msg = await asyncio.wait_for(queue.get(), timeout=2)
        worker.join()
        return msg

    assert asyncio.run(main()).content == "from a thread"


def test_full_queue_drops_instead_of_raising():
    bus = MessageBus()

    async def main():
        queue = bus.subscribe_async()
        for i in range(queue.maxsize + 5):
            bus.publish(AgentMessage("Coder", str(i)))
        await asyncio.sleep(0.05)  # let the scheduled puts run
        return queue.qsize()

    assert asyncio.run(main()) == 1000


def test_closed_loop_subscriber_is_dropped():
    bus = MessageBus()

    async def main():
        bus.subscribe_async()

    asyncio.run(main())  # that loop is now closed
    bus.publish(AgentMessage("Coder", "still fine"))
    assert bus._async_queues == []


def test_persister_gets_non_status_messages_for_the_active_run():
    bus = MessageBus()
    saved = []
    bus.set_persister(lambda pid, rid, msg: saved.append((pid, rid, msg["content"])))
    bus.publish(AgentMessage("Coder", "no project yet"))
    bus.start_run("p1", 7)
    bus.publish(AgentMessage("Coder", "kept"))
    bus.set_task_status("complete")
    assert saved == [("p1", 7, "kept")]


def test_clear_history_is_in_memory_only():
    bus = MessageBus()
    saved = []
    bus.set_persister(lambda *a: saved.append(a))
    bus.start_run("p1", 1)
    bus.publish(AgentMessage("Coder", "x"))
    bus.clear_history()
    assert bus.history == [] and len(saved) == 1


def test_try_begin_task_is_exclusive():
    bus = MessageBus()
    results = []
    threads = [threading.Thread(target=lambda: results.append(bus.try_begin_task("t"))) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1


def test_activate_refused_while_another_project_runs():
    bus = MessageBus()
    assert bus.try_begin_task("t", "p1")
    assert bus.set_active_project("p1", []) is True
    assert bus.set_active_project("p2", []) is False
    assert bus.active_project_id == "p1"


def test_delete_is_atomic_with_task_start():
    bus = MessageBus()
    assert bus.try_begin_task("t", "p1")
    assert bus.delete_project("p1", lambda pid: True) is None  # running there
    assert bus.delete_project("p2", lambda pid: True) is True  # other project is fine


def test_deleting_the_active_project_deactivates_it():
    bus = MessageBus()
    bus.set_active_project("p1", [{"agent_name": "Coder", "content": "x"}])
    assert bus.delete_project("p1", lambda pid: True) is True
    assert bus.active_project_id is None and bus.history == []
