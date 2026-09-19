import { BaseCommand, type CommandContext } from './BaseCommand';
import ApiService from '@/utils/api';

export class KeysCommand extends BaseCommand {
  name = 'keys';
  description = 'List transport keys';

  async execute({ term, writePrompt }: CommandContext): Promise<void> {
    const stopLoading = this.startLoading(term, 'Fetching transport keys...');

    try {
      const response = await ApiService.getTransportKeys();
      stopLoading();

      // Handle both wrapped response and direct array
      const data = response.success && response.data ? response.data : response;
      const keys = Array.isArray(data) ? data : [];

      if (keys.length === 0) {
        this.writeInfo(term, 'No transport keys found');
      } else {
        this.writeSuccess(
          term,
          `Found \x1b[1m${keys.length}\x1b[0m transport key${keys.length === 1 ? '' : 's'}`,
        );
        term.writeln('');
        keys.forEach((key: any, idx: number) => {
          term.writeln(
            `\x1b[36m${(idx + 1).toString().padStart(2)}.\x1b[0m \x1b[1m${key.name || 'Unnamed'}\x1b[0m`,
          );
          if (key.flood_policy) term.writeln(`    Policy: \x1b[90m${key.flood_policy}\x1b[0m`);
          if (key.parent_id) term.writeln(`    Parent: \x1b[90m${key.parent_id}\x1b[0m`);
          if (idx < keys.length - 1) term.writeln('');
        });
      }
    } catch (error) {
      stopLoading();
      this.writeError(
        term,
        error instanceof Error ? error.message : 'Failed to fetch transport keys',
      );
    }

    writePrompt();
  }
}
