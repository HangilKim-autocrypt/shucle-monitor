"""수집된 Superset 차트 데이터 분석 — 탭별 지표/값 테이블 출력"""

import json, os, sys, re
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else "shucle_data/검단신도시/20260201_20260220"


def extract_chart_info(data):
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
        query_sql = item.get("query", "")
        colnames = item.get("colnames", [])
        rows = item.get("data", [])
        rowcount = item.get("rowcount", 0)

        if not rows:
            continue

        # SQL에서 테이블 이름 추출 (FROM ... _silver 패턴)
        table_match = re.search(r'from\s+(\w+_silver)', query_sql, re.IGNORECASE)
        source_table = table_match.group(1) if table_match else ""

        # SQL에서 AS alias 추출하여 지표명 파악
        alias_matches = re.findall(r'AS\s+"([^"]+)"', query_sql)

        charts.append({
            "colnames": colnames,
            "data": rows,
            "rowcount": rowcount,
            "source_table": source_table,
            "aliases": alias_matches,
        })

    return charts if charts else None


def format_val(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        if abs(v) >= 1:
            return f"{v:,.1f}"
        return f"{v:.4f}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, str) and len(v) > 30:
        return v[:27] + "..."
    return str(v)


def print_table(colnames, rows, max_rows=10):
    """간단한 테이블 출력"""
    # 컬럼 폭 계산
    widths = {}
    for col in colnames:
        widths[col] = max(len(col), 6)
    for row in rows[:max_rows]:
        for col in colnames:
            val_str = format_val(row.get(col))
            widths[col] = max(widths.get(col, 0), len(val_str))

    # 헤더
    header = " | ".join(col.ljust(widths[col])[:40] for col in colnames)
    sep = "-+-".join("-" * min(widths[col], 40) for col in colnames)
    print(f"    {header}")
    print(f"    {sep}")

    # 데이터
    for i, row in enumerate(rows[:max_rows]):
        vals = " | ".join(format_val(row.get(col)).ljust(widths[col])[:40] for col in colnames)
        print(f"    {vals}")

    if len(rows) > max_rows:
        print(f"    ... ({len(rows) - max_rows}행 더 있음)")


def analyze(data_dir):
    print(f"\n{'=' * 80}")
    print(f"  검단신도시 수집 데이터 분석")
    print(f"  경로: {data_dir}")
    print(f"{'=' * 80}")

    # 탭별 JSON 파일 분류
    tab_files = defaultdict(list)
    skip_prefixes = ("00_", "_summary")
    tab_order = ["초기로딩", "호출_탑승", "서비스_품질", "가호출_수요", "지역_회원", "정류장_이용", "차량_운행"]

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".json"):
            continue
        if any(fname.startswith(p) for p in skip_prefixes):
            continue
        # 탭명 추출: "초기로딩_08.json" → "초기로딩"
        parts = fname.rsplit("_", 1)
        tab_name = parts[0] if len(parts) == 2 else fname.replace(".json", "")
        tab_files[tab_name].append(fname)

    # 초기로딩은 호출 탑승 탭의 데이터 (대시보드 88)
    # 실제 탭별 차트 데이터 추출
    seen_data_hashes = set()  # 중복 방지

    for tab_name in tab_order:
        files = tab_files.get(tab_name, [])
        if not files:
            continue

        display_name = tab_name.replace("_", " ")
        if tab_name == "초기로딩":
            display_name = "호출 탑승 (초기로딩)"

        chart_count = 0
        charts_output = []

        for fname in files:
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            charts = extract_chart_info(data)
            if not charts:
                continue

            for chart in charts:
                colnames = chart["colnames"]
                rows = chart["data"]

                # 중복 체크 (같은 컬럼 + 같은 데이터)
                data_hash = str(colnames) + str(rows[:2])
                if data_hash in seen_data_hashes:
                    continue
                seen_data_hashes.add(data_hash)

                chart_count += 1
                charts_output.append((fname, chart))

        if not charts_output:
            continue

        print(f"\n\n{'─' * 80}")
        print(f"  [{display_name}]  차트 {len(charts_output)}개")
        print(f"{'─' * 80}")

        for fname, chart in charts_output:
            colnames = chart["colnames"]
            rows = chart["data"]
            src = chart["source_table"]

            src_label = f"  (source: {src})" if src else ""
            print(f"\n  >> {fname}{src_label}  [{len(rows)}행]")
            print_table(colnames, rows)

    # 요약 통계
    print(f"\n\n{'=' * 80}")
    print(f"  요약")
    print(f"{'=' * 80}")
    total_files = sum(len(v) for v in tab_files.values())
    print(f"  전체 JSON 파일: {total_files}개")
    for tab in tab_order:
        cnt = len(tab_files.get(tab, []))
        if cnt:
            print(f"    {tab.replace('_', ' ')}: {cnt}개")


if __name__ == "__main__":
    analyze(DATA_DIR)
