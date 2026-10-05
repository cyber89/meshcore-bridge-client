"""Remote configuration regressions with synthetic RF responses on a virtual station."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

ARTIFACTS = Path('tests/artifacts/config-parameters-2026-10-04')


@pytest.fixture
def page(browser_page: Page) -> Page:
    return browser_page


async def _open_remote(page: Page, password: str = "virtual-only-password") -> None:
    await page.evaluate("""() => {
      const original = window.fetch;
      window.remoteAuditRequests = [];
      window.remoteAuditReply = null;
      window.fetch = async (url, options) => {
        const path = new URL(String(url), location.href).pathname;
        if (!path.startsWith('/api/repeater/remote/')) return original(url, options);
        const body = JSON.parse(options?.body || '{}');
        window.remoteAuditRequests.push({path, body});
        let data = path.endsWith('/login') ? {authenticated:true} : {status:'ok',telemetry:{frequency:915,tx_power:17,spreading_factor:11,bandwidth:250,coding_rate:5,repeat:true},responses:{}};
        let status = 200;
        if (path.endsWith('/config')) {
          if (window.remoteAuditReply) ({data,status} = window.remoteAuditReply);
          else data = {status:'ok',applied:body.params};
        }
        return new Response(JSON.stringify({status:status >= 400 ? 'error':'ok',data,detail:status >= 400 ? 'QA partial <b>original</b>':undefined}), {status,headers:{'Content-Type':'application/json'}});
      };
    }""")
    await page.locator('[data-tab="tab-nodes"]').click()
    await page.locator('.btn-manage-repeater').first.click()
    await page.locator('#repeaterGatePassword').fill(password)
    await page.locator('#btnRepeaterGateSubmit').click()
    await expect(page.locator('#repeaterAdminModalCard')).to_have_class(re.compile(r'.*\bunlocked\b.*'))
    await expect(page.locator('#radioPower')).to_have_value('17')


async def _radio_panel(page: Page) -> None:
    await page.locator('#repeaterAdminModal [data-subtab="rep-radio"]').click()


async def _power(page: Page, value: str) -> None:
    await page.locator('#radioPower').evaluate("(element,value)=>{element.value=value;element.dispatchEvent(new Event('input',{bubbles:true}));}", value)


async def _config_requests(page: Page) -> list[dict[str, object]]:
    return await page.evaluate("window.remoteAuditRequests.filter(request=>request.path.endsWith('/config'))")


async def test_remote_single_power_only_confirmed_values(page: Page) -> None:
    await _open_remote(page)
    await _radio_panel(page)
    await _power(page, '18')
    await page.evaluate("window.remoteAuditReply={status:200,data:{status:'ok',applied:{tx_power:16}}}")
    await page.locator('#btnSubmitRepRadio').click()
    await expect(page.locator('#radioPower')).to_have_value('16')
    await expect(page.locator('#repSummaryPower')).to_have_text('16 dBm')
    requests = await _config_requests(page)
    assert requests[-1]['body']['params'] == {'tx_power': 18}
    await page.locator('#btnSubmitRepRadio').click()
    assert len(await _config_requests(page)) == 1


async def test_remote_partial_retry_only_unconfirmed_field(page: Page) -> None:
    await _open_remote(page)
    await _radio_panel(page)
    await _power(page, '18')
    await page.locator('label[for="radioRepeatMode"]').click()
    await page.evaluate("window.remoteAuditReply={status:400,data:{status:'partial',applied:{tx_power:18},results:[]}}")
    await page.locator('#btnSubmitRepRadio').click()
    await expect(page.locator('.toast-message').last).to_contain_text('QA partial <b>original</b>')
    assert await page.locator('.toast-message').last.locator('b').count() == 0
    await page.evaluate("window.remoteAuditReply=null")
    await page.locator('#btnSubmitRepRadio').click()
    requests = await _config_requests(page)
    assert requests[-1]['body']['params'] == {'repeat': False}


async def test_remote_radio_saved_keeps_active_summary_and_draft(page: Page) -> None:
    await _open_remote(page)
    await _radio_panel(page)
    await page.locator('#radioFreq').fill('868.100')
    await page.evaluate("window.remoteAuditReply={status:200,data:{status:'ok',pending_reboot:true,saved:{frequency:868.1,bandwidth:250,spreading_factor:11,coding_rate:5},applied:{}}}")
    await page.locator('#btnSubmitRepRadio').click()
    await expect(page.locator('.toast-message').last).to_contain_text('falta reiniciar')
    await expect(page.locator('#repSummaryFreq')).to_contain_text('915')
    await expect(page.locator('#radioFreq')).to_have_value('868.100')
    requests = await _config_requests(page)
    assert requests[-1]['body']['params'] == {'frequency': 868.1, 'bandwidth': 250, 'spreading_factor': 11, 'coding_rate': '4/5'}
    assert len(requests) == 1


async def test_remote_dispatched_password_does_not_replace_credentials(page: Page) -> None:
    await _open_remote(page)
    await page.locator('#repeaterAdminModal [data-subtab="rep-security"]').click()
    await page.locator('#secNewAdminPwd').fill('virtual-new-secret')
    await page.evaluate("window.remoteAuditReply={status:200,data:{status:'dispatched',applied:{},dispatched_commands:['password ********']}}")
    await page.locator('#btnSubmitRepSecurity').click()
    await expect(page.locator('.toast-message').last).to_contain_text('todavía no está confirmada')
    await expect(page.locator('#secNewAdminPwd')).to_have_value('virtual-new-secret')
    await expect(page.locator('#repeaterGatePassword')).to_have_value('virtual-only-password')
    terminal = await page.locator('#repeaterTerminalOutput').inner_text()
    assert 'virtual-new-secret' not in terminal
    await page.evaluate("window.remoteAuditReply={status:200,data:{status:'ok',applied:{new_password:'********'}}}")
    await page.locator('#btnSubmitRepSecurity').click()
    await expect(page.locator('#secNewAdminPwd')).to_have_value('')
    await expect(page.locator('#repeaterGatePassword')).to_have_value('virtual-new-secret')


@pytest.mark.parametrize('minutes', [0, 60, 240])
async def test_remote_advert_interval_uses_minutes(page: Page, minutes: int) -> None:
    await _open_remote(page)
    await _radio_panel(page)
    await page.locator('#radioBeaconInterval').fill(str(minutes))
    await page.locator('#btnSubmitRepRadio').click()
    await expect(page.locator('#radioBeaconInterval')).to_have_value(str(minutes))
    assert (await _config_requests(page))[-1]['body']['params'] == {'advert_interval': minutes}


@pytest.mark.parametrize('theme,width', [('light',390),('dark',1920)])
async def test_remote_unsupported_controls_and_language_layout(page: Page, theme: str, width: int) -> None:
    await page.set_viewport_size({'width':width,'height':844 if width == 390 else 1080})
    await page.evaluate("theme=>{document.body.classList.remove('dark-theme','light-theme');document.body.classList.add(theme+'-theme')}", theme)
    await _open_remote(page)
    for lang in ('es','en'):
        await page.evaluate("lang=>{if(I18n.lang!==lang)I18n.toggle()}",lang)
        for panel,ids in [('rep-radio',['radioHopLimit']),('rep-owner-pos',['repPosAlt','repPosFixed']),('rep-security',['secAclMode','secIdentityKey'])]:
            await page.locator(f'#repeaterAdminModal [data-subtab="{panel}"]').click()
            for field in ids:
                await expect(page.locator('#'+field)).to_be_disabled()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await _radio_panel(page)
        await expect(page.locator('label[for="radioBeaconInterval"]')).to_contain_text('minuto' if lang == 'es' else 'minutes')
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        await page.screenshot(path=str(ARTIFACTS/f'remote-radio-{theme}-{lang}-{width}.png'),animations='disabled')


@pytest.mark.parametrize('endpoint,button,panel', [('/owner','btnFetchRepOwner','rep-owner-pos'),('/regions','btnFetchRepRegions','rep-owner-pos'),('/acl','btnFetchRepAcl','rep-security'),('/neighbours','btnDiscoverNeighbors','rep-neighbors')])
async def test_remote_read_http_error_is_not_success(page: Page, endpoint: str, button: str, panel: str) -> None:
    await _open_remote(page)
    await page.evaluate("""suffix=>{const original=window.fetch;window.fetch=(url,options)=>String(url).endsWith(suffix)?Promise.resolve(new Response(JSON.stringify({status:'ok',data:{owner_name:'FAKE',regions:['FAKE'],acl_data:{FAKE:1},neighbours:[{name:'FAKE'}]},detail:'forbidden'}),{status:403,headers:{'Content-Type':'application/json'}})):original(url,options)}""", endpoint)
    await page.locator(f'#repeaterAdminModal [data-subtab="{panel}"]').click()
    await page.locator('#'+button).click()
    await expect(page.locator('#repeaterTerminalOutput')).to_contain_text('forbidden')
    await expect(page.locator('#repeaterTerminalOutput')).not_to_contain_text('FAKE')


async def test_terminal_echo_does_not_invent_device_state_or_leak_password(page: Page) -> None:
    await _open_remote(page)
    await page.locator('#repeaterAdminModal [data-subtab="rep-console"]').click()
    await page.evaluate("""()=>{const original=window.fetch;window.fetch=(url,options)=>String(url).endsWith('/action')?Promise.resolve(new Response(JSON.stringify({status:'ok',data:{status:'dispatched',message:'sent'}}),{status:200,headers:{'Content-Type':'application/json'}})):original(url,options)}""")
    await page.locator('#repeaterTerminalInput').fill('password virtual-cli-secret')
    await page.locator('#repeaterTerminalForm').evaluate("form=>form.requestSubmit()")
    await expect(page.locator('#repeaterTerminalOutput')).not_to_contain_text('virtual-cli-secret')
    await page.locator('#repeaterTerminalInput').press('ArrowUp')
    await expect(page.locator('#repeaterTerminalInput')).to_have_value('')
    await page.locator('#repeaterTerminalInput').fill('set tx 21')
    await page.locator('#repeaterTerminalForm').evaluate("form=>form.requestSubmit()")
    await expect(page.locator('#repSummaryPower')).to_have_text('17 dBm')


async def test_remote_event_sender_and_structured_data_are_required(page: Page) -> None:
    await _open_remote(page)
    await _radio_panel(page)
    await page.evaluate("""async()=>{
      const {eventBus,EVENTS}=await import('/js/core/eventbus.js');
      eventBus.emit(EVENTS.RX_PACKET,{type:'repeater_response',sender:'bb'.repeat(32),text:'power 30',telemetry:{tx_power:30}});
    }""")
    await expect(page.locator('#repSummaryPower')).to_have_text('17 dBm')
    await page.evaluate("""async()=>{
      const {eventBus,EVENTS}=await import('/js/core/eventbus.js');
      const sender=document.querySelector('#adminModalNodePk').value;
      eventBus.emit(EVENTS.RX_PACKET,{type:'repeater_response',sender,text:'power 21'});
    }""")
    await expect(page.locator('#repSummaryPower')).to_have_text('17 dBm')
    await _power(page,'18')
    await page.evaluate("""async()=>{
      const {eventBus,EVENTS}=await import('/js/core/eventbus.js');
      const sender=document.querySelector('#adminModalNodePk').value;
      eventBus.emit(EVENTS.RX_PACKET,{type:'repeater_response',sender,text:'structured',telemetry:{tx_power:16}});
    }""")
    await expect(page.locator('#repSummaryPower')).to_have_text('16 dBm')
    await expect(page.locator('#radioPower')).to_have_value('18')


async def test_remote_manual_radio_read_only_populates_saved_preferences(page: Page) -> None:
    await _open_remote(page)
    await page.evaluate("""()=>{const original=window.fetch;window.fetch=(url,options)=>String(url).endsWith('/action')?Promise.resolve(new Response(JSON.stringify({status:'ok',data:{status:'ok',text:'868.1,250,7,5',saved:{frequency:868.1,bandwidth:250,spreading_factor:7,coding_rate:5},radio_settings_source:'saved_preferences'}}),{status:200,headers:{'Content-Type':'application/json'}})):original(url,options)}""")
    await page.locator('#btnModalActionRadioStats').click()
    await expect(page.locator('#radioFreq')).to_have_value('868.1')
    await expect(page.locator('#radioSf')).to_have_value('7')
    await expect(page.locator('#repSummaryFreq')).to_contain_text('915')


async def test_remote_password_literal_spaces_preserved_in_login_and_rotation(page: Page) -> None:
    await _open_remote(page, ' root123 ')
    requests = await page.evaluate('window.remoteAuditRequests')
    assert next(request['body']['password'] for request in requests if request['path'].endswith('/login')) == ' root123 '
    await page.locator('#repeaterAdminModal [data-subtab="rep-security"]').click()
    await page.locator('#secNewAdminPwd').fill(' next456 ')
    await page.evaluate("window.remoteAuditReply={status:200,data:{status:'ok',applied:{new_password:'********'}}}")
    await page.locator('#btnSubmitRepSecurity').click()
    await expect(page.locator('#repeaterGatePassword')).to_have_value(' next456 ')
    assert (await _config_requests(page))[-1]['body']['params'] == {'new_password': ' next456 '}
    await _radio_panel(page)
    await _power(page,'18')
    await page.evaluate('window.remoteAuditReply=null')
    await page.locator('#btnSubmitRepRadio').click()
    await expect(page.locator('#radioPower')).to_have_value('18')
    assert (await _config_requests(page))[-1]['body']['password'] == ' next456 '
