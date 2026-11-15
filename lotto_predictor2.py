import os
import sys
import random
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

# Windows 콘솔 인코딩 대응
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 머신러닝/딥러닝 라이브러리 임포트
try:
    import xgboost as xgb
    import lightgbm as lgb
except ImportError:
    xgb = None
    lgb = None

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:
    torch = None

# ──────────────────────────────────────────────
# 📊 역대 당첨 통계 기반 8가지 검증 규칙 설정
# ──────────────────────────────────────────────
HOT_NUMBERS = {34, 13, 27, 18, 12, 33, 45, 38, 37, 40}

def check_stat_rules(nums, lw_numbers=None, available_hot=None):
    """
    역대 통계에서 도출한 8가지 규칙 검증 (모두 만족 시 True)
    """
    nums = sorted(nums)

    # 규칙 1: 홀짝 비율 (홀수 2~4개)
    odd_count = sum(1 for n in nums if n % 2 == 1)
    if not (2 <= odd_count <= 4):
        return False

    # 규칙 2: 고저 비율 (1~22 저번호 2~4개)
    low_count = sum(1 for n in nums if n <= 22)
    if not (2 <= low_count <= 4):
        return False

    # 규칙 3: 번호 합계 범위 (100 ~ 180)
    total = sum(nums)
    if not (100 <= total <= 180):
        return False

    # 규칙 4: 연속 번호 쌍 2개 이하
    consec_pairs = sum(1 for i in range(len(nums) - 1) if nums[i+1] - nums[i] == 1)
    if consec_pairs > 2:
        return False

    # 규칙 5: 끝자리(일의 자리) 중복 2개 이하
    endings = [n % 10 for n in nums]
    dup_endings = 6 - len(set(endings))
    if dup_endings >= 3:
        return False

    # 규칙 6: 구간 분포 (1-10, 11-20, 21-30, 31-40, 41-45 중 한 구간 4개 이상 몰림 제외)
    zones = [0] * 5
    for n in nums:
        if n <= 10:   zones[0] += 1
        elif n <= 20: zones[1] += 1
        elif n <= 30: zones[2] += 1
        elif n <= 40: zones[3] += 1
        else:         zones[4] += 1
    if max(zones) >= 4:
        return False

    # 규칙 7: 핫번호 포함 (사용 가능한 핫번호가 존재하는 경우 1개 이상 포함)
    target_hot = available_hot if available_hot is not None else HOT_NUMBERS
    if target_hot:
        hot_count = sum(1 for n in nums if n in target_hot)
        if hot_count == 0:
            return False

    # 규칙 8: 직전 회차 번호 재등장 0~2개 (3개 이상 겹침 제외)
    if lw_numbers:
        overlap = len(set(nums) & set(lw_numbers))
        if overlap >= 3:
            return False

    return True

def load_data(file_path):
    """
    1회차부터 최신 회차까지 전체 유효 데이터를 로드합니다.
    """
    try:
        df = pd.read_excel(file_path)
        first_col = df.columns[0]
        if first_col != '회차':
            df = df.rename(columns={first_col: '회차'})

        if '회차' in df.columns:
            df = df.sort_values(by='회차', ascending=True).reset_index(drop=True)

        num_cols = ['번호1', '번호2', '번호3', '번호4', '번호5', '번호6']
        if not all(col in df.columns for col in num_cols):
            print("오류: '번호1' ~ '번호6' 컬럼이 존재하지 않습니다.")
            sys.exit(1)

        valid_data = []
        for _, row in df[num_cols].iterrows():
            clean_row = [int(x) for x in row if pd.notna(x) and 1 <= int(x) <= 45]
            if len(clean_row) == 6:
                valid_data.append(sorted(clean_row))

        if len(valid_data) == 0:
            print("오류: 유효한 로또 번호 데이터가 없습니다.")
            sys.exit(1)

        valid_data = np.array(valid_data)
        min_round = int(df['회차'].iloc[0])
        max_round = int(df['회차'].iloc[-1])
        return valid_data, (min_round, max_round)
    except Exception as e:
        print(f"데이터 파일 로딩 중 오류 발생: {e}")
        sys.exit(1)

