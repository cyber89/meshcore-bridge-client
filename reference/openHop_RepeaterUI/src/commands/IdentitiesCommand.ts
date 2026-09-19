import { BaseCommand, type CommandContext } from './BaseCommand';
import ApiService from '@/utils/api';

interface IdentitiesResponse {
  registered?: any[];
  configured?: any[];
}

export class IdentitiesCommand extends BaseCommand {
  name = 'identities';
  description = 'List all identities';
  aliases = ['id', 'ids'];

  private isMobile(): boolean {
    return (
      /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
      window.innerWidth < 768
    );
  }

  async execute({ term, writePrompt }: CommandContext): Promise<void> {
    const stopLoading = this.startLoading(term, 'Fetching identities...');

    try {
      const response = await ApiService.getIdentities();
      stopLoading();

      // Handle nested data structure: data.registered and data.configured
      let identities: any[] = [];
      if (response.success && response.data) {
        const data = response.data as IdentitiesResponse;
        const registered = data.registered || [];
        const configured = data.configured || [];
        // Combine both registered and configured, but show configured as they have more details
        identities = configured.length > 0 ? configured : registered;
      } else if (Array.isArray(response)) {
        identities = response;
      }

      if (identities.length === 0) {
        this.writeInfo(term, 'No identities found');
      } else {
        this.writeSuccess(
          term,
          `Found \x1b[1m${identities.length}\x1b[0m identit${identities.length === 1 ? 'y' : 'ies'}`,
        );
        term.writeln('');

        if (this.isMobile()) {
          // Mobile: List format
          identities.forEach((id: any, idx: number) => {
            term.writeln(`\x1b[1;36m[${idx + 1}] ${id.name || 'Unnamed'}\x1b[0m`);
            term.writeln(`  \x1b[90mType:\x1b[0m ${id.type || '-'}`);
            term.writeln(`  \x1b[90mHash:\x1b[0m ${id.hash || '-'}`);
            term.writeln(`  \x1b[90mAddress:\x1b[0m ${id.address || '-'}`);
            term.writeln(
              `  \x1b[90mRegistered:\x1b[0m ${id.registered ? '\x1b[32myes\x1b[0m' : '\x1b[31mno\x1b[0m'}`,
            );
            if (idx < identities.length - 1) term.writeln('');
          });
        } else {
          // Desktop: Table format
          term.writeln(
            `\x1b[36m┌────┬─────────────────────────────┬───────────────┬──────┬─────────┬────────────┐\x1b[0m`,
          );
          term.writeln(
            `\x1b[36m│ #  │ Name                        │ Type          │ Hash │ Address │ Registered │\x1b[0m`,
          );
          term.writeln(
            `\x1b[36m├────┼─────────────────────────────┼───────────────┼──────┼─────────┼────────────┤\x1b[0m`,
          );

          identities.forEach((id: any, idx: number) => {
            const num = (idx + 1).toString().padEnd(2);
            const name = (id.name || 'Unnamed').padEnd(27);
            const type = (id.type || '-').padEnd(13);
            const hash = (id.hash || '-').padEnd(4);
            const address = (id.address || '-').padEnd(7);
            const registered = (id.registered ? 'yes' : 'no').padEnd(10);

            term.writeln(
              `\x1b[36m│\x1b[0m ${num} \x1b[36m│\x1b[0m \x1b[1m${name}\x1b[0m \x1b[36m│\x1b[0m ${type} \x1b[36m│\x1b[0m ${hash} \x1b[36m│\x1b[0m ${address} \x1b[36m│\x1b[0m ${registered} \x1b[36m│\x1b[0m`,
            );
          });

          term.writeln(
            `\x1b[36m└────┴─────────────────────────────┴───────────────┴──────┴─────────┴────────────┘\x1b[0m`,
          );
        }
      }
    } catch (error) {
      stopLoading();
      this.writeError(term, error instanceof Error ? error.message : 'Failed to fetch identities');
    }

    writePrompt();
  }
}
