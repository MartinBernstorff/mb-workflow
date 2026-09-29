from typing import override

from typer.core import TyperGroup


class AlphabeticalGroup(TyperGroup):
    @override
    def list_commands(self, ctx: object) -> list[str]:
        return sorted(self.commands)
