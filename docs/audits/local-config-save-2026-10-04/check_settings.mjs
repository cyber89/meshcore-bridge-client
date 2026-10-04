// Isolated SettingsModule checks. No station, files containing user data, broker, or radio.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const baseline = process.argv.includes('--baseline');
const revision = process.argv.find(arg => arg.startsWith('--revision='))?.slice(11) || '226f8ac';
const read = file => baseline ? execFileSync('git', ['show', `${revision}:src/web/static/js/${file}`], {encoding:'utf8'}) : fs.readFileSync(path.join(process.cwd(), 'src/web/static/js', file), 'utf8');
const dataUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const {SettingsModule} = await import(dataUrl(read('modules/settings.js').replace('../core/utils.js', dataUrl(read('core/utils.js'))).replace('../core/eventbus.js', dataUrl(read('core/eventbus.js')))));
class Element {
  constructor(value='', type='text') { this.value = value; this.type = type; this.checked = false; this.disabled = false; this.style = {}; this.classList = {add(){},remove(){},toggle(){}}; }
  removeAttribute() {}
}
let elements, notices, requests, module;
globalThis.I18n = {t:(key, params={}) => key + JSON.stringify(params),setText:(element,key)=>{element.textContent=key;}};
globalThis.window = {};
globalThis.document = {getElementById:id=>elements.get(id)||null,activeElement:null};
const reply = (data, ok=true) => ({ok,status:ok?200:400,json:async()=>data});
const deferred = () => {let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const cases = [];
async function check(name, test) {
  elements = new Map(); notices = []; requests = []; document.activeElement = null;
  module = new SettingsModule({showToast:(...args)=>notices.push(args)});
  globalThis.fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options?.body||'{}')});return reply({status:'ok',data:{status:'ok',applied:requests.at(-1).body,config:requests.at(-1).body}});};
  try { cases.push({name,passed:Boolean(await test())}); } catch(error) {cases.push({name,passed:false,error:error.message});}
}
function edit(id,value,type='text') {const el=new Element(value,type);elements.set(id,el);module.dirtyFields.add(id);module._fieldEditVersions?.set(id,1);return el;}
await check('single_power_only',async()=>{edit('localTxPower','18');await module.saveLocalRadioConfig();return requests.length===1&&JSON.stringify(requests[0].body)==='{"tx_power":18}'&&!module.dirtyFields.has('localTxPower');});
await check('policy_only_does_not_reset_radio',async()=>{edit('localTelemLoc','2');await module.saveLocalRadioConfig();return JSON.stringify(requests[0]?.body)==='{"telemetry_mode_loc":2}';});
await check('name_only_omits_unsupported_metadata',async()=>{edit('localNodeName',' New ');await module.saveLocalIdentityAndPosition();return JSON.stringify(requests[0]?.body)==='{"name":"New"}';});
await check('no_changes_no_post',async()=>{await module.saveLocalRadioConfig();return requests.length===0&&notices.at(-1)?.[1]==='info';});
await check('http_failure_not_success',async()=>{edit('localTxPower','18');fetch=async()=>reply({status:'ok'},false);await module.saveLocalRadioConfig();return module.dirtyFields.has('localTxPower')&&notices.at(-1)?.[1]==='error';});
await check('unconfirmed_no_optimistic_payload',async()=>{edit('localTxPower','18');fetch=async()=>reply({status:'ok'});await module.saveLocalRadioConfig();return module.cachedConfig.tx_power===undefined&&module.dirtyFields.has('localTxPower')&&notices.at(-1)?.[1]==='error';});
await check('partial_clears_only_acknowledged',async()=>{edit('localTxPower','18');edit('localTelemBase','0');fetch=async()=>reply({status:400,partial:true,applied:{tx_power:18},config:{tx_power:18,telemetry_mode_base:1},detail:'unsupported'},false);await module.saveLocalRadioConfig();return !module.dirtyFields.has('localTxPower')&&module.dirtyFields.has('localTelemBase')&&elements.get('localTelemBase').value==='0'&&notices.at(-1)?.[1]==='error';});
await check('status_ok_missing_key_not_success',async()=>{edit('localTxPower','18');edit('localSf','9');fetch=async()=>reply({status:'ok',data:{status:'ok',applied:{tx_power:18},config:{tx_power:18}}});await module.saveLocalRadioConfig();return module.dirtyFields.has('localSf')&&notices.at(-1)?.[1]==='error';});
await check('old_get_cannot_undo_saved_config',async()=>{const old=deferred();fetch=async(url,opts)=>opts?reply({status:'ok',data:{status:'ok',applied:{tx_power:18},config:{tx_power:18}}}):old.promise;const pendingRead=module.fetchLocalNodeConfig();edit('localTxPower','18');await module.saveLocalRadioConfig();old.resolve(reply({status:'ok',data:{tx_power:20}}));await pendingRead;return module.cachedConfig.tx_power===18&&elements.get('localTxPower').value==='18';});
await check('editing_while_saving_preserves_new_draft',async()=>{const response=deferred();const field=edit('localTxPower','18');fetch=()=>response.promise;const save=module.saveLocalRadioConfig();field.value='19';module._fieldEditVersions?.set('localTxPower',2);response.resolve(reply({status:'ok',data:{status:'ok',applied:{tx_power:18},config:{tx_power:18}}}));await save;return field.value==='19'&&module.dirtyFields.has('localTxPower')&&module.cachedConfig.tx_power===18;});
await check('same_value_edited_while_saving_remains_draft',async()=>{const response=deferred();edit('localTxPower','18');fetch=()=>response.promise;const save=module.saveLocalRadioConfig();module._fieldEditVersions?.set('localTxPower',3);response.resolve(reply({status:'ok',data:{status:'ok',applied:{tx_power:18},config:{tx_power:18}}}));await save;return module.dirtyFields.has('localTxPower');});
await check('clamped_ack_updates_focused_field',async()=>{const field=edit('localTxPower','23');document.activeElement=field;fetch=async()=>reply({status:'ok',data:{status:'ok',applied:{tx_power:20},config:{tx_power:20}}});await module.saveLocalRadioConfig();return field.value==='20'&&!module.dirtyFields.has('localTxPower');});
await check('pending_reboot_not_claimed_active',async()=>{edit('localFreq','868.1');fetch=async()=>reply({status:'ok',data:{status:'ok',pending_reboot:true,applied:{frequency:868.1},config:{frequency:869.5}}});await module.saveLocalRadioConfig();return module.dirtyFields.has('localFreq')&&module.cachedConfig.frequency===869.5&&notices.at(-1)?.[1]==='warning';});
await check('unsupported_periodic_controls_disabled',async()=>{for(const id of ['localTelemetryEnable','localAdvertEnable'])elements.set(id,new Element('', 'checkbox'));for(const id of ['localTelemetryInterval','localAdvertInterval','localHopLimit','localOwnerInfo','localGpsAlt'])elements.set(id,new Element('60'));module.populateLocalConfig({capabilities:{telemetry_interval:false,advert_interval:false,hop_limit:false,owner_info:false,altitude:false}});return [...elements.values()].every(el=>el.disabled)&&elements.get('localTelemetryInterval').value==='';});
await check('nonfinite_not_serialized_as_null',async()=>{edit('localRxDelay','oops');await module.saveLocalRadioConfig();return requests.length===0&&module.dirtyFields.has('localRxDelay')&&notices.at(-1)?.[1]==='error';});
await check('disconnect_keeps_save_button_disabled',async()=>{const button=new Element();module.dom.localRadioForm={querySelector:()=>button};edit('localTxPower','18');module.cachedConfig.serial_connected=false;await module.saveLocalRadioConfig();return button.disabled;});
await check('null_applied_is_not_confirmation',async()=>{edit('localTxPower','18');fetch=async()=>reply({status:'ok',data:{status:'ok',applied:{tx_power:null},config:{tx_power:20}}});await module.saveLocalRadioConfig();return module.dirtyFields.has('localTxPower')&&notices.at(-1)?.[1]==='error';});
await check('false_and_zero_acknowledgements_are_valid',async()=>{const field=edit('localMultiAcks','', 'checkbox');field.checked=false;edit('localRxDelay','0');await module.saveLocalRadioConfig();return !module.dirtyFields.has('localMultiAcks')&&!module.dirtyFields.has('localRxDelay')&&requests[0].body.multi_acks===false&&requests[0].body.rx_delay===0&&notices.at(-1)?.[1]==='success';});
const summary={baseline,revision:baseline?revision:'working-tree',passed:cases.filter(test=>test.passed).length,total:cases.length,cases};
process.stdout.write(JSON.stringify(summary,null,2)+'\n');
process.exitCode=summary.passed===summary.total?0:1;
