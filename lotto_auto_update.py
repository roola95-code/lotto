"""
lotto_auto_update.py
─────────────────────────────────────────────
동행복권 API를 이용해 최신 로또 당첨번호를 자동으로 가져와
lotto_data.xlsx 에 없는 회차를 자동 추가합니다.

사용법:
    python lotto_auto_update.py           # 최신 1회차만 추가
    python lotto_auto_update.py --all     # 엑셀에 없는 전체 회차 모두 추가
"""

import sys
import time
import argparse
import requests
import pandas as pd

# ── 설정 ────────────────────────────────────────────
EXCEL_FILE = "lotto_data.xlsx"
API_URL    = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer"   : "https://www.dhlottery.co.kr/"
}
REQUEST_DELAY = 0.5   # 연속 요청 시 서버 과부하 방지 (초)
MAX_ROUND     = 1400  # 탐색 상한 (충분히 큰 값)


def fetch_lotto(drw_no: int) -> dict | None:
    """
    동행복권 API에서 특정 회차 당첨 정보를 가져옵니다.
    성공 시 dict 반환, 실패 또는 미발표 회차는 None 반환.
    """
    try:
        params = {"srchLtEpsd": drw_no, "_": int(time.time() * 1000)}
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        lst = data.get("data", {}).get("list", [])
        if not lst:
            return None
        d = lst[0]
        # 당첨번호가 없는 미래 회차는 건너뜀
        if not d.get("tm1WnNo"):
            return None
        return {
            "회차"  : int(d["ltEpsd"]),
            "번호1" : int(d["tm1WnNo"]),
            "번호2" : int(d["tm2WnNo"]),
            "번호3" : int(d["tm3WnNo"]),
            "번호4" : int(d["tm4WnNo"]),
            "번호5" : int(d["tm5WnNo"]),
            "번호6" : int(d["tm6WnNo"]),
            "보너스": int(d["bnsWnNo"]),
            "추첨일": str(d["ltRflYmd"]),           # YYYYMMDD
            "1등당첨금": int(d.get("rnk1WnAmt", 0)),
            "1등당첨인원": int(d.get("rnk1WnNope", 0)),
        }
    except Exception as e:
        print(f"  [경고] {drw_no}회 조회 실패: {e}")
        return None


def get_latest_round(start_from: int = 1) -> int:
    """
    현재 발표된 가장 최신 회차 번호를 탐색합니다.
    start_from: 엑셀의 현재 최대 회차 (여기서부터 앞으로 탐색하면 빠름)
    """
    print("최신 회차를 탐색하는 중...", end=" ", flush=True)
    latest_valid = start_from
    # start_from 부터 최대 52회차 앞까지 순방향 탐색 (1년치 여유)
    for drw in range(start_from, start_from + 52):
        result = fetch_lotto(drw)
        if result:
            latest_valid = drw
        else:
            break  # 데이터 없으면 이전이 최신
        time.sleep(0.2)
    print(f"{latest_valid}회 발견!")
    return latest_valid


def load_excel() -> pd.DataFrame:
    """엑셀 파일을 읽어 DataFrame 으로 반환합니다. 없으면 빈 DF 반환."""
    try:
        df = pd.read_excel(EXCEL_FILE)
        # 첫 컬럼명 자동 보정 (저장 과정에서 깨질 수 있음)
        first_col = df.columns[0]
        if first_col != "회차":
            df = df.rename(columns={first_col: "회차"})
        return df
    except FileNotFoundError:
        print(f"[알림] '{EXCEL_FILE}' 파일이 없어 새로 생성합니다.")
        return pd.DataFrame()


def save_excel(df: pd.DataFrame):
    """DataFrame 을 엑셀로 저장합니다. 파일 잠금 시 오류 메시지 출력."""
    try:
        df.to_excel(EXCEL_FILE, index=False)
        print(f"[저장 완료] {EXCEL_FILE}")
    except PermissionError:
        print()
        print("=" * 50)
        print("[오류] 파일 저장 실패!")
        print(f"  '{EXCEL_FILE}' 이 Excel에서 열려 있습니다.")
        print("  Excel 을 닫은 후 다시 실행해 주세요.")
        print("=" * 50)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="로또 당첨번호 자동 업데이트")
    parser.add_argument("--all", action="store_true",
                        help="엑셀에 없는 모든 회차를 가져옵니다 (전체 업데이트)")
    args = parser.parse_args()

    print("=" * 50)
    print("  로또 당첨번호 자동 업데이트 (동행복권 API)")
    print("=" * 50)

    # ── 기존 엑셀 로드 ──
    df = load_excel()
    existing_rounds = set(df["회차"].astype(int).tolist()) if not df.empty else set()
    print(f"현재 엑셀에 저장된 회차: {len(existing_rounds)}개 "
          f"({'없음' if not existing_rounds else f'{max(existing_rounds)}회까지'})")

    # ── 최신 회차 확인 ──
    start = max(existing_rounds) if existing_rounds else 1
    latest = get_latest_round(start_from=start)
    missing = [r for r in range(1, latest + 1) if r not in existing_rounds]

    if not missing:
        print(f"이미 최신 상태입니다! (최신: {latest}회)")
        return

    # ── 가져올 회차 결정 ──
    if args.all:
        to_fetch = missing
        print(f"전체 업데이트 모드: {len(to_fetch)}개 회차를 가져옵니다.")
    else:
        # 기본: 최신 회차만
        to_fetch = [latest] if latest not in existing_rounds else missing[-1:]
        if not to_fetch:
            print(f"이미 최신 상태입니다! (최신: {latest}회)")
            return
        print(f"최신 회차만 업데이트: {to_fetch}회")

    # ── API 호출 및 데이터 수집 ──
    new_rows = []
    for i, drw in enumerate(to_fetch):
        result = fetch_lotto(drw)
        if result:
            new_rows.append(result)
            print(f"  [{i+1}/{len(to_fetch)}] {drw}회 ({result['추첨일']}): "
                  f"{result['번호1']}, {result['번호2']}, {result['번호3']}, "
                  f"{result['번호4']}, {result['번호5']}, {result['번호6']} "
                  f"+ 보너스 {result['보너스']}")
        if i < len(to_fetch) - 1:
            time.sleep(REQUEST_DELAY)

    if not new_rows:
        print("가져온 데이터가 없습니다.")
        return

    # ── 엑셀에 병합 ──
    new_df = pd.DataFrame(new_rows)

    # 기존 DF와 합치고 회차 기준 내림차순 정렬 (최신이 맨 위)
    if df.empty:
        merged = new_df
    else:
        # 기존 컬럼 중 번호1~6, 회차만 유지하고 병합
        common_cols = ["회차", "번호1", "번호2", "번호3", "번호4", "번호5", "번호6", "보너스", "추첨일"]
        # 기존 DF에 없는 새 컬럼은 추가
        for col in common_cols:
            if col not in df.columns:
                df[col] = None
        merged = pd.concat([df, new_df], ignore_index=True)
        # 중복 회차 제거 (새 데이터 우선)
        merged = merged.drop_duplicates(subset=["회차"], keep="last")

    merged = merged.sort_values(by="회차", ascending=False).reset_index(drop=True)

    save_excel(merged)
    print()
    print(f"총 {len(new_rows)}개 회차 추가 완료!")
    print(f"엑셀 총 회차 수: {len(merged)}개")


if __name__ == "__main__":
    main()
