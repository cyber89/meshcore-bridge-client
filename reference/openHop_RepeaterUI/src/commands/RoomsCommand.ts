import { BaseCommand, type CommandContext } from './BaseCommand';
import ApiService from '@/utils/api';

interface RoomsResponse {
  rooms?: any[];
}

export class RoomsCommand extends BaseCommand {
  name = 'rooms';
  description = 'List room servers';

  private isMobile(): boolean {
    return (
      /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
      window.innerWidth < 768
    );
  }

  async execute({ term, writePrompt }: CommandContext): Promise<void> {
    const stopLoading = this.startLoading(term, 'Fetching room stats...');

    try {
      const response = await ApiService.getRoomStats();
      stopLoading();

      // Handle both wrapped response and direct data
      let rooms: any[] = [];
      if (response.success && response.data) {
        const data = response.data as RoomsResponse;
        // Check if rooms are nested in data.rooms or if data is the array
        rooms = data.rooms || (Array.isArray(response.data) ? response.data : []);
      } else if (Array.isArray(response)) {
        rooms = response;
      }

      if (rooms.length === 0) {
        this.writeInfo(term, 'No room servers found');
      } else {
        this.writeSuccess(
          term,
          `Found \x1b[1m${rooms.length}\x1b[0m room server${rooms.length === 1 ? '' : 's'}`,
        );
        term.writeln('');

        if (this.isMobile()) {
          // Mobile: List format
          rooms.forEach((room: any, idx: number) => {
            term.writeln(`\x1b[1;36m[${idx + 1}] ${room.room_name || 'Unnamed'}\x1b[0m`);
            term.writeln(`  \x1b[90mMessages:\x1b[0m ${room.total_messages || 0}`);
            term.writeln(`  \x1b[90mTotal Clients:\x1b[0m ${room.total_clients || 0}`);
            term.writeln(`  \x1b[90mActive Clients:\x1b[0m ${room.active_clients || 0}`);
            term.writeln(
              `  \x1b[90mSync:\x1b[0m ${room.sync_running ? '\x1b[32mrunning\x1b[0m' : '\x1b[31mstopped\x1b[0m'}`,
            );
            if (idx < rooms.length - 1) term.writeln('');
          });
        } else {
          // Desktop: Table format
          term.writeln(
            `\x1b[36m┌────┬─────────────────────────────┬──────────┬──────────────┬────────────────┬──────────┐\x1b[0m`,
          );
          term.writeln(
            `\x1b[36m│ #  │ Room Name                   │ Messages │ Total Clients│ Active Clients │ Sync     │\x1b[0m`,
          );
          term.writeln(
            `\x1b[36m├────┼─────────────────────────────┼──────────┼──────────────┼────────────────┼──────────┤\x1b[0m`,
          );

          rooms.forEach((room: any, idx: number) => {
            const num = (idx + 1).toString().padEnd(2);
            const name = (room.room_name || 'Unnamed').padEnd(27);
            const messages = (room.total_messages?.toString() || '0').padEnd(8);
            const totalClients = (room.total_clients?.toString() || '0').padEnd(12);
            const activeClients = (room.active_clients?.toString() || '0').padEnd(14);
            const sync = (room.sync_running ? 'running' : 'stopped').padEnd(8);

            term.writeln(
              `\x1b[36m│\x1b[0m ${num} \x1b[36m│\x1b[0m \x1b[1m${name}\x1b[0m \x1b[36m│\x1b[0m ${messages} \x1b[36m│\x1b[0m ${totalClients} \x1b[36m│\x1b[0m ${activeClients} \x1b[36m│\x1b[0m ${sync} \x1b[36m│\x1b[0m`,
            );
          });

          term.writeln(
            `\x1b[36m└────┴─────────────────────────────┴──────────┴──────────────┴────────────────┴──────────┘\x1b[0m`,
          );
        }
      }
    } catch (error) {
      stopLoading();
      this.writeError(term, error instanceof Error ? error.message : 'Failed to fetch room stats');
    }

    writePrompt();
  }
}
