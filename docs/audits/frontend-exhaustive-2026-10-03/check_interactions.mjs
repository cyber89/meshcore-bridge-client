// Isolated behavioral checks: no network, storage, bridge, browser, or radio.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
const root = process.cwd();
const baseline = process.argv.includes('--baseline');
const baselineRevision = process.argv.find(arg => arg.startsWith('--revision='))?.slice('--revision='.length) || '942ccd80b6d8af1d9c22cb9eef91c2cd75aa5702';
const read = file => baseline ? execFileSync('git', ['show', `${baselineRevision}:src/web/static/js/${file}`], { encoding: 'utf8' }) : fs.readFileSync(path.join(root, 'src/web/static/js', file), 'utf8');
const dataUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const utilsUrl = dataUrl(read('core/utils.js'));
const eventsUrl = dataUrl(read('core/eventbus.js'));
const { SnifferModule } = await import(dataUrl(read('modules/sniffer.js')
  .replace('../core/utils.js', utilsUrl).replace('../core/eventbus.js', eventsUrl)));
class Element {
  constructor(id = '') { this.id = id; this.listeners = new Map(); this.value = ''; this.innerHTML = ''; this.textContent = ''; this.disabled = false;
    this.attrs = new Map(); this.classes = new Set(); this.isConnected = true; this.offsetParent = {}; this.children = [];
    this.classList = { add: (...xs) => xs.forEach(x => this.classes.add(x)), remove: (...xs) => xs.forEach(x => this.classes.delete(x)), contains: x => this.classes.has(x), toggle: (x, on) => on ? this.classes.add(x) : this.classes.delete(x) };
  }
  setAttribute(k, v) { this.attrs.set(k, v); }
  removeAttribute(k) { this.attrs.delete(k); }
  addEventListener(k, fn) { if (!this.listeners.has(k)) this.listeners.set(k, new Set()); this.listeners.get(k).add(fn); }
  removeEventListener(k, fn) { this.listeners.get(k)?.delete(fn); }
  fire(k, ev = {}) { for (const fn of [...this.listeners.get(k) || []]) fn(ev); }
  focus() { document.activeElement = this; }
  select() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getClientRects() { return [{}]; }
  click() { this.fire('click', { target: this, preventDefault() {} }); }
}
const elements = new Map();
globalThis.document = new Element('document');
document.getElementById = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
document.createElement = () => new Element();
document.activeElement = new Element('outside');
globalThis.window = { I18n: {} };
globalThis.I18n = { t: key => key, setText: (el, key) => { el.textContent = key; } };
const warnings = [];
console.warn = (message, error) => warnings.push({ message, error: error?.message });
const result = {};
const notices = [];
const module = new SnifferModule({ showToast: (...args) => notices.push(args) });
module.renderFilteredLogs = () => {};
module.systemLogs = [{ level: 'INFO', source: 'bridge.audit', message: 'sentinel' }];
globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ status: 'error', detail: 'Forbidden' }) });
await module.clearSystemLogs();
result.clear_failure_preserves_logs = module.systemLogs.length === 1;
module.dom.chkDebugMode = new Element();
module.dom.chkDebugMode.checked = true;
await module.setDebugMode(true);
result.debug_failure_restores_state = !module.isDebugMode && module.dom.chkDebugMode.checked === false;
module.dom.logSearchInput = { value: 'bridge.audit' };
result.log_source_searchable = module.matchesLogFilter({ level: 'INFO', source: 'bridge.audit', message: 'sentinel' });
result.log_source_visible = module.createLogElement({ level: 'INFO', source: 'bridge.audit', message: 'sentinel' }).innerHTML.includes('bridge.audit');
module.dom.logSearchInput.value = '';
module.dom.logLevelFilter = { value: 'WARNING' };
result.warning_alias_style = module.createLogElement({ level: 'WARN', message: 'sentinel' }).innerHTML.includes('badge-lvl-warning');
result.case_insensitive_level = module.matchesLogFilter({ level: 'warning', message: 'sentinel' });
result.iso_time_compact = module.createLogElement({ level: 'INFO', iso_time: '2026-10-03T10:22:33.123', message: 'sentinel' }).innerHTML.includes('>10:22:33</span>');
const beforeNotices = notices.length;
let createdDownload = false;
globalThis.URL.createObjectURL = () => { createdDownload = true; return 'blob:fixture'; };
globalThis.URL.revokeObjectURL = () => {};
document.body = { appendChild() {}, removeChild() {} };
await module.downloadRawLogs();
result.failed_download_not_created = !createdDownload;
result.failed_download_notified = notices.length > beforeNotices;

let source = read('app.js').replace(/^import[^;]*;\s*$/gm, '');
const sandbox = { document, window, I18n, setTimeout: fn => { fn(); return 1; }, clearTimeout() {}, console };
vm.runInNewContext(`${source}\nthis.App = MeshCoreApp;`, sandbox);
const app = Object.create(sandbox.App.prototype);
app._ensureSystemDialogModal = () => document.getElementById('systemDialogModal');
const first = app.showConfirm('first', { isDanger: true });
await Promise.resolve();
document.activeElement = document.getElementById('btnCancelSystemDialog');
const enter = { key: 'Enter', target: document.activeElement, defaultPrevented: false,
  preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, stopImmediatePropagation() {} };
document.fire('keydown', enter);
// Emulate the browser's native button activation if the handler did not consume Enter.
if (!enter.defaultPrevented) document.activeElement.click();
result.enter_on_cancel_cancels = (await first) === false;
const second = app.showConfirm('second');
const third = app.showConfirm('third');
await Promise.resolve();
result.concurrent_dialogs_serialized = document.getElementById('systemDialogMessage').textContent === 'second';
document.getElementById('btnConfirmSystemDialog').click();
await second;
await Promise.resolve(); await Promise.resolve();
document.getElementById('btnCancelSystemDialog').click();
result.concurrent_independent_answers = (await third) === false;
const safe = module.createLogElement({ level: 'INFO', source: '<img onerror=fixture>', message: '<script>fixture</script>', exception: '<b>fixture</b>' }).innerHTML;
result.log_html_escaped = !safe.includes('<script>') && !safe.includes('<img onerror=');
console.log(JSON.stringify({ node: process.version, baseline, source: baseline ? baselineRevision : 'working-tree', warnings, checks: result, passed: Object.values(result).filter(Boolean).length,
  total: Object.keys(result).length }, null, 2));
if (process.argv.includes('--require-pass') && Object.values(result).some(value => !value)) process.exitCode = 1;
