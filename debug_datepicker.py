"""date-range-picker 세그먼트 구조 확인용 디버그 스크립트"""

import asyncio, sys, json
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SITE_URL = "https://insight.shucle.com/metrics"
BROWSER_PROFILE = "./shucle_browser_profile"


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE, headless=False,
            viewport={"width": 1920, "height": 1080}, slow_mo=300,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("[접속] 사이트 접속 중...")
        await page.goto(SITE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)

        if "login" in page.url.lower() or "auth" in page.url.lower():
            print("[로그인] 브라우저에서 로그인해주세요 (최대 300초 대기)")
            try:
                await page.wait_for_url("**/metrics**", timeout=300000)
                await page.wait_for_timeout(5000)
            except Exception:
                print("[로그인] 시간 초과")
                await context.close()
                return

        # ============================================================
        # date-range-picker 구조 분석
        # ============================================================
        print("\n" + "=" * 60)
        print("[디버그] date-range-picker 세그먼트 구조 분석")
        print("=" * 60)

        # 1. date-range-picker 관련 모든 요소
        picker_info = await page.evaluate("""() => {
            const result = [];
            // date-range-picker 클래스가 포함된 모든 요소
            const els = document.querySelectorAll('[class*="date-range-picker"]');
            for (const el of els) {
                result.push({
                    tag: el.tagName,
                    className: el.className.toString().substring(0, 200),
                    text: el.textContent.trim().substring(0, 100),
                    childCount: el.children.length,
                    html: el.outerHTML.substring(0, 500),
                });
            }
            return result;
        }""")
        print(f"\n[1] date-range-picker 요소 {len(picker_info)}개:")
        for i, el in enumerate(picker_info):
            print(f"  [{i}] <{el['tag']}> class='{el['className'][:80]}'")
            print(f"       text='{el['text'][:60]}' children={el['childCount']}")
            print(f"       html: {el['html'][:300]}")
            print()

        # 2. Picker 내부의 세그먼트/입력 요소
        segment_info = await page.evaluate("""() => {
            const result = [];
            // data-slot="segment" 또는 input 요소들
            const selectors = [
                '[data-slot="segment"]',
                '[data-type]',
                'input[type="text"]',
                'input[type="number"]',
                '[contenteditable]',
                '[role="spinbutton"]',
                '[data-slot="input"]',
                '[class*="segment"]',
                '[class*="Segment"]',
                '[class*="date-field"]',
                '[class*="DateField"]',
                '[class*="date-input"]',
                '[class*="DateInput"]',
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    // date-range-picker 내부인지 확인
                    const inPicker = el.closest('[class*="date-range-picker"]');
                    result.push({
                        selector: sel,
                        tag: el.tagName,
                        className: el.className.toString().substring(0, 150),
                        text: el.textContent.trim().substring(0, 50),
                        value: el.value || '',
                        dataSlot: el.getAttribute('data-slot') || '',
                        dataType: el.getAttribute('data-type') || '',
                        role: el.getAttribute('role') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        ariaValueNow: el.getAttribute('aria-valuenow') || '',
                        ariaValueMin: el.getAttribute('aria-valuemin') || '',
                        ariaValueMax: el.getAttribute('aria-valuemax') || '',
                        tabindex: el.getAttribute('tabindex') || '',
                        inPicker: !!inPicker,
                        html: el.outerHTML.substring(0, 400),
                    });
                }
            }
            return result;
        }""")
        print(f"\n[2] 세그먼트/입력 요소 {len(segment_info)}개:")
        for i, el in enumerate(segment_info):
            print(f"  [{i}] selector='{el['selector']}' <{el['tag']}> inPicker={el['inPicker']}")
            print(f"       data-slot='{el['dataSlot']}' data-type='{el['dataType']}' role='{el['role']}'")
            print(f"       aria-label='{el['ariaLabel']}' aria-valuenow='{el['ariaValueNow']}'")
            print(f"       aria-valuemin='{el['ariaValueMin']}' aria-valuemax='{el['ariaValueMax']}'")
            print(f"       text='{el['text']}' value='{el['value']}' tabindex='{el['tabindex']}'")
            print(f"       class='{el['className'][:80]}'")
            print(f"       html: {el['html'][:250]}")
            print()

        # 3. date-range-picker__Picker 내부 구조 (날짜 표시 영역)
        picker_detail = await page.evaluate("""() => {
            const picker = document.querySelector('[class*="date-range-picker__Picker"]');
            if (!picker) return { found: false };
            return {
                found: true,
                tag: picker.tagName,
                className: picker.className.toString(),
                html: picker.outerHTML.substring(0, 2000),
                childrenHTML: Array.from(picker.children).map(c => ({
                    tag: c.tagName,
                    className: c.className.toString().substring(0, 100),
                    text: c.textContent.trim().substring(0, 50),
                    html: c.outerHTML.substring(0, 500),
                })),
            };
        }""")
        print(f"\n[3] date-range-picker__Picker 상세:")
        if picker_detail.get('found'):
            print(f"  class='{picker_detail['className'][:100]}'")
            print(f"  children: {len(picker_detail.get('childrenHTML', []))}개")
            for i, ch in enumerate(picker_detail.get('childrenHTML', [])):
                print(f"    [{i}] <{ch['tag']}> class='{ch['className'][:60]}' text='{ch['text'][:40]}'")
                print(f"         html: {ch['html'][:300]}")
                print()
            print(f"\n  전체 HTML:\n{picker_detail['html'][:1500]}")
        else:
            print("  date-range-picker__Picker 요소 없음")

        # 4. 달력 버튼 및 달력 팝업 관련
        calendar_info = await page.evaluate("""() => {
            const result = [];
            const sels = [
                'button[aria-label*="달력"]',
                'button[aria-label*="calendar"]',
                '[class*="calendar"]',
                '[class*="Calendar"]',
                '[role="dialog"]',
                '[role="grid"]',
            ];
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    result.push({
                        selector: sel,
                        tag: el.tagName,
                        className: el.className.toString().substring(0, 100),
                        ariaLabel: el.getAttribute('aria-label') || '',
                        text: el.textContent.trim().substring(0, 80),
                        html: el.outerHTML.substring(0, 400),
                    });
                }
            }
            return result;
        }""")
        print(f"\n[4] 달력/캘린더 관련 요소 {len(calendar_info)}개:")
        for i, el in enumerate(calendar_info):
            print(f"  [{i}] selector='{el['selector']}' <{el['tag']}>")
            print(f"       aria-label='{el['ariaLabel']}' class='{el['className'][:60]}'")
            print(f"       text='{el['text'][:60]}'")
            print(f"       html: {el['html'][:250]}")
            print()

        print(f"\n[종료] 5초 후 브라우저 닫기...")
        await page.wait_for_timeout(5000)
        await context.close()
        print("[종료] 완료!")


if __name__ == "__main__":
    asyncio.run(main())
