import io
import unittest

from api_logging import _TeeStream


class TestTeeStream(unittest.TestCase):
    def test_write_and_flush_forward_to_console_and_log_file(self):
        console = io.StringIO()
        log_file = io.StringIO()
        stream = _TeeStream(console, log_file, terminal_enabled=True)

        self.assertEqual(stream.write("app started\n"), len("app started\n"))
        stream.flush()

        self.assertEqual(console.getvalue(), "app started\n")
        self.assertEqual(log_file.getvalue(), "app started\n")

    def test_write_and_flush_suppress_console_but_keep_file_logging(self):
        console = io.StringIO()
        log_file = io.StringIO()
        stream = _TeeStream(console, log_file, terminal_enabled=False)

        self.assertEqual(stream.write("app started\n"), len("app started\n"))
        stream.flush()

        self.assertEqual(console.getvalue(), "")
        self.assertEqual(log_file.getvalue(), "app started\n")


if __name__ == "__main__":
    unittest.main()
