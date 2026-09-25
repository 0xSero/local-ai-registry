"""Watchdog regression checks; every process inspection and signal is mocked."""

import importlib.util
from pathlib import Path
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch


path = Path(__file__).resolve().parents[1] / "sources/qwen38-apple-silicon/monitor_memory.py"
spec = importlib.util.spec_from_file_location("qwen_memory_monitor", path)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def process(**changes):
    return {
        "pid": 42, "uid": 501, "state": "S", "started": "Fri Sep 25 14:00:00 2026",
        "rss_kib": 1024, "rss_bytes": 1048576,
        "command": "runs/qwen38/venv/bin/python registry/asset/qwen38-mlx-vlm-serve.py --port 8766",
        **changes,
    }


class MemoryParsersTests(unittest.TestCase):
    def test_ps_preserves_start_time_and_complete_arguments(self):
        row = "42 501 S Fri Sep 25 14:00:00 2026 1024 " + process()["command"]
        self.assertEqual(monitor.parse_process(row), process())
        for invalid in ("", "42 501 S missing fields", row.replace("1024", "-1", 1)):
            with self.subTest(row=invalid), self.assertRaises(ValueError):
                monitor.parse_process(invalid)

    def test_swap_units_and_vm_stat_counters(self):
        swap = monitor.parse_swapusage("vm.swapusage: total = 16.00G used = 1536.25M free = 1.00G (encrypted)")
        self.assertEqual(swap["total_bytes"], 16 * 1024**3)
        self.assertEqual(swap["used_bytes"], int(1536.25 * monitor.MIB))
        self.assertEqual(monitor.parse_swapusage("used = 1024 KiB")["used_bytes"], monitor.MIB)
        vm = monitor.parse_vm_stat(
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free: 123.\nSwapouts: 567.\n"
        )
        self.assertEqual(vm, {"page_size_bytes": 16384, "counters": {"Pages free": 123, "Swapouts": 567}})
        for invalid in ("used = nanM", "used = -1.00M", "no swap stats"):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                monitor.parse_swapusage(invalid)

    def test_exited_or_zombie_process_is_done_but_inspection_failure_is_not(self):
        row = "42 501 Z Fri Sep 25 14:00:00 2026 1024 " + process()["command"]
        for result in (SimpleNamespace(returncode=1, stdout="", stderr=""),
                       SimpleNamespace(returncode=0, stdout=row, stderr="")):
            with self.subTest(result=result), patch.object(monitor, "command", return_value=result):
                self.assertIsNone(monitor.read_process(42))
        with patch.object(monitor, "command", return_value=SimpleNamespace(returncode=2, stdout="", stderr="ps failed")):
            with self.assertRaisesRegex(RuntimeError, "could not inspect"):
                monitor.read_process(42)


class ProcessIdentityTests(unittest.TestCase):
    def test_pid_owner_start_time_and_command_must_match(self):
        original = process()
        with patch.object(monitor.os, "geteuid", return_value=501):
            self.assertEqual(monitor.guard_process(original, 42), original)
            for field, value in (("pid", 43), ("uid", 502), ("started", "Fri Sep 25 14:01:00 2026"),
                                 ("command", original["command"] + " --max-tokens 64")):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    monitor.guard_process({**original, field: value}, 42, original)

    def test_marker_in_unrelated_command_or_python_c_is_not_a_wrapper_process(self):
        for command in ("sleep 100 registry/asset/qwen38-mlx-vlm-serve.py",
                        "python -c registry/asset/qwen38-mlx-vlm-serve.py",
                        "python -m registry/asset/qwen38-mlx-vlm-serve.py",
                        "sh -c 'python registry/asset/qwen38-mlx-vlm-serve.py'",
                        "python other.py --label registry/asset/qwen38-mlx-vlm-serve.py"):
            with self.subTest(command=command), patch.object(monitor.os, "geteuid", return_value=501):
                with self.assertRaisesRegex(ValueError, "do not identify"):
                    monitor.guard_process(process(command=command), 42)
        command = "/usr/bin/python3 -B -u /checkout/registry/asset/qwen38-mlx-vlm-serve.py --port 8766"
        with patch.object(monitor.os, "geteuid", return_value=501):
            self.assertEqual(monitor.guard_process(process(command=command), 42)["pid"], 42)

    def test_saved_process_metadata_omits_arguments(self):
        public = monitor.public_process(process())
        self.assertNotIn("command", public)
        self.assertEqual(public["wrapper"], monitor.WRAPPER)
        self.assertEqual(len(public["command_sha256"]), 64)
        self.assertEqual(public["rss_bytes"], 1048576)


