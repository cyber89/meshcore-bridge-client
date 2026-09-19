import { BaseCommand, type CommandContext } from './BaseCommand';
import ApiService from '@/utils/api';

export class AclCommand extends BaseCommand {
  name = 'acl';
  description = 'Show ACL statistics';

  async execute({ term, writePrompt }: CommandContext): Promise<void> {
    const stopLoading = this.startLoading(term, 'Fetching ACL stats...');

    try {
      const response = await ApiService.getACLStats();
      stopLoading();

      // Handle both wrapped response and direct data
      const data = response.success && response.data ? response.data : response;

      if (data && typeof data === 'object') {
        this.writeSuccess(term, 'ACL Statistics:');
        term.writeln('');

        const formatValue = (value: any, indent: string = '  '): void => {
          if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            for (const [subKey, subValue] of Object.entries(value)) {
              if (typeof subValue === 'object' && subValue !== null) {
                term.writeln(`${indent}\x1b[90m${subKey}:\x1b[0m`);
                formatValue(subValue, indent + '  ');
              } else {
                term.writeln(`${indent}\x1b[90m${subKey.padEnd(18)}\x1b[0m ${subValue}`);
              }
            }
          } else {
            term.writeln(`${indent}${value}`);
          }
        };

        for (const [key, value] of Object.entries(data)) {
          if (typeof value === 'object' && value !== null) {
            term.writeln(`  \x1b[36m${key}\x1b[0m`);
            formatValue(value, '    ');
          } else {
            term.writeln(`  \x1b[36m${key.padEnd(20)}\x1b[0m ${value}`);
          }
        }
      } else {
        this.writeError(term, 'No ACL data available');
      }
    } catch (error) {
      stopLoading();
      this.writeError(term, error instanceof Error ? error.message : 'Failed to fetch ACL stats');
    }

    writePrompt();
  }
}
