import unittest

from export_plugin import exportable


class ExportFlagsTest(unittest.TestCase):
    def test_device_flag_launches_export(self):
        self.assertTrue(exportable({}))
        self.assertTrue(exportable({"flags": []}))
        self.assertTrue(exportable({"flags": ["--device /dev/kfd"]}))
        self.assertTrue(exportable({"flags": ["--device /dev/kfd", "--device /dev/dri"]}))

    def test_privileged_flag_launches_stay_out(self):
        for flag in ("--ipc host", "--security-opt seccomp=unconfined", "--ulimit memlock=-1:-1",
                     "--privileged", "--pid host", "--cap-add SYS_ADMIN", "--device /dev/mem"):
            self.assertFalse(exportable({"flags": ["--device /dev/kfd", flag]}), flag)

    def test_host_programs_and_multi_machine_stay_out(self):
        self.assertFalse(exportable({"kind": "host"}))
        self.assertFalse(exportable({"machines": 2}))
        self.assertFalse(exportable({"build": "x"}))


if __name__ == "__main__":
    unittest.main()
