import pandas as pd
import numpy as np

def update_lotto_excel(file_path, output_path=None):
    # 1. 엑셀 파일 불러오기()
    print(f"'{file_path}' 파일을 읽어오는 중입니다...")
    df = pd.read_excel(file_path)

    # ── 회차 컬럼명 자동 탐지 ──────────────────────────────
    # 엑셀 저장 과정에서 '회차' 대신 숫자(예: 3)로 저장될 수 있으므로
    # 첫 번째 컬럼을 무조건 '회차'로 인식하도록 처리합니다.
    first_col = df.columns[0]
    if first_col != '회차':
        print(f"  [알림] 첫 번째 컬럼명이 '{first_col}'으로 되어 있어 '회차'로 변경합니다.")
        df = df.rename(columns={first_col: '회차'})

    # 번호 컬럼 확인
    num_cols = ['번호1', '번호2', '번호3', '번호4', '번호5', '번호6']
    if not all(col in df.columns for col in num_cols):
        print("오류: 엑셀 파일에 '번호1'~'번호6' 컬럼이 없습니다. 파일을 확인해주세요.")
        return

    # 2. 계산을 위해 과거 회차부터 순서대로 정렬 (오름차순)
    df = df.sort_values(by='회차', ascending=True).reset_index(drop=True)

    # 3. 기본 통계 칼럼 계산
    print("기본 통계 칼럼(번호합, 앞수합, 뒷수합, 첫수합, 끝수합)을 계산합니다...")

    df['번호합'] = df[num_cols].sum(axis=1)
    df['앞수합'] = df[['번호1', '번호2', '번호3']].sum(axis=1)
    df['뒷수합'] = df[['번호4', '번호5', '번호6']].sum(axis=1)

    def get_tens(num): return num // 10
    def get_ones(num): return num % 10

    df['첫수합'] = df[num_cols].map(get_tens).sum(axis=1)
    df['끝수합'] = df[num_cols].map(get_ones).sum(axis=1)

    # 4. 해당 회차 당첨 번호 반영 후 '연속 미발생 번호 Top 10' 계산
    print("회차별 당첨 반영 기준 '연속 미발생 번호 Top 10'을 계산합니다...")

    missing_counts = {i: 0 for i in range(1, 46)}
    top10_list = []

    for idx, row in df.iterrows():
        # [1] 현재 회차 당첨 번호 반영 (출현한 번호는 0으로 리셋, 미출현은 +1)
        current_numbers = set(row[num_cols].dropna().astype(int))
        for i in range(1, 45 + 1):
            if i in current_numbers:
                missing_counts[i] = 0
            else:
                missing_counts[i] += 1

        # [2] 당첨 번호 반영 후 기준 Top 10 추출
        # (미발생 회수가 높은 순, 회수가 같으면 번호 오름차순)
        sorted_missing = sorted(missing_counts.items(), key=lambda x: (-x[1], x[0]))
        top10_nums = [num for num, count in sorted_missing[:10]]

        # 문자열 형태로 저장
        top10_list.append(", ".join(map(str, top10_nums)))

    df['연속미발생_Top10'] = top10_list

    # 5. 원래의 정렬 순서(최신 회차가 위로 오도록)로 재정렬
    df = df.sort_values(by='회차', ascending=False).reset_index(drop=True)

    # 6. 결과 저장
    import sys
    save_path = output_path if output_path else file_path
    try:
        df.to_excel(save_path, index=False)
        print(f"[완료] 성공적으로 칼럼이 추가되었습니다! 저장 완료: {save_path}")
    except PermissionError:
        print()
        print("=" * 50)
        print("[오류] 파일 저장 실패!")
        print(f"  '{save_path}' 파일이 현재 Excel에서 열려 있습니다.")
        print("  Excel을 닫은 후 다시 실행해 주세요.")
        print("=" * 50)
        sys.exit(1)

# 실행 코드
if __name__ == "__main__":
    input_file = "lotto_data.xlsx"
    update_lotto_excel(input_file)