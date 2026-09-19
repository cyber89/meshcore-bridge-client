import type { Terminal } from '@xterm/xterm';

export interface CommandContext {
  term: Terminal;
  args: string[];
  writePrompt: () => void;
}

export interface CommandResult {
  success: boolean;
  message?: string;
}

export abstract class BaseCommand {
  abstract name: string;
  abstract description: string;
  aliases?: string[];
  usage?: string;

  abstract execute(context: CommandContext): Promise<void> | void;

  matches(input: string): boolean {
    const lower = input.toLowerCase();
    return (
      lower === this.name.toLowerCase() ||
      (this.aliases?.some((alias) => lower === alias.toLowerCase()) ?? false)
    );
  }

  protected writeLine(term: Terminal, message: string, color?: string): void {
    if (color) {
      term.writeln(`${color}${message}\x1b[0m`);
    } else {
      term.writeln(message);
    }
  }

  protected writeSuccess(term: Terminal, message: string): void {
    term.writeln(`\x1b[1;32m✓\x1b[0m ${message}`);
  }

  protected writeError(term: Terminal, message: string): void {
    term.writeln(`\x1b[1;31m✗ Error:\x1b[0m ${message}`);
  }

  protected writeInfo(term: Terminal, message: string): void {
    term.writeln(`\x1b[90m${message}\x1b[0m`);
  }

  protected startLoading(term: Terminal, message: string): () => void {
    const frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
    let i = 0;
    let isLoading = true;

    const interval = setInterval(() => {
      if (!isLoading) {
        clearInterval(interval);
        return;
      }
      term.write(`\r\x1b[36m${frames[i]}\x1b[0m ${message}`);
      i = (i + 1) % frames.length;
    }, 80);

    return () => {
      isLoading = false;
      clearInterval(interval);
      term.write('\r\x1b[K');
    };
  }
}
