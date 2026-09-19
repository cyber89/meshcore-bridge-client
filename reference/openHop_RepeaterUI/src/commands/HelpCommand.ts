import { BaseCommand, type CommandContext } from './BaseCommand';

export class HelpCommand extends BaseCommand {
  name = 'help';
  description = 'Show available commands';
  aliases = ['?', 'h'];

  constructor(private commands: BaseCommand[]) {
    super();
  }

  execute({ term, writePrompt }: CommandContext): void {
    term.writeln('');
    term.writeln('\x1b[1;33mAvailable Commands:\x1b[0m');
    term.writeln('');

    this.commands.forEach((cmd) => {
      const aliases = cmd.aliases?.length ? ` (${cmd.aliases.join(', ')})` : '';
      term.writeln(`  \x1b[1;36m${cmd.name.padEnd(15)}\x1b[0m ${cmd.description}${aliases}`);
    });

    term.writeln('');
    term.writeln('\x1b[90mTip: Use Tab for autocomplete, ↑↓ for history, Ctrl+F to search\x1b[0m');
    writePrompt();
  }
}
