"""
셔클 인사이트 탭별 전체 페이지 스크린샷 캡처 스크립트
====================================================
목적: 좌측 대분류 탭 → 소분류 탭별로 전체 페이지 스크롤 캡처
결과: shucle_screenshots/{대분류}/{소분류}.png

실행: python shucle_screenshot.py
사전: pip install playwright Pillow && playwright install chromium
"""

import asyncio, os, sys, io
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image

# stdout UTF-8 강제 설정 (Windows cp949 이모지 오류 방지)
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SITE_URL = "https://insight.shucle.com/metrics"
BROWSER_PROFILE = "./shucle_browser_profile"
SAVE_BASE = "shucle_screenshots"
LOGIN_TIMEOUT = 300

# ============================================================
# 좌측 대분류 탭 → 소분류 탭 매핑
# ============================================================
# 좌측 사이드바 대분류 탭 목록 (아이콘 + 텍스트 레이블)
LEFT_TABS = ["운행", "매출", "통계", "지역"]

# 소분류 탭은 해당 대분류 진입 후 상단에 나타나는 탭들
# 운행은 이미 확인됨, 나머지는 실행 시 자동 탐지
KNOWN_SUBTABS = {
    "운행": ["호출 탑승", "서비스 품질", "가호출 수요", "지역 회원", "정류장 이용", "차량 운행"],
}


async def wait_for_page_stable(page, timeout=15, stable_secs=3):
    """네트워크 안정화 대기"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        try:
            await page.wait_for_load_state("networkidle", timeout=stable_secs * 1000)
            return
        except Exception:
            pass
    await page.wait_for_timeout(2000)


def find_superset_frame(page):
    """Superset iframe 프레임 객체를 찾아 반환"""
    for frame in page.frames:
        if "superset" in frame.url:
            return frame
    return None


async def capture_full_page(page, save_path, scroll_step=700, overlap=100):
    """
    Superset iframe 내부를 스크롤하며 전체 페이지 캡처 후 합성.
    - document.documentElement 를 스크롤 대상으로 고정 (가장 안정적)
    - 메인 페이지 스크린샷을 찍되, iframe 내부 스크롤로 콘텐츠 이동
    """
    frame = find_superset_frame(page)
    if not frame:
        print("      [WARN] Superset iframe 없음 -- 메인 페이지 full_page 캡처")
        await page.screenshot(path=save_path, full_page=True)
        return

    # 1) iframe 내부: documentElement 상단으로 이동 + 크기 측정
    scroll_info = await frame.evaluate("""() => {
        const el = document.documentElement;
        el.scrollTop = 0;
        return {
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight,
        };
    }""")

    scroll_height = scroll_info["scrollHeight"]
    client_height = scroll_info["clientHeight"]
    print(f"      iframe 콘텐츠: {scroll_height}px (보이는 영역: {client_height}px)")

    # 2) 스크롤 불필요하면 단순 캡처
    if scroll_height <= client_height + 50:
        await page.screenshot(path=save_path, full_page=False)
        print(f"      -> 단일 캡처 저장")
        return

    # 3) iframe 내부를 스크롤하며 메인 페이지 스크린샷 반복 캡처
    screenshots = []
    positions = []
    effective_step = scroll_step - overlap
    current_y = 0
    stuck_count = 0  # 스크롤 멈춤 감지

    while current_y < scroll_height:
        # iframe documentElement 직접 스크롤
        actual_y = await frame.evaluate(f"""() => {{
            document.documentElement.scrollTop = {current_y};
            return document.documentElement.scrollTop;
        }}""")

        await page.wait_for_timeout(800)  # 렌더링 대기

        buf = await page.screenshot(full_page=False)
        img = Image.open(io.BytesIO(buf))
        screenshots.append(img)
        positions.append(actual_y)

        # 바닥 도달 체크
        if actual_y + client_height >= scroll_height - 5:
            break

        # 스크롤이 더 이상 안 움직이면 종료 (연속 2회 같은 위치)
        if len(positions) >= 2 and actual_y == positions[-2]:
            stuck_count += 1
            if stuck_count >= 2:
                print(f"      [WARN] 스크롤 멈춤 at {actual_y}px -- 중단")
                break
        else:
            stuck_count = 0

        current_y += effective_step

    if not screenshots:
        await page.screenshot(path=save_path, full_page=False)
        return

    if len(screenshots) == 1:
        screenshots[0].save(save_path)
        print(f"      -> 단일 캡처 저장")
        return

    # 4) 이미지 합성 — 첫 캡처는 전체(헤더 포함), 이후는 iframe 내 새 콘텐츠만

    # iframe의 화면 내 위치 파악
    iframe_rect = await page.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
            if (iframe.src && iframe.src.includes('superset')) {
                const rect = iframe.getBoundingClientRect();
                return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
            }
        }
        return null;
    }""")

    if iframe_rect:
        iframe_top = max(0, int(iframe_rect["top"]))
        iframe_height = int(iframe_rect["height"])
    else:
        iframe_top = 140
        iframe_height = screenshots[0].height - iframe_top

    # 첫 캡처: 전체 사용 (헤더 포함)
    crops = [screenshots[0]]

    for i in range(1, len(screenshots)):
        img = screenshots[i]
        prev_pos = positions[i - 1]
        curr_pos = positions[i]

        # iframe 내부 스크롤 이동량
        scroll_delta = curr_pos - prev_pos

        if scroll_delta <= 0:
            continue

        # iframe 영역 내에서 새로 보이는 부분만 crop
        # iframe 하단에서 scroll_delta 만큼이 새 콘텐츠
        new_content_top = iframe_top + iframe_height - scroll_delta
        if new_content_top < iframe_top:
            new_content_top = iframe_top

        cropped = img.crop((0, new_content_top, img.width, iframe_top + iframe_height))
        if cropped.height > 0:
            crops.append(cropped)

    # 합성 이미지 생성
    total_height = sum(c.height for c in crops)
    merged = Image.new("RGB", (crops[0].width, total_height))
    y_offset = 0
    for crop in crops:
        merged.paste(crop, (0, y_offset))
        y_offset += crop.height

    merged.save(save_path, quality=90)
    print(f"      -> {len(screenshots)}장 합성, {merged.width}x{merged.height}px")


