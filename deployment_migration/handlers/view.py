import json
from dataclasses import dataclass
from typing import Callable, MutableMapping, Self, Optional, Iterator

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt


@dataclass
class Terminal:
    """ "Handles Input and Output from the terminal"""

    console: Console = Console()

    def ask(
        self,
        question: str,
        default: str | None = None,
        choices: list[str] | None = None,
    ) -> str:
        """Asks the user for input"""
        question_string = f"[bold]{question}[/bold]"

        response = None
        while not response:
            response = Prompt.ask(question_string, default=default)

        return response

    def hint(self, hint: str) -> None:
        """Gives the user a hint"""
        hint_string = f"[italic][blue]Hint:[/blue] {hint}[/italic]"
        self.console.print(hint_string)

    def heading_and_info(self, heading: str, info: str) -> None:
        """Gives the user a heading"""
        self.console.print(Panel(f"[bold]{heading}[/bold]"))
        self.console.print(info)

    def update(self, text: str) -> None:
        """Update the user about the current status"""
        self.console.print(f"[blue]{text}[/blue]")

    def warn(self, short: str, long: str) -> None:
        """Warn the user about something"""
        self.console.print(f"[yellow][bold]Warning:[/bold] {short}[/yellow]\n{long}")

    def error(self, text: str) -> None:
        """Error out the user"""
        self.console.print(f"[red][bold]Error:[/bold] {text}[/red]")

    def hr_line(self):
        self.console.print(Markdown("---"))


class QueryCache(MutableMapping[str, str]):
    """Caches the queries"""

    CACHE_FILE = ".vydev-cli-cache.json"

    def __init__(self: Self):
        self._config = self._load_config()

    def _load_config(self) -> dict[str, str]:
        try:
            with open(self.CACHE_FILE, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {}

        return config

    def _save_config(self, config: dict[str, str]) -> None:
        with open(self.CACHE_FILE, "w") as f:
            json.dump(self._config, f)

    def __setitem__(self, key: str, value: str, /) -> None:
        self._config[key] = value

        self._save_config(self._config)

    def __delitem__(self, key: str, /) -> None:
        del self._config[key]

        self._save_config(self._config)

    def __getitem__(self, key: str, /) -> str:
        return self._config[key]

    def __len__(self) -> int:
        raise NotImplementedError("Will not be implemented")

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError("Will not be implemented")


class Queryier:
    """Grabs relevant information needed for the migration"""

    def __init__(self: Self, terminal: Terminal):
        self.terminal = terminal
        self.config = QueryCache()

    def ask_user_with_default_and_hint(
        self: Self,
        question: str,
        default_query: Callable[[], str | None],
        return_default: bool = False,
        hint: Optional[str] = None,
        choices: Optional[list[str]] = None,
    ) -> str:
        from_cache = self.config.get(question, None)
        if from_cache:
            return from_cache

        try:
            default = default_query()
        except Exception:
            default = None

        if return_default and default is not None:
            return default

        self.terminal.hr_line()

        if hint:
            self.terminal.hint(hint)
        response = self.terminal.ask(question, default=default, choices=choices)

        self.config[question] = response

        return response