def get_train_data(data):
    """
    원-핫 인코딩 시퀀스 데이터셋 구성
    """
    X = []
    y = []
    for i in range(len(data) - 1):
        x_vec = np.zeros(45)
        for num in data[i]:
            x_vec[int(num) - 1] = 1
        X.append(x_vec)

        y_vec = np.zeros(45)
        for num in data[i + 1]:
            y_vec[int(num) - 1] = 1
        y.append(y_vec)

    X = np.array(X)
    y = np.array(y)

    last_vec = np.zeros(45)
    for num in data[-1]:
        last_vec[int(num) - 1] = 1
    last_input = last_vec.reshape(1, -1)

    return X, y, last_input

def train_lstm_probs(X, y, last_input):
    """
    LSTM 딥러닝 모델 학습 후 번호별 예측 확률 반환
    """
    if torch is None:
        print("  [알림] PyTorch 미설치로 Random Forest로 대체합니다.")
        return train_rf_probs(X, y, last_input)

    class LottoLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(input_size=45, hidden_size=64, batch_first=True)
            self.fc = nn.Linear(64, 45)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x):
            out, _ = self.lstm(x)
            out = self.fc(out[:, -1, :])
            return self.sigmoid(out)

    X_t = torch.FloatTensor(X).unsqueeze(1)
    y_t = torch.FloatTensor(y)
    last_t = torch.FloatTensor(last_input).unsqueeze(1)

    model = LottoLSTM()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)

    model.train()
    for _ in range(50):
        optimizer.zero_grad()
        loss = criterion(model(X_t), y_t)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        probs = model(last_t).numpy()[0]
    return probs

def train_xgb_lgb_probs(X, y, last_input):
    """
    XGBoost & LightGBM 앙상블 모델 학습 후 번호별 예측 확률 반환
    """
    if xgb is None or lgb is None:
        print("  [알림] XGBoost/LightGBM 미설치로 Random Forest로 대체합니다.")
        return train_rf_probs(X, y, last_input)

    df_X = pd.DataFrame(X, columns=[f'num_{k+1}' for k in range(45)])
    df_last = pd.DataFrame(last_input, columns=[f'num_{k+1}' for k in range(45)])

    pred_probs = np.zeros(45)
    for i in range(45):
        y_i = y[:, i]
        if len(np.unique(y_i)) > 1:
            m_xgb = xgb.XGBRegressor(n_estimators=40, max_depth=3, objective='reg:squarederror', verbosity=0)
            m_xgb.fit(X, y_i)
            p_xgb = m_xgb.predict(last_input)[0]

            m_lgb = lgb.LGBMRegressor(n_estimators=40, max_depth=3, verbosity=-1)
            m_lgb.fit(df_X, y_i)
            p_lgb = m_lgb.predict(df_last)[0]

            pred_probs[i] = (p_xgb + p_lgb) / 2.0
        else:
            pred_probs[i] = y_i[0]
    return pred_probs

def train_rf_probs(X, y, last_input):
    """
    Random Forest 모델 학습 후 번호별 예측 확률 반환
    """
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    probs = model.predict(last_input)[0]
    return probs