async def find_left_tabs(page):
    """좌측 사이드바의 대분류 탭 목록을 자동 탐지"""
    # 좌측 사이드바 메뉴 항목 탐색
    tabs = await page.evaluate("""() => {
        const results = [];
        // nav, aside, sidebar 등에서 메뉴 항목 탐색
        const selectors = [
            'nav a', 'aside a',
            '[class*="sidebar"] a', '[class*="menu"] a', '[class*="nav"] a',
            '[class*="Sidebar"] a', '[class*="Menu"] a', '[class*="Nav"] a',
        ];
        const seen = new Set();
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const text = el.textContent?.trim();
                const href = el.getAttribute('href') || '';
                if (text && text.length < 20 && !seen.has(text) && href) {
                    seen.add(text);
                    results.push({ text, href });
                }
            }
        }
        return results;
    }""")
    return tabs


async def find_subtabs(page):
    """현재 페이지의 상단 소분류 탭 목록 자동 탐지"""
    # 기존 스크립트에서 알고 있는 탭 구조: 상단 탭 버튼들
    tabs = await page.evaluate("""() => {
        const results = [];
        // 탭 버튼/링크 탐색 (상단 영역)
        const selectors = [
            '[role="tab"]', '[role="tablist"] button', '[role="tablist"] a',
            '[class*="tab"] button', '[class*="Tab"] button',
            'button[data-slot="tab"]',
        ];
        const seen = new Set();
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const text = el.textContent?.trim();
                if (text && text.length < 20 && !seen.has(text)) {
                    seen.add(text);
                    const rect = el.getBoundingClientRect();
                    // 상단 200px 이내의 탭만
                    if (rect.top < 200 && rect.height > 0) {
                        results.push(text);
                    }
                }
            }
        }
        return results;
    }""")
    return tabs


