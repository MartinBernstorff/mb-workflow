from typing import TYPE_CHECKING, override

from typer.core import TyperGroup

if TYPE_CHECKING:
    from typer._click import Command, Context


class AlphabeticalGroup(TyperGroup):
    @override
    def list_commands(self, ctx: object) -> list[str]:
        return sorted(self.commands)

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None and any(param.required for param in command.params):
            command.no_args_is_help = True
        return command