def generate_sets(pred_probs, num_sets=5, excluded_numbers=None, last_week_numbers=None, existing_seen=None):
    """
    주어진 확률 벡터와 8가지 통계 규칙을 적용하여 중복되지 않는 num_sets 개의 로또 번호 세트 생성
    """
    if excluded_numbers is None:
        excluded_numbers = set()
    if existing_seen is None:
        existing_seen = set()

    available_numbers = [n for n in range(1, 46) if n not in excluded_numbers]
    available_hot = HOT_NUMBERS - excluded_numbers

    # 만약 제외수가 너무 많아서 핫번호가 없거나 선택 가능한 번호가 6개 미만인 경우 보호
    if len(available_numbers) < 6:
        print("  [경고] 제외수가 너무 많아 일부 제외수를 해제합니다.")
        excluded_numbers = set()
        available_numbers = list(range(1, 46))
        available_hot = HOT_NUMBERS

    results = []
    attempts = 0
    max_attempts = num_sets * 1000

    while len(results) < num_sets and attempts < max_attempts:
        attempts += 1
        # 노이즈를 주어 다양한 조합 탐색
        noise = np.random.uniform(0, max(0.01, np.max(pred_probs) * 0.35 + 0.05), size=45)
        adj_probs = pred_probs.copy() + noise

        # 제외수 가중치 제거
        for ex in excluded_numbers:
            if 1 <= ex <= 45:
                adj_probs[ex - 1] = -999999.0

        top_6 = np.argsort(adj_probs)[-6:]
        combo = tuple(sorted([int(idx) + 1 for idx in top_6]))

        if combo not in existing_seen:
            if check_stat_rules(combo, last_week_numbers, available_hot):
                existing_seen.add(combo)
                results.append(list(combo))

    # 규칙 조건이 너무 엄격하여 미달 시, 규칙 완화 폴백
    fallback_attempts = 0
    while len(results) < num_sets and fallback_attempts < 20000:
        fallback_attempts += 1
        sample_nums = random.sample(available_numbers, 6)
        combo = tuple(sorted(sample_nums))
        if combo not in existing_seen:
            # 규칙 우선 적용 시도, 10000회 이상 넘어가면 최소한의 홀짝/합계만 체크
            if fallback_attempts < 10000:
                if check_stat_rules(combo, last_week_numbers, available_hot):
                    existing_seen.add(combo)
                    results.append(list(combo))
            else:
                total = sum(combo)
                odd_c = sum(1 for n in combo if n % 2 == 1)
                if 90 <= total <= 190 and 1 <= odd_c <= 5:
                    existing_seen.add(combo)
                    results.append(list(combo))

    return results