class TerminationTests(unittest.TestCase):
    def test_term_then_kill_rechecks_identity_before_each_signal(self):
        original, events = process(), []
        with patch.object(monitor.os, "geteuid", return_value=501), \
                patch.object(monitor, "read_process", side_effect=[original, original, original, None]) as read, \
                patch.object(monitor.os, "kill") as kill, \
                patch.object(monitor.time, "monotonic", side_effect=[0, 11, 12]), \
                patch.object(monitor.time, "sleep"):
            monitor.terminate_target(42, original, lambda event, **data: events.append((event, data)))
        self.assertEqual(kill.call_args_list, [call(42, signal.SIGTERM), call(42, signal.SIGKILL)])
        self.assertEqual(read.call_count, 4)
        self.assertEqual([data["signal"] for event, data in events if event == "signal_sent"], ["SIGTERM", "SIGKILL"])
        self.assertEqual(events[-1][0], "server_exited")

    def test_graceful_exit_never_escalates(self):
        original = process()
        with patch.object(monitor.os, "geteuid", return_value=501), \
                patch.object(monitor, "read_process", side_effect=[original, None]), \
                patch.object(monitor.os, "kill") as kill, \
                patch.object(monitor.time, "monotonic", return_value=0):
            monitor.terminate_target(42, original, lambda *args, **kwargs: None)
        kill.assert_called_once_with(42, signal.SIGTERM)

    def test_pid_reused_immediately_before_escalation_is_never_killed(self):
        original = process()
        replacement = process(started="Fri Sep 25 14:01:00 2026")
        with patch.object(monitor.os, "geteuid", return_value=501), \
                patch.object(monitor, "read_process", side_effect=[original, original, replacement]), \
                patch.object(monitor.os, "kill") as kill, \
                patch.object(monitor.time, "monotonic", side_effect=[0, 11]), \
                patch.object(monitor.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                monitor.terminate_target(42, original, lambda *args, **kwargs: None)
        kill.assert_called_once_with(42, signal.SIGTERM)

    def test_exited_target_or_identity_change_before_first_signal_sends_nothing(self):
        original = process()
        with patch.object(monitor, "read_process", return_value=None), patch.object(monitor.os, "kill") as kill:
            self.assertFalse(monitor.signal_target(42, original, signal.SIGTERM, lambda *args, **kwargs: None))
        kill.assert_not_called()
        with patch.object(monitor.os, "geteuid", return_value=501), \
                patch.object(monitor, "read_process", return_value=process(uid=502)), \
                patch.object(monitor.os, "kill") as kill:
            with self.assertRaises(ValueError):
                monitor.signal_target(42, original, signal.SIGTERM, lambda *args, **kwargs: None)
        kill.assert_not_called()

    def test_exit_between_guard_and_signal_is_recorded(self):
        events = []
        with patch.object(monitor.os, "geteuid", return_value=501), \
                patch.object(monitor, "read_process", return_value=process()), \
                patch.object(monitor.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(monitor.signal_target(42, process(), signal.SIGTERM,
                                                   lambda event, **data: events.append(event)))
        self.assertEqual(events, ["server_exited"])


class SwapGrowthTests(unittest.TestCase):
    def test_termination_requires_growth_strictly_above_baseline_threshold(self):
        baseline, events = 2 * monitor.MIB, []
        observations = [{"swap": {"used_bytes": baseline}},
                        {"swap": {"used_bytes": baseline + 8192 * monitor.MIB}},
                        {"swap": {"used_bytes": baseline + 8193 * monitor.MIB}}]
        with patch.object(monitor, "checked_process", return_value=process()), \
                patch.object(monitor, "memory_observation", side_effect=observations), \
                patch.object(monitor.time, "sleep"), patch.object(monitor, "terminate_target") as terminate:
            code = monitor.monitor(SimpleNamespace(pid=42, max_swap_growth_mib=8192, interval=10),
                                   lambda event, **data: events.append((event, data)))
        self.assertEqual(code, 0)
        terminate.assert_called_once()
        self.assertEqual(len([event for event, _ in events if event == "sample"]), 2)
        self.assertEqual(events[-1][0], "swap_threshold_exceeded")
        self.assertEqual(events[-1][1]["baseline_swap_bytes"], baseline)

    def test_decreasing_swap_does_not_signal_and_server_exit_ends_monitoring(self):
        events = []
        with patch.object(monitor, "checked_process", side_effect=[process(), process(), None]), \
                patch.object(monitor, "memory_observation", side_effect=[{"swap": {"used_bytes": 2 * monitor.MIB}},
                                                                        {"swap": {"used_bytes": monitor.MIB}}]), \
                patch.object(monitor.time, "sleep"), patch.object(monitor, "terminate_target") as terminate:
            code = monitor.monitor(SimpleNamespace(pid=42, max_swap_growth_mib=8192, interval=10),
                                   lambda event, **data: events.append((event, data)))
        self.assertEqual(code, 0)
        terminate.assert_not_called()
        self.assertEqual(next(data["swap_growth_bytes"] for event, data in events if event == "sample"), -monitor.MIB)
        self.assertEqual(events[-1][0], "server_exited")


if __name__ == "__main__":
    unittest.main()
