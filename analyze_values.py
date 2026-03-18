"""수집된 Superset 차트 데이터 — 탭별 지표+값 요약 테이블 출력

차트 제목 결정 우선순위:
1. JSON 내 _meta.slice_name (수집 스크립트에서 매핑)
2. _summary.json의 slice_name (URL slice_id → dashboard/charts 매핑)
3. 컬럼명으로 추론 (폴백)
"""

import json, os, sys, re, urllib.parse
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else "shucle_data/검단신도시/20260218_20260224"


def build_slice_map(data_dir):
    """데이터 디렉토리에서 slice_id → slice_name 매핑 구축.
    소스 1: 각 JSON의 _meta.slice_name
    소스 2: dashboard/charts API 응답 (result[].{id, slice_name})
    소스 3: _summary.json의 slice_name 필드
    """
    slice_map = {}

    # 모든 JSON 파일에서 dashboard/charts 응답 탐색
    for fname in os.listdir(data_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        result = data.get("result")
        if not isinstance(result, list):
            continue
        for item in result:
            if isinstance(item, dict) and "slice_name" in item and "id" in item:
                slice_map[item["id"]] = item["slice_name"]

    # _summary.json에서 추가 매핑
    summary_path = os.path.join(data_dir, "_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
            for entry in summary:
                sid = entry.get("slice_id")
                sname = entry.get("slice_name")
                if sid and sname and sid not in slice_map:
                    slice_map[sid] = sname
        except Exception:
            pass

    return slice_map


def build_file_slice_map(data_dir, slice_map):
    """파일명 → slice_name 매핑.
    소스 1: JSON 내 _meta
    소스 2: _summary.json URL에서 slice_id 추출 → slice_map 조회
    파일명 규칙: {tab}_{j:02d}.json (j = 탭 내 전체 응답의 인덱스)
    """
    file_map = {}  # fname → slice_name

    # summary에서 URL 기반 매핑
    # 수집 스크립트의 파일 저장 로직 재현:
    # 1) tab별로 그룹핑, 2) enumerate(responses)에서 j가 파일명 인덱스
    summary_path = os.path.join(data_dir, "_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)

            tab_responses = defaultdict(list)
            for entry in summary:
                tab_responses[entry.get("tab", "")].append(entry)

            for tab, responses in tab_responses.items():
                for j, entry in enumerate(responses):
                    has_data = entry.get("has_data", False)
                    size = entry.get("size", 0)
                    if not (has_data and size > 100):
                        continue

                    fname = f"{tab.replace(' ', '_')}_{j:02d}.json"
                    url = entry.get("url", "")

                    # URL에서 slice_id 추출
                    try:
                        parsed_url = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed_url.query)
                        if "form_data" in params:
                            fd = json.loads(params["form_data"][0])
                            sid = fd.get("slice_id")
                            if sid and sid in slice_map:
                                file_map[fname] = slice_map[sid]
                    except Exception:
                        pass
        except Exception:
            pass

    # 각 JSON 파일의 _meta에서 직접 읽기 (더 정확 — 오버라이드)
    for fname in os.listdir(data_dir):
        if not fname.endswith(".json") or fname.startswith("_") or fname.startswith("00"):
            continue
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "_meta" in data:
                meta = data["_meta"]
                sname = meta.get("slice_name")
                if sname:
                    file_map[fname] = sname
        except Exception:
            pass

    return file_map


def extract_charts(data):
    """Superset chart/data API JSON에서 차트 정보 추출"""
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, list) or not result:
        return None
    charts = []
    for item in result:
        if item.get("status") != "success":
            continue
        colnames = item.get("colnames", [])
        rows = item.get("data", [])
        if not rows:
            continue
        charts.append({"colnames": colnames, "data": rows, "rowcount": len(rows)})
    return charts if charts else None


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        if abs(v) >= 100:
            return f"{v:,.0f}"
        if abs(v) >= 1:
            return f"{v:,.1f}"
        return f"{v:.4f}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, str) and len(v) > 25:
        return v[:22] + "..."
    return str(v)


def ts_to_date(ts):
    """밀리초 타임스탬프 → 날짜 문자열"""
    if isinstance(ts, (int, float)) and ts > 1_000_000_000_000:
        import datetime
        dt = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc)
        return dt.strftime("%m/%d")
    return fmt(ts)


