import { BaseCommand, type CommandContext } from './BaseCommand';
import ApiService from '@/utils/api';

export class AdvertCommand extends BaseCommand {
  name = 'advert';
  description = 'Send neighbor advert immediately';

  async execute({ term, writePrompt }: CommandContext): Promise<void> {
    const stopLoading = this.startLoading(term, 'Sending advert...');

    try {
      // Use longer timeout for advert sending (matches system store implementation)
      const response = await ApiService.post<string>(
        '/send_advert',
        {},
        {
          timeout: 10000, // 10 seconds instead of default 5
        },
      );
      stopLoading();

      if (response.success) {
        this.writeSuccess(term, response.data || 'Advert sent successfully');
      } else {
        this.writeError(term, response.error || 'Failed to send advert');
      }
    } catch (error) {
      stopLoading();
      this.writeError(term, `Failed to send advert: ${error}`);
    }

    writePrompt();
  }
}
