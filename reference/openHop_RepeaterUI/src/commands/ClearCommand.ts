import { BaseCommand, type CommandContext } from './BaseCommand';

export class ClearCommand extends BaseCommand {
  name = 'clear';
  description = 'Clear terminal screen';
  aliases = ['cls'];

  execute({ term, writePrompt }: CommandContext): void {
    term.clear();
    writePrompt();
  }
}
