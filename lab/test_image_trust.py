import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock
from image_trust import images, verify


class ImageTrustTest(unittest.TestCase):
    def test_git_comparison_finds_nested_images_and_ignores_tag_only_changes(self):
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                def git(*args):
                    return subprocess.check_output(["git", "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", *args], text=True, stderr=subprocess.DEVNULL)
                git("init")
                path = Path("registry/engines/test.json")
                path.parent.mkdir(parents=True)
                digest = "a" * 64
                path.write_text('{"image":"ghcr.io/0xsero/gateway:old@sha256:' + digest + '"}')
                git("add", ".")
                git("commit", "-m", "base")
                base = git("rev-parse", "HEAD").strip()
                path.write_text('{"image":"ghcr.io/0xsero/gateway:new@sha256:' + digest +
                    '","nested":{"image":"ghcr.io/0xsero/exl3xpu@sha256:' + "b" * 64 + '"}}')
                git("add", ".")
                git("commit", "-m", "new image")
                self.assertEqual(images("HEAD") - images(base),
                    {"ghcr.io/0xsero/exl3xpu@sha256:" + "b" * 64})
                with self.assertRaises(subprocess.CalledProcessError):
                    images("missing-base")
            finally:
                os.chdir(old)

    def test_verification_binds_subject_publisher_workflow_and_branch(self):
        run = Mock()
        image = "ghcr.io/0xsero/gateway@sha256:" + "a" * 64
        verify(image, run)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["gh", "attestation", "verify", "oci://" + image,
            "--repo", "0xSero/local-ai-images", "--signer-workflow",
            "0xSero/local-ai-images/.github/workflows/release-image.yml",
            "--source-ref", "refs/heads/main", "--deny-self-hosted-runners"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 120)

    def test_unapproved_or_mutable_images_fail_before_network(self):
        for image in ["ghcr.io/0xsero/gateway:latest", "evil/gateway@sha256:" + "a" * 64]:
            with self.subTest(image=image), self.assertRaises(ValueError):
                verify(image, Mock(side_effect=AssertionError("network accessed")))

    def test_verification_failure_is_fatal(self):
        for error in [subprocess.CalledProcessError(1, "gh"), subprocess.TimeoutExpired("gh", 120)]:
            with self.subTest(error=error), self.assertRaises(type(error)):
                verify("ghcr.io/0xsero/gateway@sha256:" + "a" * 64, Mock(side_effect=error))


if __name__ == "__main__":
    unittest.main()