def main():
    print("=" * 60)
    print(" [*] 로또 번호 1-SHOT 완전 자동 예측기 (25개 세트 추천)")
    print("=" * 60)

    excel_file = "lotto_data.xlsx"
    if not os.path.exists(excel_file):
        print(f"오류: '{excel_file}' 파일이 존재하지 않습니다.")
        sys.exit(1)

    print(f"\n[1] '{excel_file}' 데이터 로딩 중 (1회차부터 최신 회차까지 전체 분석)...")
    data, (min_round, max_round) = load_data(excel_file)
    print(f"  총 데이터: {len(data)}회차 ({min_round}회 ~ {max_round}회)")

    last_week_numbers = list(data[-1])
    print(f"  최근({max_round}회) 당첨번호: {last_week_numbers}")

    print("\n[2] 머신러닝/딥러닝 데이터셋 구축 중...")
    X, y, last_input = get_train_data(data)

    seen_sets = set()
    recommendations_by_group = {}

    # ── 그룹 1: LSTM (5개) ──
    print("\n[3] [그룹 1] LSTM 딥러닝 모델 학습 및 5세트 생성 중...")
    start_time = time.time()
    lstm_probs = train_lstm_probs(X, y, last_input)
    group1 = generate_sets(lstm_probs, num_sets=5, excluded_numbers=set(),
                           last_week_numbers=last_week_numbers, existing_seen=seen_sets)
    recommendations_by_group['그룹 1 (LSTM)'] = group1
    print(f"  -> 완료 ({time.time() - start_time:.1f}초)")

    # 그룹 1에서 나온 모든 고유 번호 추출
    group1_numbers = set([num for s in group1 for num in s])
    print(f"  * 그룹 1 전체 출현 번호 (총 {len(group1_numbers)}개): {sorted(list(group1_numbers))}")

    # ── 그룹 2: LSTM 제외수 적용 (5개) ──
    print("\n[4] [그룹 2] 그룹 1 추출 번호를 '제외수'로 설정하여 LSTM 5세트 생성 중...")
    group2 = generate_sets(lstm_probs, num_sets=5, excluded_numbers=group1_numbers,
                           last_week_numbers=last_week_numbers, existing_seen=seen_sets)
    recommendations_by_group['그룹 2 (LSTM - 그룹1 제외)'] = group2
    print(f"  -> 완료")

    # ── 그룹 3: XGBoost & LightGBM (5개) ──
    print("\n[5] [그룹 3] XGBoost & LightGBM 앙상블 모델 학습 및 5세트 생성 중...")
    start_time = time.time()
    xgb_probs = train_xgb_lgb_probs(X, y, last_input)
    group3 = generate_sets(xgb_probs, num_sets=5, excluded_numbers=set(),
                           last_week_numbers=last_week_numbers, existing_seen=seen_sets)
    recommendations_by_group['그룹 3 (XGBoost & LightGBM)'] = group3
    print(f"  -> 완료 ({time.time() - start_time:.1f}초)")

    # 그룹 3에서 나온 모든 고유 번호 추출
    group3_numbers = set([num for s in group3 for num in s])
    print(f"  * 그룹 3 전체 출현 번호 (총 {len(group3_numbers)}개): {sorted(list(group3_numbers))}")

    # ── 그룹 4: XGBoost 제외수 적용 (5개) ──
    print("\n[6] [그룹 4] 그룹 3 추출 번호를 '제외수'로 설정하여 XGBoost 5세트 생성 중...")
    group4 = generate_sets(xgb_probs, num_sets=5, excluded_numbers=group3_numbers,
                           last_week_numbers=last_week_numbers, existing_seen=seen_sets)
    recommendations_by_group['그룹 4 (XGBoost - 그룹3 제외)'] = group4
    print(f"  -> 완료")

    # ── 그룹 5: Random Forest (5개) ──
    print("\n[7] [그룹 5] Random Forest 모델 학습 및 5세트 생성 중...")
    start_time = time.time()
    rf_probs = train_rf_probs(X, y, last_input)
    group5 = generate_sets(rf_probs, num_sets=5, excluded_numbers=set(),
                           last_week_numbers=last_week_numbers, existing_seen=seen_sets)
    recommendations_by_group['그룹 5 (Random Forest)'] = group5
    print(f"  -> 완료 ({time.time() - start_time:.1f}초)")

    # ── 최종 결과 출력 및 텍스트 파일 저장 ──
    # 전체 5개 그룹 중 예산(15,000원 = 15세트)에 맞게 무작위 3개 그룹 선정
    group_keys = list(recommendations_by_group.keys())
    selected_group_keys = sorted(random.sample(group_keys, 3), key=lambda k: group_keys.index(k))

    output_lines = []
    output_lines.append("=" * 65)
    output_lines.append(f" [*] 로또 {max_round + 1}회차 대비 추천 번호 15세트 (1만5천원 예산 맞춤)")
    output_lines.append(f" 기준 데이터: 1회 ~ {max_round}회 전체 분석 | 8가지 통계 황금 규칙 적용")
    output_lines.append(" 5개 AI 분석 그룹 중 무작위 추첨된 3개 행운 그룹 (총 15세트)")
    output_lines.append("=" * 65)

    set_idx = 1
    for grp_name in selected_group_keys:
        sets = recommendations_by_group[grp_name]
        output_lines.append(f"\n[ {grp_name} ]")
        for nums in sets:
            odd_cnt = sum(1 for n in nums if n % 2 == 1)
            total = sum(nums)
            output_lines.append(f"  세트 {set_idx:02d}:  {nums}   (합: {total}, 홀{odd_cnt}:짝{6-odd_cnt})")
            set_idx += 1

    output_lines.append("\n" + "=" * 65)
    output_lines.append(" 행운을 빕니다! 이번 주 1등 당첨 대박 기원합니다! (총 15게임 / 15,000원)")
    output_lines.append("=" * 65)

    final_text = "\n".join(output_lines)
    print("\n" + final_text)

    # 15세트 맞춤 파일로 저장
    try:
        with open("recommended_lotto_15.txt", "w", encoding="utf-8") as f:
            f.write(final_text)
        print("\n[저장 완료] 이번 주 1만 5천원(15세트) 추천 번호가 'recommended_lotto_15.txt'에 저장되었습니다.")
    except Exception:
        pass

    # 전체 25개 세트 백업 저장 (선택 사항)
    try:
        all_lines = []
        all_lines.append("=" * 65)
        all_lines.append(f" [*] 로또 {max_round + 1}회차 분석 전체 25세트 원본 백업")
        all_lines.append("=" * 65)
        all_set_idx = 1
        for grp_name, sets in recommendations_by_group.items():
            all_lines.append(f"\n[ {grp_name} ]")
            for nums in sets:
                odd_cnt = sum(1 for n in nums if n % 2 == 1)
                total = sum(nums)
                all_lines.append(f"  세트 {all_set_idx:02d}:  {nums}   (합: {total}, 홀{odd_cnt}:짝{6-odd_cnt})")
                all_set_idx += 1
        with open("recommended_lotto_all_25.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(all_lines))
    except Exception:
        pass

if __name__ == "__main__":
    main()