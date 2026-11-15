import openpyxl
from openpyxl.styles import PatternFill

# 엑셀 파일 로드
print("'lotto_data.xlsx' 파일을 읽어오는 중입니다...")
wb = openpyxl.load_workbook('lotto_data.xlsx')
ws = wb.active

max_row = ws.max_row
yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
no_fill = PatternFill(fill_type=None)

# 번호 컬럼 위치 확인 (B~G = 2~7열)
NUM_START_COL = 2  # B열
NUM_END_COL = 7    # G열

print(f"총 {max_row - 1}개 회차의 데이터를 처리합니다...")
print("기존 노란 배경을 초기화하는 중...")

# 기존 배경색 초기화 (데이터 행만: 2행부터)
for row in range(2, max_row + 1):
    for col in range(NUM_START_COL, NUM_END_COL + 1):
        ws.cell(row=row, column=col).fill = no_fill

print("이전 차수와 번호가 겹치는 셀에 노란 배경을 칠하는 중...")

# 각 행(row)을 순회하며, 위/아래 행과 번호가 겹치면 노란색으로 칠하기
# 데이터는 2행부터 시작 (1행은 헤더)
# 파일이 최신 회차가 위에 있으므로, '이전 차수' = 아래 행(row+1)
for row in range(2, max_row + 1):
    # 현재 행의 번호들
    current_nums = set()
    for col in range(NUM_START_COL, NUM_END_COL + 1):
        val = ws.cell(row=row, column=col).value
        if val is not None:
            current_nums.add(int(val))

    # 위 행(row-1)의 번호들 (바로 이전 회차 = 더 최신)
    prev_nums = set()
    if row > 2:
        for col in range(NUM_START_COL, NUM_END_COL + 1):
            val = ws.cell(row=row - 1, column=col).value
            if val is not None:
                prev_nums.add(int(val))

    # 아래 행(row+1)의 번호들 (바로 다음 회차 = 더 과거)
    next_nums = set()
    if row < max_row:
        for col in range(NUM_START_COL, NUM_END_COL + 1):
            val = ws.cell(row=row + 1, column=col).value
            if val is not None:
                next_nums.add(int(val))

    # 현재 행의 번호가 위 또는 아래 행과 겹치면 노란색
    adjacent_nums = prev_nums | next_nums
    for col in range(NUM_START_COL, NUM_END_COL + 1):
        val = ws.cell(row=row, column=col).value
        if val is not None and int(val) in adjacent_nums:
            ws.cell(row=row, column=col).fill = yellow_fill

# 파일 저장 (원본 파일에 바로 저장)
wb.save('lotto_data.xlsx')
print("[완료] 노란 배경 처리 완료! 'lotto_data.xlsx' 파일에 저장되었습니다.")