def summarize_chart(colnames, rows):
    """차트를 요약 문자열로 반환"""
    lines = []
    n = len(rows)

    # 1행짜리: 각 컬럼=값 나열
    if n <= 3:
        for row in rows:
            parts = []
            for c in colnames:
                v = row.get(c)
                if c == "__timestamp" or "timestamp" in c.lower() or "date" in c.lower():
                    parts.append(f"{ts_to_date(v)}")
                else:
                    parts.append(f"{c}={fmt(v)}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    # 다행: 핵심 컬럼 식별
    ts_col = None
    label_col = None
    val_cols = []
    for c in colnames:
        cl = c.lower()
        if "__timestamp" == c or "timestamp" in cl or "_date" in cl:
            ts_col = c
        elif any(k in cl for k in ["hour", "dow", "day", "holiday", "age", "group", "type", "gender",
                                     "driver", "session", "stop", "pick", "drop", "plate", "zone",
                                     "display_name", "caller"]):
            label_col = c if label_col is None else label_col
            if label_col != c:
                val_cols.append(c)
        else:
            val_cols.append(c)

    x_col = ts_col or label_col
    if not val_cols:
        val_cols = [c for c in colnames if c != x_col]

    if n <= 8:
        for row in rows:
            x_val = ts_to_date(row.get(x_col)) if x_col and (ts_col or "date" in (x_col or "").lower()) else fmt(row.get(x_col)) if x_col else ""
            vals = " | ".join(f"{fmt(row.get(c))}" for c in val_cols[:5])
            x_label = f"{x_val}: " if x_val else ""
            lines.append(f"  {x_label}{vals}")

        header = " | ".join(c[:15] for c in val_cols[:5])
        return f"[{header}]\n" + "\n".join(lines)
    else:
        def row_str(row):
            x_val = ts_to_date(row.get(x_col)) if x_col and (ts_col or "date" in (x_col or "").lower()) else fmt(row.get(x_col)) if x_col else ""
            vals = " | ".join(f"{fmt(row.get(c))}" for c in val_cols[:5])
            x_label = f"{x_val}: " if x_val else ""
            return f"  {x_label}{vals}"

        header = " | ".join(c[:15] for c in val_cols[:5])
        for row in rows[:3]:
            lines.append(row_str(row))
        lines.append(f"  ... ({n - 4}행 생략)")
        lines.append(row_str(rows[-1]))
        return f"[{header}]\n" + "\n".join(lines)


def main():
    data_dir = DATA_DIR

    # slice_id → slice_name 매핑
    slice_map = build_slice_map(data_dir)
    file_slice_map = build_file_slice_map(data_dir, slice_map)
    print(f"[매핑] slice_id {len(slice_map)}개, 파일→차트이름 {len(file_slice_map)}개")

    # 탭별 JSON 파일 분류
    tab_files = defaultdict(list)
    skip_prefixes = ("00_", "_")
    tab_order = ["초기로딩", "호출_탑승", "서비스_품질", "가호출_수요", "지역_회원", "정류장_이용", "차량_운행"]

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".json"):
            continue
        if any(fname.startswith(p) for p in skip_prefixes):
            continue
        parts = fname.rsplit("_", 1)
        tab_name = parts[0] if len(parts) == 2 else fname.replace(".json", "")
        tab_files[tab_name].append(fname)

    seen = set()
    chart_no = 0
    mapped_count = 0
    unmapped_count = 0

    for tab_name in tab_order:
        files = tab_files.get(tab_name, [])
        if not files:
            continue

        display = tab_name.replace("_", " ")
        if tab_name == "초기로딩":
            display = "호출 탑승 (초기로딩)"

        tab_charts = []

        for fname in files:
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            charts = extract_charts(data)
            if not charts:
                continue

            # 차트 제목 결정
            chart_title = file_slice_map.get(fname)

            for chart in charts:
                colnames = chart["colnames"]
                rows = chart["data"]
                h = str(colnames) + str(rows[:2])
                if h in seen:
                    continue
                seen.add(h)
                tab_charts.append((fname, colnames, rows, chart_title))

        if not tab_charts:
            continue

        print(f"\n{'=' * 100}")
        print(f"  [{display}]  차트 {len(tab_charts)}개")
        print(f"{'=' * 100}")

        for fname, colnames, rows, chart_title in tab_charts:
            chart_no += 1

            # 제목: slice_name 우선, 없으면 컬럼명 추론
            if chart_title:
                # ◼︎ 접두사 제거
                title = chart_title.lstrip("◼︎■ ").strip()
                mapped_count += 1
            else:
                # 폴백: 컬럼명으로 추론
                metric_names = [c for c in colnames
                               if c != "__timestamp"
                               and "timestamp" not in c.lower()
                               and "_date" not in c.lower()]
                title = ", ".join(metric_names[:4])
                if len(metric_names) > 4:
                    title += f" 외 {len(metric_names)-4}개"
                unmapped_count += 1

            print(f"\n  #{chart_no}  {title}  ({len(rows)}행)  [{fname}]")
            print(f"  {'-' * 90}")

            summary = summarize_chart(colnames, rows)
            for line in summary.split("\n"):
                print(f"  {line}")

    print(f"\n\n{'=' * 100}")
    print(f"  총 {chart_no}개 차트 출력 완료")
    print(f"  차트 이름 매핑 성공: {mapped_count}개 / 미매핑(컬럼명 추론): {unmapped_count}개")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