async def select_region(page, region_keyword):
    """지역 선택 (shucle_api_probe.py에서 가져옴)"""
    print(f"  [지역] {region_keyword} 선택 중...")

    # 이미 선택된 지역 확인
    zone_buttons = page.locator('button[data-slot="trigger"][aria-haspopup="dialog"]')
    cnt = await zone_buttons.count()
    for idx in range(cnt):
        btn = zone_buttons.nth(idx)
        try:
            txt = await btn.inner_text(timeout=1000)
            if region_keyword in txt:
                print(f"  [지역] 이미 {region_keyword} 선택됨")
                return True
        except Exception:
            continue

    # 지역 드롭다운 열기
    zone_trigger = None
    triggers = page.locator('button[data-slot="trigger"][aria-haspopup="dialog"]')
    cnt = await triggers.count()
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
        print("  [지역] 드롭다운 버튼 못 찾음")
        return False

    await zone_trigger.click()
    await page.wait_for_timeout(2000)

    js_result = await page.evaluate("""(keyword) => {
        const allValues = document.querySelectorAll('div[class*="zone-select__Value"]');
        const values = [];
        for (const el of allValues) {
            const text = el.textContent?.trim() || '';
            const h = el.getBoundingClientRect().height;
            const style = window.getComputedStyle(el);
            if (h > 5 && style.display !== 'none' && text.length > 0 && text.length <= 30) {
                values.push({el, text});
            }
        }
        for (const v of values) {
            if (v.text.includes(keyword)) {
                v.el.click();
                return {success: true, text: v.text};
            }
        }
        const allOptions = document.querySelectorAll('div[class*="zone-select__Option"]');
        const options = [];
        for (const el of allOptions) {
            const text = el.textContent?.trim() || '';
            const h = el.getBoundingClientRect().height;
            if (h > 5 && h < 200 && text.length > 0 && text.length <= 50) {
                options.push({el, text});
            }
        }
        for (let i = 0; i < options.length; i++) {
            if (options[i].text.includes(keyword)) {
                if (i < values.length) {
                    values[i].el.click();
                    return {success: true, text: values[i].text};
                }
            }
        }
        return {success: false};
    }""", region_keyword)

    if js_result.get("success"):
        print(f"  [지역] '{js_result['text']}' 선택 완료")
        await page.wait_for_timeout(3000)
        return True
    else:
        await page.keyboard.press("Escape")
        print("  [지역] 선택 실패")
        return False


