"""Browser IPC temp paths stay outside source and are removed on every exit."""
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from sqe_studio.testing import process_temp


class ProcessWorkspaceTests(unittest.TestCase):
    def test_prefers_short_external_parent_for_a_long_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / ('long-checkout-' * 6) / 'source'
            root.mkdir(parents=True)
            short = base / 'short'
            short.mkdir()
            with process_temp.process_workspace(root, parents=(short, root.parent)) as work:
                self.assertEqual(work.parent, short)
                self.assertTrue(work.is_dir())
                self.assertFalse(work.is_relative_to(root))
            self.assertFalse(work.exists())

    def test_falls_back_when_preferred_parent_denies_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'source'
            root.mkdir()
            denied = base / 'denied'
            denied.mkdir()
            create = tempfile.TemporaryDirectory
            def attempt(*args, **kwargs):
                if kwargs['dir'] == denied:
                    raise PermissionError('simulated restricted host')
                return create(*args, **kwargs)
            with patch.object(process_temp.tempfile, 'TemporaryDirectory', side_effect=attempt):
                with process_temp.process_workspace(root, parents=(denied, root.parent)) as work:
                    self.assertEqual(work.parent, root.parent)
            self.assertFalse(work.exists())

    def test_never_selects_source_or_a_source_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'source'
            nested = root / 'reports'
            nested.mkdir(parents=True)
            with process_temp.process_workspace(root, parents=(root, nested, root.parent)) as work:
                self.assertEqual(work.parent, root.parent)
            self.assertEqual(list(nested.iterdir()), [])
            with self.assertRaisesRegex(OSError, 'outside source root'):
                with process_temp.process_workspace(root, parents=(root, nested)):
                    self.fail('Unsafe workspace was accepted')

    def test_cleans_workspace_when_child_operation_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'source'
            root.mkdir()
            with self.assertRaisesRegex(RuntimeError, 'child failed'):
                with process_temp.process_workspace(root, parents=(root.parent,)) as work:
                    (work / 'child-output').write_text('transient', encoding='utf-8')
                    raise RuntimeError('child failed')
            self.assertFalse(work.exists())

    @unittest.skipUnless(os.name == 'posix', 'Chromium Unix socket path limit is POSIX-specific')
    def test_default_workspace_allows_browser_style_unix_socket_for_long_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ('long-checkout-' * 8) / 'source'
            root.mkdir(parents=True)
            with process_temp.process_workspace(root) as work:
                profile = work / 'playwright_chromiumdev_profile-123456'
                profile.mkdir()
                with socket.socket(socket.AF_UNIX) as listener:
                    listener.bind(str(profile / 'SingletonSocket'))


if __name__ == '__main__':
    unittest.main()
