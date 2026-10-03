"""Directed frontend audit only; reuse the maintained isolated virtual bridge."""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import pytest
def deny_operational_env(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes)):
        if Path(str(args[0])).name == ".env":
            raise PermissionError("Operational .env access denied by frontend audit")
sys.addaudithook(deny_operational_env)
import conftest
from playwright.async_api import async_playwright

OUT = Path(__file__).parent


async def main() -> None:
    report: dict = {"base_head": "9f561932d648470e8c8bd23fc789a66bdb378d0e", "requests": [], "reproductions": {}}
    with tempfile.TemporaryDirectory(prefix="config-ui-audit-", dir=OUT) as tmp, pytest.MonkeyPatch.context() as mp:
        isolated = conftest.isolated_state.__wrapped__(Path(tmp), mp)
        next(isolated)
        virtual = conftest.virtual_bridge.__wrapped__(Path(tmp))
        bridge = await anext(virtual)
        try:
            server = bridge.web_server.server
            origin = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            report["virtual_origin"] = origin
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                report['tools']={'playwright':version('playwright'),'chromium':browser.version,'python':sys.version}
                try:
                    context = await browser.new_context(viewport={"width": 390, "height": 844})
                    await context.grant_permissions(["local-network-access"], origin=origin)
                    mode = {"error": False, "delay": False}

                    async def route_request(route):
                        req = route.request
                        path = urlsplit(req.url).path
                        if not req.url.startswith(origin + "/"):
                            report.setdefault("blocked_external", []).append(req.url)
                            await route.abort()
                        elif req.method == "POST":
                            body = req.post_data_json
                            report["requests"].append({"path": path, "body": body})
                            if mode["delay"]:
                                await asyncio.sleep(.4)
                            if mode["error"]:
                                await route.fulfill(status=422, json={"status": 422, "title": "Unprocessable Entity", "detail": "AUDIT_EXACT_VALIDATION_DETAIL", "type": "about:blank"})
                            elif mode.get("owner"):
                                await route.fulfill(json={"status":"ok","data":{"owner_name":"OBSERVED_A","owner_info":"INFO_A"}})
                            elif mode.get("dispatched"):
                                await route.fulfill(json={"status":"ok","data":{"status":"dispatched","pending_reboot":True,"operations":[{"status":"dispatched"}]}})
                            else:
                                await route.fulfill(json={"status": "ok", "data": {"config": {"frequency": 433.125, "altitude_m": 123}, "authenticated": True}})
                        elif req.resource_type == "document":
                            response = await route.fetch()
                            html = re.sub(r'<link\b[^>]*href="https://[^>]*>', "", await response.text())
                            html = re.sub(r'<script\b[^>]*src="https://[^>]*></script>', "", html)
                            await route.fulfill(response=response, body=html)
                        else:
                            await route.continue_()

                    await context.route("**/*", route_request)
                    page = await context.new_page()
                    page.on("pageerror", lambda e: report.setdefault("page_errors", []).append(str(e)))
                    page.on("console", lambda m: report.setdefault("console_errors", []).append(m.text) if m.type == "error" else None)
                    await page.goto(origin, wait_until="domcontentloaded")
                    await page.locator('#channelListUi [data-channel-idx="1"]').wait_for()
                    await page.evaluate("""async () => {
                      const {SettingsModule} = await import('/js/modules/settings.js');
                      const {RepeaterModule} = await import('/js/modules/repeater.js');
                      window.auditToasts=[];
                      window.auditCtx={knownNodes:new Map(), getAuthHeaders:()=>({'Content-Type':'application/json'}), showToast:(message,type)=>auditToasts.push({message,type})};
                      for(const id of ['localRadioForm','localOwnerPosForm']) { const el=document.getElementById(id);el.replaceWith(el.cloneNode(true)); }
                      window.auditSettings=new SettingsModule(auditCtx); auditSettings._bindElements();auditSettings._bindEvents();
                      // Detach original modal listeners; bind the same production module in isolation.
                      const modal=document.getElementById('repeaterAdminModal'); modal.replaceWith(modal.cloneNode(true));
                      window.auditRepeater=new RepeaterModule(auditCtx); auditRepeater._bindElements();auditRepeater._bindEvents();
                    }""")
                    results = report["reproductions"]
                    results["local_draft_overwrite_and_altitude"] = await page.evaluate("""() => {
                      const s=auditSettings;s.populateLocalConfig({name:'ORIGINAL',frequency:915,altitude_m:123,autoadd_config:{config:0,max_hops:0}});
                      document.getElementById('localFreq').value='916.5';document.getElementById('localFreq').dispatchEvent(new Event('input'));document.getElementById('localNodeName').value='UNSAVED_DRAFT';document.getElementById('localNodeName').dispatchEvent(new Event('input'));
                      s.populateLocalConfig({battery_pct:77});
                      return {frequency:document.getElementById('localFreq').value,name:document.getElementById('localNodeName').value,altitude:document.getElementById('localGpsAlt').value,max_hops:document.getElementById('numAutoAddMaxHops').value,auto_chat:document.getElementById('chkAutoAddChat').checked};
                    }""")
                    results["local_capability_controls"] = await page.evaluate("""() => {
                      auditSettings.populateLocalConfig({role:'CLIENT',radio_connected:false,capabilities:{radio:false,repeat:false,set_pin:false}});
                      return ['btnSaveLocalRadio','localRepeatMode','localDevicePin','localPathHashMode','btnActionAdvertHop','btnActionRebootLocal'].map(id=>({id,disabled:document.getElementById(id)?.disabled}));
                    }""")
                    await page.evaluate("auditSettings.saveLocalRadioConfig()")
                    results["local_server_normalization_ignored"] = await page.evaluate("() => ({display:document.getElementById('localFreq').value,cached:auditSettings.cachedConfig.frequency,toasts:auditToasts.slice(-1)})")
                    await page.evaluate("() => {document.getElementById('localRxDelay').value='0.5';document.getElementById('localAirtimeFactor').value='1.5';}")
                    await page.evaluate("auditSettings.saveLocalRadioConfig()")
                    results['local_fractional_tuning']={key:report['requests'][-1]['body'][key] for key in ['rx_delay','airtime_factor']}
                    mode["error"] = True
                    await page.evaluate("auditSettings.saveLocalIdentityAndPosition()")
                    results["local_problem_detail"] = await page.evaluate("auditToasts.slice(-1)")
                    mode["error"] = False
                    results["remote_role_capabilities_and_zero_power"] = await page.evaluate("""() => {
                      const r=auditRepeater;r.selectedRepeaterTarget='ca'.repeat(32);auditCtx.knownNodes.set(r.selectedRepeaterTarget,{public_key:r.selectedRepeaterTarget,role:'CLIENT'});
                      r.openRepeaterAdminModal(r.selectedRepeaterTarget,'AUDIT CLIENT');
                      const gateVisible=!document.getElementById('repeaterAuthGate').classList.contains('hidden');
                      r.unlockRepeaterAdminView(r.selectedRepeaterTarget);
                      r.populateRepeaterModalData({public_key:r.selectedRepeaterTarget,role:'CLIENT',tx_power:0,min_tx_power:0,max_tx_power:14,frequency:915,capabilities:{radio:false,config:false}});
                      const zeroPowerDisplay=document.getElementById('radioPower').value;
                      document.getElementById('radioFreq').value='916.5';document.getElementById('radioFreq').dispatchEvent(new Event('input'));r.populateRepeaterModalData({public_key:r.selectedRepeaterTarget,frequency:915,battery_pct:80});
                      return {gateVisible,zeroPowerDisplay,powerAfterPartialUpdate:document.getElementById('radioPower').value,frequencyAfterUpdate:document.getElementById('radioFreq').value,controls:['btnSubmitRepRadio','radioRepeatMode','btnModalActionReboot'].map(id=>({id,disabled:document.getElementById(id)?.disabled}))};
                    }""")
                    mode["delay"] = True
                    before = len(report["requests"])
                    results["remote_radio_busy"] = await page.evaluate("""() => {
                      document.getElementById('repRadioForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                      const disabled=document.getElementById('btnSubmitRepRadio').disabled;
                      document.getElementById('repRadioForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                      return {buttonDisabledAfterFirst:disabled};
                    }""")
                    await page.wait_for_timeout(650)
                    results["remote_radio_busy"]["posts"] = len(report["requests"]) - before
                    mode["delay"] = False
                    mode["error"] = True
                    await page.evaluate("document.getElementById('repRadioForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
                    await page.wait_for_timeout(150)
                    results["remote_problem_detail"] = await page.locator("#repeaterTerminalOutput").inner_text()
                    mode["error"] = False
                    results["target_switch_stale_fields"] = await page.evaluate("""() => {
                      const r=auditRepeater;const a='aa'.repeat(32),b='bb'.repeat(32);
                      auditCtx.knownNodes.set(a,{public_key:a,role:'REPEATER',frequency:867.5,latitude:10,longitude:20,owner_info:'OWNER_A',spreading_factor:9});
                      auditCtx.knownNodes.set(b,{public_key:b,role:'REPEATER'});
                      r.openRepeaterAdminModal(a,'AUDIT A');r.openRepeaterAdminModal(b,'AUDIT B');
                      return {frequency:document.getElementById('radioFreq').value,sf:document.getElementById('radioSf').value,owner:document.getElementById('repOwnerInfo').value,lat:document.getElementById('repPosLat').value};
                    }""")
                    before=len(report['requests'])
                    await page.evaluate("document.getElementById('repSecurityForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
                    await page.wait_for_timeout(150)
                    results['remote_security_unchanged']={'posts':len(report['requests'])-before,'last_request':report['requests'][-1] if len(report['requests'])>before else None}
                    report['control_inventory']=await page.evaluate("""() => [...document.querySelectorAll('#tab-settings input,#tab-settings select,#tab-settings textarea,#repeaterAdminModal input,#repeaterAdminModal select')].map(e=>({id:e.id,type:e.type,form:e.form?.id,readonly:e.readOnly,disabled:e.disabled,required:e.required,min:e.min,max:e.max,step:e.step,labels:[...e.labels||[]].map(l=>l.textContent.trim()),options:e.options?[...e.options].map(o=>({value:o.value,text:o.textContent})):null}))""")
                    await extra_reproductions(page,report,mode)
                    (OUT/'reproduction-results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
                    await page.evaluate("auditRepeater.closeRepeaterAdminModal()")
                    # Directed visual check of each local and remote configuration subpanel.
                    for theme in ['dark','light']:
                        for lang in ['es','en']:
                            await page.evaluate("([theme,lang])=>{document.body.classList.toggle('light-theme',theme==='light');if(I18n.lang!==lang)I18n.toggle();}",[theme,lang])
                            report.setdefault('i18n',{})[lang]=await page.evaluate("""() => {
                              const attrs=['data-i18n','data-i18n-placeholder','data-i18n-title','data-i18n-aria-label'];
                              const keys=[...new Set([...document.querySelectorAll('#tab-settings *,#repeaterAdminModal *')].flatMap(el=>attrs.map(a=>el.getAttribute(a)).filter(Boolean)))];
                              return {keys:keys.length,missing:keys.filter(key=>I18n.t(key)===key)};
                            }""")
                            for panel in ['local-radio','local-owner-pos','local-security']:
                                await page.locator('.nav-btn[data-tab="tab-settings"]').click()
                                await page.locator(f'.local-subtab-btn[data-subtab="{panel}"]').click()
                                await page.screenshot(path=str(OUT/f'{theme}-{lang}-{panel}-390.png'),animations='disabled')
                                report.setdefault('layout',{})[f'{theme}-{lang}-{panel}-390']=await measure_layout(page)
                            await page.evaluate("auditRepeater.unlockRepeaterAdminView(auditRepeater.selectedRepeaterTarget);document.getElementById('repeaterAdminModal').classList.remove('hidden')")
                            for panel in ['rep-radio','rep-owner-pos','rep-security']:
                                await page.locator(f'.repeater-subtabs .subtab-btn[data-subtab="{panel}"]').click()
                                await page.screenshot(path=str(OUT/f'{theme}-{lang}-{panel}-390.png'),animations='disabled')
                                report.setdefault('layout',{})[f'{theme}-{lang}-{panel}-390']=await measure_layout(page)
                            await page.evaluate("auditRepeater.closeRepeaterAdminModal()")
                    await page.set_viewport_size({'width':1920,'height':1080})
                    await page.evaluate("()=>{document.body.classList.add('light-theme');if(I18n.lang!=='es')I18n.toggle();}")
                    await page.locator('.local-subtab-btn[data-subtab="local-radio"]').click()
                    await page.screenshot(path=str(OUT/'light-es-local-radio-1920.png'),animations='disabled')
                    report['layout']['light-es-local-radio-1920']=await measure_layout(page)
                    await page.evaluate("auditRepeater.unlockRepeaterAdminView(auditRepeater.selectedRepeaterTarget);document.getElementById('repeaterAdminModal').classList.remove('hidden')")
                    await page.locator('.repeater-subtabs .subtab-btn[data-subtab="rep-radio"]').click()
                    await page.screenshot(path=str(OUT/'light-es-rep-radio-1920.png'),animations='disabled')
                    report['layout']['light-es-rep-radio-1920']=await measure_layout(page)
                    report["websocket_connected"] = bool(bridge.web_server.active_websockets)
                    await context.close()
                finally:
                    await browser.close()
        finally:
            await virtual.aclose()
            try:
                next(isolated)
            except StopIteration:
                pass
    (OUT/'reproduction-results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report['reproductions'],indent=2,ensure_ascii=True))



async def extra_reproductions(page,report,mode):
    r=report['reproductions']
    r['native_numeric_validity']=await page.evaluate("""() => {
      auditSettings.dirtyFields.clear();auditSettings.populateLocalConfig({spreading_factor:5,tx_power:0,min_tx_power:-9,max_tx_power:22,rx_delay:0.5,airtime_factor:1.5,radio_connected:true});
      const out=['localSf','localTxPower','localRxDelay','localAirtimeFactor'].map(id=>{const e=document.getElementById(id);return {id,value:e.value,valid:e.checkValidity(),stepMismatch:e.validity.stepMismatch,min:e.min,max:e.max}});
      document.getElementById('localFreq').value='915.123';out.push({id:'localFreq',value:document.getElementById('localFreq').value,valid:document.getElementById('localFreq').checkValidity(),stepMismatch:document.getElementById('localFreq').validity.stepMismatch});return out;
    }""")
    r['client_entry_guard']=await page.evaluate("""()=>{auditRepeater.closeRepeaterAdminModal();const t='cc'.repeat(32);auditCtx.knownNodes.set(t,{public_key:t,role:'CLIENT'});auditRepeater.openRepeaterAdminModal(t,'CLIENT GUARD');return {target:auditRepeater.selectedRepeaterTarget,hidden:document.getElementById('repeaterAdminModal').classList.contains('hidden'),toast:auditToasts.slice(-1)}}""")
    before=len(report['requests']);await page.evaluate('auditSettings.saveLocalRadioConfig()')
    r['sf5_roundtrip_fallback']={'posts':len(report['requests'])-before,'sf':report['requests'][-1]['body']['spreading_factor'],'power':report['requests'][-1]['body']['tx_power']}
    r['autoadd_draft_overwrite']=await page.evaluate("""() => {
      document.getElementById('numAutoAddMaxHops').value='7';document.getElementById('numAutoAddMaxHops').dispatchEvent(new Event('input'));
      document.getElementById('chkAutoAddChat').checked=true;document.getElementById('chkAutoAddChat').dispatchEvent(new Event('change'));
      auditSettings.populateLocalConfig({battery_pct:79});return {hops:document.getElementById('numAutoAddMaxHops').value,chat:document.getElementById('chkAutoAddChat').checked};
    }""")
    await page.evaluate("""() => {auditSettings.dirtyFields.clear();auditSettings.populateLocalConfig({frequency:915,spreading_factor:9,pin:null,radio_connected:true});document.getElementById('localFreq').value='916.5';document.getElementById('localFreq').dispatchEvent(new Event('input'));document.getElementById('localDevicePin').value='';}""")
    before=len(report['requests']);await page.evaluate('auditSettings.saveLocalRadioConfig()')
    r['local_one_field_full_payload']={'posts':len(report['requests'])-before,'body':report['requests'][-1]['body']}
    await page.evaluate("""() => {const t='dd'.repeat(32);auditCtx.knownNodes.set(t,{public_key:t,role:'REPEATER',frequency:915});auditRepeater.openRepeaterAdminModal(t,'AUDIT DISPATCH');auditRepeater.unlockRepeaterAdminView(t);document.getElementById('radioFreq').value='916.5';document.getElementById('radioFreq').dispatchEvent(new Event('input'));}""")
    mode['dispatched']=True
    await page.evaluate("document.getElementById('repRadioForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
    await page.wait_for_timeout(150)
    r['remote_dispatched_presented_applied']=await page.evaluate("""()=>({frequency:auditCtx.knownNodes.get(auditRepeater.selectedRepeaterTarget).frequency,summary:document.getElementById('repSummaryFreq').textContent,dirty:auditRepeater.dirtyFields.has('radioFreq'),toast:auditToasts.slice(-1),terminal:document.getElementById('repeaterTerminalOutput').innerText})""")
    mode['dispatched']=False
    mode['delay']=True
    await page.evaluate("""() => {document.getElementById('localFreq').value='917';document.getElementById('localFreq').dispatchEvent(new Event('input'));window.pendingLocalSave=auditSettings.saveLocalRadioConfig();document.getElementById('localFreq').value='918';document.getElementById('localFreq').dispatchEvent(new Event('input'));auditSettings.populateLocalConfig({radio_connected:false});}""")
    await page.evaluate('pendingLocalSave')
    r['local_edit_during_save_and_disconnect']=await page.evaluate("""()=>({frequency:document.getElementById('localFreq').value,dirty:auditSettings.dirtyFields.has('localFreq'),saveDisabled:document.getElementById('btnSaveLocalRadio').disabled,radioConnected:auditSettings.cachedConfig.radio_connected})""")
    mode['delay']=False
    mode['owner']=True
    await page.evaluate("""()=>{const t=auditRepeater.selectedRepeaterTarget;document.getElementById('repOwnerName').value='UNSAVED_OWNER';document.getElementById('repOwnerName').dispatchEvent(new Event('input'));window.ownerRead=auditRepeater.fetchRepeaterOwner(t)}""")
    await page.evaluate('ownerRead')
    r['remote_owner_read_destroys_dirty']=await page.evaluate("""()=>({value:document.getElementById('repOwnerName').value,dirty:auditRepeater.dirtyFields.has('repOwnerName')})""")
    mode['delay']=True
    await page.evaluate("""()=>{window.ownerReadLate=auditRepeater.fetchRepeaterOwner(auditRepeater.selectedRepeaterTarget);const t='ee'.repeat(32);auditCtx.knownNodes.set(t,{public_key:t,role:'REPEATER',owner_name:'OWNER_B'});auditRepeater.openRepeaterAdminModal(t,'OWNER B')}""")
    await page.evaluate('ownerReadLate')
    r['remote_owner_read_cross_target']=await page.evaluate("""()=>({target:auditRepeater.selectedRepeaterTarget,name:document.getElementById('repOwnerName').value,info:document.getElementById('repOwnerInfo').value})""")
    mode['delay']=False;mode['owner']=False


async def measure_layout(page):
    return await page.evaluate("""() => {
      const active = [...document.querySelectorAll('.repeater-admin-modal-body,.main-content,#tab-settings')].filter(el=>el.getBoundingClientRect().width>0);
      return {viewport:innerWidth,root:{client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth},panels:active.map(el=>({selector:el.id||el.className,height:el.clientHeight,scrollHeight:el.scrollHeight,overflowY:getComputedStyle(el).overflowY})),tabs:[...document.querySelectorAll('.repeater-subtabs .subtab-btn')].filter(el=>el.getBoundingClientRect().width>0).map(el=>({text:el.textContent.trim(),client:el.clientWidth,scroll:el.scrollWidth,overflow:getComputedStyle(el).overflow}))};
    }""")


if __name__ == '__main__':
    asyncio.run(main())
