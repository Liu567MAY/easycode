"""控制台输入输出：主线程与后台线程共用一个 stdin。"""

import threading

from agent import config

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False


class ConsoleBroker:
    """Serialize normal prompts and worker permission questions on one stdin."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reader = None

    def ask(self, prompt: str) -> str:
        with self._lock:
            return (self.reader or input)(prompt)


CONSOLE = ConsoleBroker()


def terminal_print(text: str):
    if threading.current_thread() is threading.main_thread() or not config.CLI_ACTIVE:
        print(text)
        return
    line = ""
    if READLINE_AVAILABLE:
        try:
            line = readline.get_line_buffer()
        except Exception:
            line = ""
    print(f"\r\033[K{text}")
    print(config.PROMPT + line, end="", flush=True)