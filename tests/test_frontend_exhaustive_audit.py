"""Observable regressions from the exhaustive frontend review, on virtual fixtures."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

ARTIFACTS = Path("tests/artifacts/frontend-exhaustive") / os.getenv("FRONTEND_AUDIT_PHASE", "final")


@pytest.mark.parametrize("width,height", [(390, 844), (1920, 1080)])
@pytest.mark.parametrize("theme", ["dark", "light"])
async def test_system_logs_rendered_contrast_and_long_entries(
    browser_page: Page, width: int, height: int, theme: str
) -> None:
    await browser_page.set_viewport_size({"width": width, "height": height})
    await browser_page.evaluate("theme => {document.body.classList.remove('light-theme', 'dark-theme'); document.body.classList.add(theme + '-theme');}", theme)
    await browser_page.locator('[data-tab="tab-logs"]').click()
    await browser_page.evaluate("""async () => {
        const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
        for (const level of ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']) {
            const category={DEBUG:'[TRAFICO-SOSPECHOSO] ',INFO:'[HTTP-CLIENT] ',WARNING:'[RX-AUDIT] '}[level]||'';
            eventBus.emit(EVENTS.SYSTEM_LOG, {level, iso_time: '2026-10-03 12:34:56',
                module: 'audit.module.' + 'longname'.repeat(8),
                message: level + ' audit ' + category + '<img src=x onerror=alert(1)> ' + 'long-entry-'.repeat(45),
                exception: level === 'ERROR' ? 'Traceback:\\n' + 'exception-with-no-spaces'.repeat(30) : ''});
        }
    }""")
    await expect(browser_page.locator('#systemLogsFeed .log-row').last).to_contain_text('CRITICAL audit')
    report = await browser_page.evaluate("""() => {
        function blend(a,b) { const alpha=a[3] ?? 1; return a.slice(0,3).map((v,i)=>v*alpha+b[i]*(1-alpha)).concat(1); }
        function parse(s) { return s.match(/[\\d.]+/g).map(Number); }
        function bg(el) { let chain=[]; for(let p=el;p;p=p.parentElement) chain.push(p); let color=[255,255,255,1]; for(const p of chain.reverse()) color=blend(parse(getComputedStyle(p).backgroundColor),color); return color; }
        function lum(rgb) { return rgb.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0); }
        const entries=[...document.querySelectorAll('#systemLogsFeed .log-row')].slice(-5);
        const colors=entries.flatMap(row=>[...row.querySelectorAll('.log-time,.log-badge,.log-mod,.log-msg,.log-trace')].map(el=>{
            let background=bg(el),foreground=blend(parse(getComputedStyle(el).color),background),a=lum(foreground),b=lum(background);
            return {class:el.className, foreground,background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
        }));
        return {colors,scroll:document.documentElement.scrollWidth,width:innerWidth,
            messageWidths:entries.map(row=>row.querySelector('.log-msg').getBoundingClientRect().width),
            feedBackground:getComputedStyle(document.querySelector('#systemLogsFeed')).backgroundColor,
            boxBackground:getComputedStyle(document.querySelector('.system-logs-box')).backgroundColor,
            injectedImages:document.querySelectorAll('#systemLogsFeed img').length};
    }""")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"logs-{theme}-{width}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    await browser_page.screenshot(path=str(ARTIFACTS / f"logs-{theme}-{width}.png"), animations="disabled")
    assert not report["injectedImages"], report
    assert report["scroll"] <= width, report
    assert min(report["messageWidths"]) >= 160, report
    assert not [item for item in report["colors"] if item["ratio"] < 4.5], report


@pytest.mark.parametrize("lang", ["es", "en"])
async def test_logs_http_failures_preserve_data_and_debug_state(browser_page: Page, lang: str) -> None:
    await browser_page.evaluate("lang=>{if(I18n.lang!==lang) I18n.toggle();}", lang)
    await browser_page.locator('[data-tab="tab-logs"]').click()
    await browser_page.evaluate("""async () => {
        const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
        eventBus.emit(EVENTS.SYSTEM_LOG, {level:'INFO', source:'audit.source', message:'KEEP_ME audit log'});
        window.auditDownloads=0;
        const create=URL.createObjectURL; URL.createObjectURL=(...args)=>{window.auditDownloads++;return create(...args);};
        const original=window.fetch;
        window.fetch=(url,options={})=>{
            const path=new URL(String(url),location.href).pathname;
            if((path==='/api/system/logs' && options.method==='DELETE') || path==='/api/system/logs/level' || path==='/api/logs/download') {
                return Promise.resolve(new Response(JSON.stringify({status:'error',detail:'Denied <b>literal</b>'}),{status:403,headers:{'Content-Type':'application/json'}}));
            }
            return original(url,options);
        };
    }""")
    await browser_page.locator("#btnClearLogs").click()
    await expect(browser_page.locator(".toast-message").last).to_contain_text("Denied <b>literal</b>")
    await expect(browser_page.locator("#systemLogsFeed")).to_contain_text("KEEP_ME")
    await expect(browser_page.locator("#btnClearLogs")).to_be_enabled()
    await browser_page.locator('label[for="chkDebugMode"]').click()
    await expect(browser_page.locator("#chkDebugMode")).not_to_be_checked()
    await expect(browser_page.locator(".toast-message").last).to_contain_text("Denied <b>literal</b>")
    await browser_page.locator("#btnDownloadRawLogs").click()
    await expect(browser_page.locator("#systemDialogMessage")).to_contain_text("Denied <b>literal</b>")
    assert await browser_page.evaluate("window.auditDownloads") == 0
    assert await browser_page.locator(".toast-message b, #systemDialogMessage b").count() == 0
    await browser_page.locator("#btnConfirmSystemDialog").click()


async def test_logs_source_search_and_warn_alias(browser_page: Page) -> None:
    await browser_page.locator('[data-tab="tab-logs"]').click()
    await browser_page.evaluate("""async () => {
        const {eventBus, EVENTS} = await import('/js/core/eventbus.js');
        eventBus.emit(EVENTS.SYSTEM_LOG, {level:'warn', source:'audit.unique-source', message:'source-only marker'});
        eventBus.emit(EVENTS.SYSTEM_LOG, {level:'ERROR', source:'other', message:'other entry'});
    }""")
    await browser_page.locator("#logLevelFilter").select_option("WARNING")
    await browser_page.locator("#logSearchInput").fill("audit.unique-source")
    row = browser_page.locator('#systemLogsFeed .log-row')
    await expect(row).to_have_count(1)
    await expect(row.locator('.log-mod')).to_have_text('audit.unique-source')
    await expect(row.locator('.log-msg')).to_have_text('source-only marker')


async def test_system_dialog_cancel_enter_and_concurrent_queue(browser_page: Page) -> None:
    opener = browser_page.locator("#themeToggleBtn")
    await opener.focus()
    await browser_page.evaluate("""() => {
        window.auditDialogResults=[];
        window.showConfirm('First confirmation', {isDanger:true}).then(v=>window.auditDialogResults.push(['first',v]));
        window.showPrompt('Second prompt', 'draft').then(v=>window.auditDialogResults.push(['second',v]));
    }""")
    await expect(browser_page.locator('#systemDialogMessage')).to_have_text('First confirmation')
    await browser_page.locator('#btnCancelSystemDialog').focus()
    await browser_page.keyboard.press('Enter')
    await expect(browser_page.locator('#systemDialogMessage')).to_have_text('Second prompt')
    await browser_page.locator('#systemDialogInput').fill('literal <b>draft</b>')
    await browser_page.keyboard.press('Enter')
    await expect(browser_page.locator('#systemDialogModal')).not_to_be_visible()
    await browser_page.wait_for_function("window.auditDialogResults.length===2")
    assert await browser_page.evaluate('window.auditDialogResults') == [
        ['first', False], ['second', 'literal <b>draft</b>']
    ]
    await expect(opener).to_be_focused()


@pytest.mark.parametrize("width,height", [(390, 844), (844, 390)])
@pytest.mark.parametrize("theme", ["dark", "light"])
async def test_long_dialog_reflows_and_keyboard_focus(browser_page: Page, width: int, height: int, theme: str) -> None:
    await browser_page.set_viewport_size({"width":width,"height":height})
    await browser_page.evaluate("""theme=>{
        document.body.classList.remove('dark-theme','light-theme');document.body.classList.add(theme+'-theme');
        window.showConfirm('Long message with <b>literal markup</b>. '.repeat(180),{isDanger:true});
    }""", theme)
    modal = browser_page.locator('#systemDialogModal')
    await expect(modal).to_be_visible()
    card = await modal.locator('.modal-card').bounding_box()
    assert card is not None and card['x'] >= 0 and card['y'] >= 0, card
    assert card['x']+card['width'] <= width and card['y']+card['height'] <= height, card
    for selector in ('#btnConfirmSystemDialog', '#btnCancelSystemDialog', '#btnCloseSystemDialog'):
        await browser_page.locator(selector).click(trial=True)
    assert await browser_page.locator('#systemDialogMessage b').count() == 0
    await browser_page.locator('#btnCloseSystemDialog').focus()
    await browser_page.keyboard.press('Shift+Tab')
    await expect(browser_page.locator('#btnConfirmSystemDialog')).to_be_focused()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    await browser_page.screenshot(path=str(ARTIFACTS/f'dialog-{theme}-{width}.png'), animations='disabled')
    await browser_page.keyboard.press('Escape')
    await expect(modal).not_to_be_visible()


@pytest.mark.parametrize("width,height", [(320, 740), (844, 390), (1920, 1080)])
@pytest.mark.parametrize("theme", ["dark", "light"])
async def test_authenticated_remote_admin_panels_reflow(browser_page: Page, width: int, height: int, theme: str) -> None:
    await browser_page.set_viewport_size({"width":width,"height":height})
    await browser_page.evaluate("""theme=>{
        document.body.classList.remove('dark-theme','light-theme');document.body.classList.add(theme+'-theme');
        const original=window.fetch;
        window.fetch=(url,options)=>{
            const path=new URL(String(url),location.href).pathname;
            if(path.startsWith('/api/repeater/remote/')) {
                window.auditRemoteRequests=(window.auditRemoteRequests||[]).concat(path);
                const data=path.endsWith('/login')?{authenticated:true}:{telemetry:{freq:915,tx_power:17},responses:{}};
                return Promise.resolve(new Response(JSON.stringify({status:'ok',data}),{status:200,headers:{'Content-Type':'application/json'}}));
            }
            return original(url,options);
        };
    }""", theme)
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    await browser_page.locator('.btn-manage-repeater').first.click()
    await expect(browser_page.locator('#repeaterAuthGate')).to_be_visible()
    await browser_page.locator('#repeaterGatePassword').fill('virtual-only-password')
    await browser_page.locator('#btnRepeaterGateSubmit').click()
    await expect(browser_page.locator('#repeaterAdminModalCard')).to_have_class(re.compile(r'.*\bunlocked\b.*'))
    modal = browser_page.locator('#repeaterAdminModal')
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for lang in ('es','en'):
        await browser_page.evaluate("lang=>{if(I18n.lang!==lang)I18n.toggle();}", lang)
        for panel in ('rep-info','rep-radio','rep-owner-pos','rep-security','rep-neighbors','rep-console'):
            await modal.locator(f'.subtab-btn[data-subtab="{panel}"]').click()
            await expect(browser_page.locator(f'#{panel}')).to_be_visible()
            card = await modal.locator('.modal-card').bounding_box()
            assert card is not None and card['x'] >= 0 and card['y'] >= 0, card
            assert card['x']+card['width'] <= width and card['y']+card['height'] <= height, card
            geometry = await browser_page.evaluate("""() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
                outside:[...document.querySelectorAll('body *')].filter(el=>el.checkVisibility()).map(el=>({id:el.id,cls:String(el.className),...el.getBoundingClientRect().toJSON()})).filter(r=>r.width>0&&(r.left<0||r.right>innerWidth+1)).slice(0,20)})""")
            if geometry['scroll'] > width:
                (ARTIFACTS/f'remote-overflow-{theme}-{width}.json').write_text(json.dumps({"panel":panel,"lang":lang,**geometry},indent=2),encoding='utf-8')
                await browser_page.screenshot(path=str(ARTIFACTS/f'remote-overflow-{theme}-{width}.png'),animations='disabled')
            assert geometry['scroll'] <= width, (panel,lang,geometry)
            if panel in ('rep-radio','rep-owner-pos','rep-security'):
                await browser_page.locator(f'#{panel} .form-actions-full button').last.click(trial=True)
            if panel == 'rep-console':
                await browser_page.locator('#repeaterTerminalInput').click(trial=True)
            if panel in ('rep-radio','rep-console'):
                await browser_page.screenshot(path=str(ARTIFACTS/f'remote-{panel}-{theme}-{lang}-{width}.png'), animations='disabled')
    assert '/api/repeater/remote/login' in await browser_page.evaluate('window.auditRemoteRequests')
    await browser_page.locator('#btnCloseRepeaterAdminModal').click()


@pytest.mark.parametrize("theme", ['dark','light'])
async def test_hover_switch_and_offline_card_keep_theme_contrast(browser_page: Page, theme: str) -> None:
    await browser_page.evaluate("theme=>{document.body.classList.remove('dark-theme','light-theme');document.body.classList.add(theme+'-theme');}", theme)
    await browser_page.locator('[data-tab="tab-settings"]').click()
    await browser_page.locator('[data-subtab="local-owner-pos"]').click()
    group = browser_page.locator('#local-owner-pos .toggle-field-group').first
    await group.hover()
    ratio = await group.evaluate("""el=>{
        const rgb=s=>s.match(/[\\d.]+/g).slice(0,3).map(Number);
        const lum=c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
        const a=lum(rgb(getComputedStyle(el.querySelector('.toggle-field-title')).color)),b=lum(rgb(getComputedStyle(el).backgroundColor));
        return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    }""")
    assert ratio>=4.5, (theme,ratio)
    await browser_page.locator('[data-tab="tab-nodes"]').click()
    card = browser_page.locator('#nodesUnifiedGridUi .node-card').first
    await card.evaluate("el=>el.classList.add('node-card-offline')")
    assert await card.evaluate("el=>getComputedStyle(el).opacity") == '1'
    assert await card.evaluate("el=>getComputedStyle(el).borderTopStyle") == 'dashed'


@pytest.mark.parametrize('kind', ['confirm','prompt'])
async def test_open_dialog_language_changes_keep_custom_copy_and_drafts(browser_page: Page, kind: str) -> None:
    await browser_page.evaluate("""kind=>{
        if(I18n.lang!=='es')I18n.toggle();
        if(kind==='confirm')window.showConfirm('Original literal message');
        else window.showPrompt('Original literal message','KEEP_DRAFT');
    }""",kind)
    await expect(browser_page.locator('#systemDialogModal')).to_be_visible()
    await browser_page.evaluate('I18n.toggle()')
    await expect(browser_page.locator('#systemDialogTitleText')).to_have_text('Confirm' if kind=='confirm' else 'Data input')
    await expect(browser_page.locator('#btnConfirmSystemDialog')).to_have_text('Confirm')
    await expect(browser_page.locator('#btnCancelSystemDialog')).to_have_text('Cancel')
    await expect(browser_page.locator('#systemDialogMessage')).to_have_text('Original literal message')
    if kind=='prompt':
        await expect(browser_page.locator('#systemDialogInput')).to_have_value('KEEP_DRAFT')
    await browser_page.keyboard.press('Escape')
    await browser_page.evaluate("""kind=>{
        const options={title:'Operator title',confirmText:'Proceed now',cancelText:'Keep'};
        if(kind==='confirm')window.showConfirm('User message',options);
        else window.showPrompt('User message','OTHER_DRAFT',options);
    }""",kind)
    await expect(browser_page.locator('#systemDialogTitleText')).to_have_text('Operator title')
    await browser_page.evaluate('I18n.toggle()')
    await expect(browser_page.locator('#systemDialogTitleText')).to_have_text('Operator title')
    await expect(browser_page.locator('#btnConfirmSystemDialog')).to_have_text('Proceed now')
    await expect(browser_page.locator('#btnCancelSystemDialog')).to_have_text('Keep')
    await browser_page.keyboard.press('Escape')


@pytest.mark.parametrize('theme',['dark','light'])
async def test_intermediate_header_widths_keep_controls_accessible(browser_page: Page, theme: str) -> None:
    await browser_page.evaluate("theme=>{document.body.classList.remove('dark-theme','light-theme');document.body.classList.add(theme+'-theme');}",theme)
    for width in (320,390,769,844,900,1024,1100,1201):
        await browser_page.set_viewport_size({'width':width,'height':740})
        for lang in ('es','en'):
            await browser_page.evaluate("lang=>{if(I18n.lang!==lang)I18n.toggle();}",lang)
            assert await browser_page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (theme,width,lang)
            for selector in ('#themeToggleBtn','#langToggleBtn','.header-center button'):
                box=await browser_page.locator(selector).bounding_box()
                assert box is not None and 0<=box['x'] and box['x']+box['width']<=width, (width,selector,box)
                await browser_page.locator(selector).click(trial=True)
