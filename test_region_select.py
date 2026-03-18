"""지역 선택 테스트 — Options 주소에서 키워드 매칭 → 대응 Value 클릭"""

import asyncio, sys
from playwright.async_api import async_playwright

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SITE_URL = "https://insight.shucle.com/metrics"
BROWSER_PROFILE = "./shucle_browser_profile"

TEST_CASES = [
    ("영천", "신녕"),
    ("인천", "검단"),
    ("음성", "충북혁신"),
    ("충북", "충북혁신"),
]


async def get_current_region(page):
    triggers = page.locator('button[data-slot="trigger"][aria-haspopup="dialog"]')
    cnt = await triggers.count()
    for idx in range(cnt):
        btn = triggers.nth(idx)
        try:
            txt = await btn.inner_text(timeout=2000)
        except Exception:
            continue
        if "DRT" not in txt and "전체 유형" not in txt and "달력" not in txt and txt.strip():
            return txt.strip().replace("\n", " ")
    return "(unknown)"


async def try_select_region(page, keyword):
    before = await get_current_region(page)
    print(f"   선택 전: '{before}'")

    # 드롭다운 열기
    triggers = page.locator('button[data-slot="trigger"][aria-haspopup="dialog"]')
    cnt = await triggers.count()
    zone_trigger = None
    for idx in range(cnt):
        btn = triggers.nth(idx)
        try:
            txt = await btn.inner_text(timeout=2000)
        except Exception:
            continue
        if "DRT" not in txt and "전체 유형" not in txt and "달력" not in txt and txt.strip():
            zone_trigger = btn
            break
    if not zone_trigger:
        print("   [FAIL] 드롭다운 버튼 못 찾음")
        return None

    await zone_trigger.click()
    await page.wait_for_timeout(2000)

    # Options(전체주소) 에서 키워드 매칭 → 대응 Values(표시명) 클릭
    js_result = await page.evaluate("""(keyword) => {
        // Options: zone-select__Option — 첫 번째는 컨테이너(전체 주소 합쳐진 것), 나머지가 개별
        const allOptions = document.querySelectorAll('div[class*="zone-select__Option"]');
        const options = [];
        for (const el of allOptions) {
            const text = el.textContent?.trim() || '';
            const h = el.getBoundingClientRect().height;
            // 개별 옵션만 (컨테이너=높이 200+ 제외)
            if (h > 5 && h < 200 && text.length > 0 && text.length <= 50) {
                options.push({el, text, h});
            }
        }

        // Values: zone-select__Value — 표시명
        const allValues = document.querySelectorAll('div[class*="zone-select__Value"]');
        const values = [];
        for (const el of allValues) {
            const text = el.textContent?.trim() || '';
            const h = el.getBoundingClientRect().height;
            const style = window.getComputedStyle(el);
            const visible = h > 5 && style.display !== 'none';
            if (visible && text.length > 0 && text.length <= 30) {
                values.push({el, text, h});
            }
        }

        const debug = {
            optionCount: options.length,
            valueCount: values.length,
            options: options.map(o => o.text),
            values: values.map(v => v.text),
        };

        // Options에서 키워드 포함하는 것 찾기
        let matchIdx = -1;
        for (let i = 0; i < options.length; i++) {
            if (options[i].text.includes(keyword)) {
                matchIdx = i;
                break;
            }
        }

        if (matchIdx < 0) {
            return {success: false, reason: 'no option contains keyword', debug};
        }

        debug.matchedOption = options[matchIdx].text;
        debug.matchIdx = matchIdx;

        // 대응 Value 클릭 (같은 인덱스)
        if (matchIdx < values.length) {
            const targetValue = values[matchIdx];
            targetValue.el.click();
            return {success: true, text: targetValue.text, method: 'index-match', debug};
        }

        // 인덱스 대응 실패 시, Option 텍스트에서 Value 텍스트를 매칭
        const optText = options[matchIdx].text;
        for (const v of values) {
            if (optText.endsWith(v.text)) {
                v.el.click();
                return {success: true, text: v.text, method: 'suffix-match', debug};
            }
        }

        return {success: false, reason: 'no matching value', debug};
    }""", keyword)

    debug = js_result.get('debug', {})
    print(f"   Options({debug.get('optionCount')}): {debug.get('options', [])}")
    print(f"   Values({debug.get('valueCount')}): {debug.get('values', [])}")

    if js_result.get("success"):
        print(f"   매칭: '{debug.get('matchedOption')}' [idx={debug.get('matchIdx')}]")
        print(f"   클릭: '{js_result['text']}' ({js_result['method']})")
    else:
        print(f"   [FAIL] {js_result.get('reason')}")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)
        return None

    await page.wait_for_timeout(3000)
    after = await get_current_region(page)
    print(f"   선택 후: '{after}'")
    return after


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE, headless=False,
            viewport={"width": 1920, "height": 1080}, slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("[접속] 사이트 접속 중...")
        await page.goto(SITE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)

        if "login" in page.url.lower() or "auth" in page.url.lower():
            print("[로그인] 로그인해주세요 (최대 300초)")
            try:
                await page.wait_for_url("**/metrics**", timeout=300000)
                await page.wait_for_timeout(5000)
            except Exception:
                print("[로그인] 시간 초과")
                await context.close()
                return

        try:
            await page.wait_for_selector(
                'button[data-slot="trigger"][aria-haspopup="dialog"]',
                timeout=30000
            )
            await page.wait_for_timeout(2000)
        except Exception:
            print("[접속] 드롭다운 버튼 대기 타임아웃")
            await page.wait_for_timeout(10000)

        results = []
        for keyword, expected in TEST_CASES:
            print(f"\n{'='*60}")
            print(f"[TEST] '{keyword}' -> 기대: '{expected}' 포함")
            print(f"{'='*60}")
            after = await try_select_region(page, keyword)
            ok = after is not None and expected in after
            status = "PASS" if ok else "FAIL"
            results.append((keyword, expected, after, status))
            print(f"   => [{status}]")
            await page.wait_for_timeout(1000)

        print(f"\n{'='*60}")
        print("[결과 요약]")
        for keyword, expected, after, status in results:
            print(f"  [{status}] '{keyword}' -> '{after}' (기대: '{expected}' 포함)")
        print(f"{'='*60}")

        print("\n[완료] 5초 후 브라우저 닫기")
        await page.wait_for_timeout(5000)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
