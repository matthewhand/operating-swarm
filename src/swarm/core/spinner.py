"""
Terminal spinners for interactive feedback during long operations.

This module is the single source of truth for spinner implementations:
- ``Spinner``: plain stdlib spinner for generic terminal feedback.
- ``SwarmSpinner``: Rich-console spinner used by blueprint CLIs.
"""

import sys
import threading
import time


class Spinner:
    """Simple terminal spinner for interactive feedback."""
    # Define spinner characters (can be customized)
    SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    # Custom status sequences for special cases
    STATUS_SEQUENCES = {
        'generating': ['Generating.', 'Generating..', 'Generating...'],
        'running': ['Running...']
    }

    def __init__(self, interactive: bool, custom_sequence: str = None):
        """
        Initialize the spinner.

        Args:
            interactive (bool): Hint whether the environment is interactive.
                                Spinner is disabled if False or if output is not a TTY.
            custom_sequence (str): Optional name for a custom status sequence (e.g., 'generating', 'running').
        """
        self.interactive = interactive
        self.is_tty = sys.stdout.isatty()
        self.enabled = self.interactive and self.is_tty
        self.running = False
        self.thread: threading.Thread | None = None
        self.status = ""
        self.index = 0
        self.custom_sequence = custom_sequence
        self.sequence_idx = 0

    def start(self, status: str = "Processing..."):
        """Start the spinner with an optional status message."""
        if not self.enabled or self.running:
            return # Do nothing if disabled or already running
        self.status = status
        self.running = True
        self.sequence_idx = 0
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the spinner and clear the line."""
        if not self.enabled or not self.running:
            return # Do nothing if disabled or not running
        self.running = False
        if self.thread is not None:
            self.thread.join() # Wait for the thread to finish
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        self.thread = None

    def _spin(self):
        """Internal method running in the spinner thread to animate."""
        start_time = time.time()
        warned = False
        while self.running:
            elapsed = time.time() - start_time
            if self.custom_sequence and self.custom_sequence in self.STATUS_SEQUENCES:
                seq = self.STATUS_SEQUENCES[self.custom_sequence]
                # If taking longer than 10s, show special message
                if elapsed > 10 and not warned:
                    msg = f"{seq[-1]} Taking longer than expected"
                    warned = True
                else:
                    msg = seq[self.sequence_idx % len(seq)]
                sys.stdout.write(f"\r{msg}\033[K")
                sys.stdout.flush()
                self.sequence_idx += 1
            else:
                char = self.SPINNER_CHARS[self.index % len(self.SPINNER_CHARS)]
                sys.stdout.write(f"\r{char} {self.status}\033[K")
                sys.stdout.flush()
                self.index += 1
            time.sleep(0.4 if self.custom_sequence else 0.1)

class SwarmSpinner:
    """Spinner for CLI blueprints, producing standard frames (Rich console)."""
    FRAMES = ["Generating.", "Generating..", "Generating...", "Running..."]
    SLOW_FRAME = "Generating... Taking longer than expected"
    INTERVAL = 0.12
    SLOW_THRESHOLD = 10  # seconds

    def __init__(self, console):
        from rich.style import Style
        from rich.text import Text
        self._Style = Style
        self._Text = Text
        self.console = console
        self._stop_event = threading.Event()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin)
        self._thread.daemon = True
        self._thread.start()

    def _spin(self):
        idx = 0
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start_time
            if elapsed > self.SLOW_THRESHOLD:
                txt = self._Text(self.SLOW_FRAME, style=self._Style(color="yellow", bold=True))
            else:
                frame = self.FRAMES[idx % len(self.FRAMES)]
                txt = self._Text(frame, style=self._Style(color="cyan", bold=True))
            self.console.print(txt, end="\r", soft_wrap=True, highlight=False)
            time.sleep(self.INTERVAL)
            idx += 1
        # Clear line on stop
        self.console.print(" " * 40, end="\r")

    def stop(self):
        self._stop_event.set()
        self._thread.join()


class CodeySpinner:
    """Frame-based spinner state machine used by codey blueprint and CLI tests."""

    SPINNER_STATES = ["Generating.", "Generating..", "Generating...", "Running..."]
    LONG_WAIT_MSG = "Generating... Taking longer than expected"

    def __init__(self):
        self._idx = 0
        self._start_time = None
        self._last_frame = self.SPINNER_STATES[0]

    def start(self):
        self._idx = 0
        self._last_frame = self.SPINNER_STATES[0]
        self._start_time = time.time()

    def _spin(self):
        self._idx = (self._idx + 1) % len(self.SPINNER_STATES)
        self._last_frame = self.SPINNER_STATES[self._idx]

    def current_spinner_state(self):
        if self._start_time and (time.time() - self._start_time) > 10:
            return self.LONG_WAIT_MSG
        return self._last_frame


# Example usage (if run directly)
if __name__ == "__main__":
    print("Starting spinner test...")
    s = Spinner(interactive=True) # Assume interactive for testing
    s.start("Doing something cool")
    try:
        time.sleep(5) # Simulate work
        s.stop()
        print("Spinner stopped.")
        s.start("Doing another thing")
        time.sleep(3)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        s.stop() # Ensure spinner stops on exit/error
        print("Test finished.")
