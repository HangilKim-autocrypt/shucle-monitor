"""지역 선택 드롭다운 UI 구조 확인용 디버그 스크립트"""

import asyncio, sys, json
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SITE_URL = "https://insight.shucle.com/metrics"
BROWSER_PROFILE = "./shucle_browser_profile"
PROBE_DIR = "shucle_data/api_probe"


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
        # 상단 헤더 영역 HTML 구조 확인
        # ============================================================
        print("\n" + "=" * 60)
        print("[디버그] 상단 헤더 영역 HTML 구조 분석")
        print("=" * 60)

        # 1. 페이지 상단 영역 전체 HTML 출력
        header_html = await page.evaluate("""() => {
            // 상단 100px 영역의 모든 요소
            const els = document.querySelectorAll('header, nav, [class*="header"], [class*="nav"], [class*="toolbar"], [class*="top"]');
            let result = [];
            els.forEach(el => {
                result.push({
                    tag: el.tagName,
                    class: el.className,
                    id: el.id,
                    html: el.outerHTML.substring(0, 500)
                });
            });
            return result;
        }""")
        print(f"\n[1] 헤더/네비 요소 {len(header_html)}개:")
        for i, el in enumerate(header_html[:10]):
            print(f"  [{i}] <{el['tag']}> class='{el['class']}' id='{el['id']}'")
            print(f"       {el['html'][:200]}")

        # 2. 영덕 또는 지역 관련 텍스트가 있는 요소 찾기
        region_elements = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            let result = [];
            for (const el of all) {
                const text = el.textContent?.trim() || '';
                if (text.length < 50 && (text.includes('영덕') || text.includes('검단') || text.includes('DRT'))) {
                    result.push({
                        tag: el.tagName,
                        class: el.className?.toString() || '',
                        id: el.id || '',
                        text: text.substring(0, 100),
                        html: el.outerHTML?.substring(0, 300) || '',
                        clickable: el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button' || el.style?.cursor === 'pointer',
                        parentTag: el.parentElement?.tagName || '',
                        parentClass: el.parentElement?.className?.toString()?.substring(0, 100) || '',
                    });
                }
            }
            return result;
        }""")
        print(f"\n[2] 영덕/검단/DRT 관련 요소 {len(region_elements)}개:")
        for i, el in enumerate(region_elements):
            print(f"  [{i}] <{el['tag']}> text='{el['text']}' class='{el['class'][:60]}'")
            print(f"       clickable={el['clickable']} parent=<{el['parentTag']}> parentClass='{el['parentClass'][:60]}'")
            print(f"       html: {el['html'][:200]}")
            print()

        # 3. 드롭다운/셀렉트 요소 찾기
        dropdowns = await page.evaluate("""() => {
            const sels = [
                'select', '[class*="dropdown"]', '[class*="select"]',
                '[role="combobox"]', '[role="listbox"]', '[class*="menu"]',
                '[class*="picker"]', 'button[aria-haspopup]'
            ];
            let result = [];
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    result.push({
                        selector: sel,
                        tag: el.tagName,
                        class: el.className?.toString()?.substring(0, 100) || '',
                        text: el.textContent?.trim()?.substring(0, 100) || '',
                        html: el.outerHTML?.substring(0, 400) || '',
                    });
                });
            }
            return result;
        }""")
        print(f"\n[3] 드롭다운/셀렉트 요소 {len(dropdowns)}개:")
        for i, el in enumerate(dropdowns):
            print(f"  [{i}] selector='{el['selector']}' <{el['tag']}> text='{el['text'][:60]}'")
            print(f"       class='{el['class'][:80]}'")
            print(f"       html: {el['html'][:250]}")
            print()

        # 4. 상단 영역 클릭 가능 요소 중 지역 관련
        print(f"\n[4] 지역 드롭다운 클릭 테스트:")

        # 영덕 텍스트가 포함된 요소 클릭 시도
        try:
            region_btn = page.locator('text=/영덕/').first
            if await region_btn.is_visible(timeout=3000):
                bbox = await region_btn.bounding_box()
                print(f"   '영덕' 요소 위치: {bbox}")
                await region_btn.click()
                await page.wait_for_timeout(2000)

                # 클릭 후 나타난 옵션 목록 확인
                options_after = await page.evaluate("""() => {
                    const all = document.querySelectorAll('*');
                    let result = [];
                    for (const el of all) {
                        const text = el.textContent?.trim() || '';
                        const style = window.getComputedStyle(el);
                        const isVisible = style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0;
                        if (isVisible && text.length < 30 && text.includes('검단')) {
                            result.push({
                                tag: el.tagName,
                                class: el.className?.toString()?.substring(0, 100) || '',
                                text: text,
                                html: el.outerHTML?.substring(0, 300) || '',
                            });
                        }
                    }
                    return result;
                }""")
                print(f"   클릭 후 '검단' 옵션 {len(options_after)}개 발견:")
                for opt in options_after:
                    print(f"     <{opt['tag']}> text='{opt['text']}' class='{opt['class'][:60]}'")
                    print(f"     html: {opt['html'][:200]}")

                # 드롭다운 전체 스크린샷
                await page.screenshot(path=f"{PROBE_DIR}/debug_dropdown_open.png")
                print(f"   [스크린샷] {PROBE_DIR}/debug_dropdown_open.png")

                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"   영덕 요소 클릭 실패: {e}")

        print(f"\n[종료] 5초 후 브라우저 닫기...")
        await page.wait_for_timeout(5000)
        await context.close()
        print("[종료] 완료!")


if __name__ == "__main__":
    asyncio.run(main())