async def main():
    # 실행 설정
    print("\n[설정] 스크린샷 캡처 파라미터 입력")
    print("-" * 40)

    region = input("  지역 키워드 (예: 검단, 영덕, 봉양): ").strip()
    if not region:
        region = "검단"
        print(f"  -> 기본값: {region}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_root = os.path.join(SAVE_BASE, timestamp)
    os.makedirs(save_root, exist_ok=True)
    print(f"  저장 경로: {os.path.abspath(save_root)}")
    print("-" * 40)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE, headless=False,
            viewport={"width": 1920, "height": 1080}, slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # ============================================================
        # 사이트 접속
        # ============================================================
        print("\n[접속] 사이트 접속 중...")
        await page.goto(SITE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)

        # UI 요소 로딩 대기
        try:
            await page.wait_for_selector(
                'button[data-slot="trigger"][aria-haspopup="dialog"]',
                timeout=30000
            )
            await page.wait_for_timeout(2000)
        except Exception:
            print("[접속] 드롭다운 버튼 대기 타임아웃 -- 추가 대기 10초")
            await page.wait_for_timeout(10000)

        # ============================================================
        # 로그인 대기 (수동)
        # ============================================================
        if "login" in page.url.lower() or "auth" in page.url.lower():
            print(f"[로그인] 브라우저에서 로그인해주세요 (최대 {LOGIN_TIMEOUT}초 대기)")
            try:
                await page.wait_for_url("**/metrics**", timeout=LOGIN_TIMEOUT * 1000)
                await page.wait_for_timeout(5000)
                print("[로그인] 로그인 완료!")
            except Exception:
                print("[로그인] 시간 초과 -- 종료합니다")
                await context.close()
                return
        else:
            print("[로그인] 이미 로그인 상태")

        # ============================================================
        # 지역 선택
        # ============================================================
        await select_region(page, region)
        await page.wait_for_timeout(3000)

        # ============================================================
        # 좌측 대분류 탭 순회 (LEFT_TABS 기반)
        # ============================================================
        print(f"\n[탐색] 좌측 대분류 탭: {LEFT_TABS}")

        total_captured = 0

        for main_idx, main_name in enumerate(LEFT_TABS):
            main_dir = os.path.join(save_root, main_name)
            os.makedirs(main_dir, exist_ok=True)

            print(f"\n{'='*60}")
            print(f"[{main_idx+1}/{len(LEFT_TABS)}] 대분류: {main_name}")
            print(f"{'='*60}")

            # 좌측 사이드바에서 대분류 탭 클릭 (navigation__Menu 버튼)
            if main_idx > 0:
                clicked_main = False
                try:
                    # navigation__Menu 클래스의 button 중 텍스트 매칭
                    result = await page.evaluate("""(tabName) => {
                        const buttons = document.querySelectorAll('button[class*="navigation__Menu"]');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim();
                            if (text && text === tabName) {
                                btn.click();
                                return { success: true, text: text };
                            }
                        }
                        return { success: false };
                    }""", main_name)

                    if result.get("success"):
                        print(f"  [OK] 좌측 메뉴 '{result['text']}' 클릭")
                        clicked_main = True
                        await page.wait_for_timeout(5000)
                        await wait_for_page_stable(page)
                except Exception as e:
                    print(f"  [WARN] JS 클릭 실패: {e}")

                if not clicked_main:
                    print(f"  [FAIL] 대분류 탭 '{main_name}' 클릭 실패 -- 스킵")
                    continue

                # 지역 재선택 (대분류 이동 시 초기화될 수 있음)
                await page.wait_for_timeout(2000)
                try:
                    await page.wait_for_selector(
                        'button[data-slot="trigger"][aria-haspopup="dialog"]',
                        timeout=10000
                    )
                    await select_region(page, region)
                    await page.wait_for_timeout(3000)
                except Exception:
                    pass

            # 소분류 탭 탐지
            if main_name in KNOWN_SUBTABS:
                subtabs = KNOWN_SUBTABS[main_name]
                print(f"  소분류 탭 (기존 매핑): {subtabs}")
            else:
                # 상단 소분류 탭 자동 탐지
                subtabs = await find_subtabs(page)
                if not subtabs:
                    # 탭이 없으면 현재 페이지 자체를 캡처
                    subtabs = [main_name]
                print(f"  소분류 탭 (자동 탐지): {subtabs}")

            # 각 소분류 탭 캡처
            for sub_idx, sub_name in enumerate(subtabs):
                print(f"\n  [{sub_idx+1}/{len(subtabs)}] {main_name} > {sub_name}")

                # 소분류 탭 클릭
                if sub_name != main_name:  # 대분류와 동일하면 현재 페이지 그대로
                    try:
                        tab_el = page.get_by_text(sub_name, exact=True).first
                        await tab_el.click()
                        await page.wait_for_timeout(5000)
                    except Exception as e:
                        print(f"    [FAIL] 탭 클릭 실패: {e}")
                        continue

                # 차트 데이터 로딩 대기
                await wait_for_page_stable(page, timeout=15, stable_secs=5)

                # iframe 내부 스크롤로 lazy-load 트리거
                print(f"    iframe 내부 스크롤하며 lazy-load 트리거...")
                frame = find_superset_frame(page)
                if frame:
                    # 1차 스크롤: 하단까지 (documentElement 직접 사용)
                    for step in range(8):
                        await frame.evaluate("document.documentElement.scrollTop += 800")
                        await page.wait_for_timeout(1500)

                    # 상단 복귀
                    await frame.evaluate("document.documentElement.scrollTop = 0")
                    await page.wait_for_timeout(2000)

                    # 2차 스크롤: 다시 하단까지 (2차 lazy-load)
                    for step in range(8):
                        await frame.evaluate("document.documentElement.scrollTop += 800")
                        await page.wait_for_timeout(1500)

                    # 상단 복귀 (캡처 시작 전)
                    await frame.evaluate("document.documentElement.scrollTop = 0")
                    await page.wait_for_timeout(2000)
                else:
                    # iframe 없으면 메인 페이지 스크롤
                    for _ in range(5):
                        await page.mouse.wheel(0, 800)
                        await page.wait_for_timeout(1500)
                    await page.mouse.wheel(0, -5000)
                    await page.wait_for_timeout(2000)

                # 모든 차트 로딩 대기
                await wait_for_page_stable(page, timeout=10, stable_secs=3)

                # 전체 페이지 캡처
                safe_name = sub_name.replace(" ", "_").replace("/", "_")
                save_path = os.path.join(main_dir, f"{sub_idx+1:02d}_{safe_name}.png")

                print(f"    캡처 중...")
                await capture_full_page(page, save_path)
                total_captured += 1
                print(f"    -> 저장: {save_path}")

        # ============================================================
        # 완료
        # ============================================================
        print(f"\n\n{'='*60}")
        print(f"[완료] 총 {total_captured}개 스크린샷 캡처 완료")
        print(f"  저장 경로: {os.path.abspath(save_root)}")
        print(f"{'='*60}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
