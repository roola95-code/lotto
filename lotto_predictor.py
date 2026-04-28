import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 새로운 모델 라이브러리 (설치 필요)
try:
    import xgboost as xgb
    import lightgbm as lgb
except ImportError as e:
    print(f"XGBoost/LightGBM 임포트 에러: {e}")


try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:
    pass

def create_sample_excel(file_path):
    # 템플릿 파일 생성
    print(f"'{file_path}' 파일이 없어서 샘플 템플릿을 생성합니다.")
    # 임의의 과거 10주치 샘플 데이터
    data = {
        '회차': list(range(1001, 1011)),
        '번호1': [1, 2, 5, 2, 7, 3, 4, 1, 9, 2],
        '번호2': [10, 11, 12, 17, 18, 14, 15, 12, 14, 11],
        '번호3': [23, 19, 20, 21, 22, 23, 24, 28, 26, 25],
        '번호4': [31, 25, 29, 32, 33, 30, 31, 35, 34, 30],
        '번호5': [40, 36, 35, 41, 40, 39, 42, 40, 41, 42],
        '번호6': [45, 42, 44, 43, 44, 45, 43, 44, 45, 44]
    }
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)
    print(f"샘플 파일({file_path})이 생성되었습니다. 본인의 데이터로 수정 후 다시 실행해주세요.")

def load_data(file_path, past_weeks):
    try:
        # 파일 형식에 따라 유연하게 읽기 (엑셀이 아니면 CSV로 시도)
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        # ★ [수정된 부분] 최신 회차가 맨 위에 있다면 오름차순(과거->최신)으로 정렬
        if '회차' in df.columns and df['회차'].iloc[0] > df['회차'].iloc[-1]:
            df = df.sort_values(by='회차', ascending=True)
            
        # 숫자형 데이터만 추출
        df_numeric = df.select_dtypes(include=[np.number])
        
        # 마지막 6개 열이 로또 번호라고 가정 (보너스 번호 제외)
        if df_numeric.shape[1] < 6:
            print("엑셀 파일에 숫자 데이터 열이 6개 이상 필요합니다.")
            sys.exit(1)
            
        cols = df_numeric.columns[-6:]
        data = df_numeric[cols].values
        
        # 유효한 로또 번호(1~45)만 필터링
        valid_data = []
        valid_rounds = []
        has_round = '회차' in df.columns
        if has_round:
            round_vals = df['회차'].values
            
        for idx, row in enumerate(data):
            valid_row = [x for x in row if not pd.isna(x) and 1 <= x <= 45]
            if len(valid_row) == 6:
                valid_data.append(valid_row)
                if has_round:
                    valid_rounds.append(round_vals[idx])
                
        if len(valid_data) == 0:
            print("유효한 로또 번호 데이터가 없습니다. (1~45 사이의 숫자 6개)")
            sys.exit(1)
            
        valid_data = np.array(valid_data)
        actual_weeks = len(valid_data) if len(valid_data) < past_weeks else past_weeks
        
        if len(valid_data) < past_weeks:
            print(f"경고: 요청한 {past_weeks}주보다 데이터가 적습니다. (실제 데이터: {len(valid_data)}주)")
            
        final_data = valid_data[-actual_weeks:]
        
        round_info = None
        if has_round and len(valid_rounds) > 0:
            final_rounds = valid_rounds[-actual_weeks:]
            # 사용자가 요청한 양식: "1212회 ~ 1208회" 와 같이 큰 값이 먼저 오도록 정렬하기 위해 max, min 추출
            max_round = max(final_rounds[0], final_rounds[-1])
            min_round = min(final_rounds[0], final_rounds[-1])
            round_info = (max_round, min_round)
            
        return final_data, round_info
        
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        sys.exit(1)

def predict_lotto(data, num_sets, model_type='1', filters=None, excluded_numbers=None, included_numbers=None):
    if excluded_numbers is None:
        excluded_numbers = set()
    if included_numbers is None:
        included_numbers = set()
        
    # 만약 포함수와 제외수가 겹치면 제외수에서 빼서 포함수를 우선시함
    excluded_numbers = excluded_numbers - included_numbers
        
    if filters is None:
        filters = {
            'sum': (122, 180),
            'front_sum': (34, 63),
            'back_sum': (82, 120),
            'first': (7, 15),
            'last': (22, 38)
        }
        
    if len(data) < 2:
        print("최소 2주 이상의 데이터가 필요하여 모델을 학습할 수 없습니다.")
        # 데이터가 부족하면 일단 랜덤으로 추천
        recommendations = []
        for _ in range(num_sets):
            base_lotto = set(included_numbers)
            while len(base_lotto) < 6:
                base_lotto.add(int(np.random.choice(range(1, 46))))
            recommendations.append(sorted(list(base_lotto)))
        return recommendations

    # 머신러닝을 위한 데이터 셋 구성 (공통)
    # X: 이전 주차의 번호 분포, y: 다음 주차의 번호 분포
    X = []
    y = []
    
    for i in range(len(data) - 1):
        x_vec = np.zeros(45)
        for num in data[i]:
            x_vec[int(num)-1] = 1
        X.append(x_vec)
        
        y_vec = np.zeros(45)
        for num in data[i+1]:
            y_vec[int(num)-1] = 1
        y.append(y_vec)
        
    X = np.array(X)
    y = np.array(y)
    
    # 가장 마지막 주차 데이터
    last_week_vec = np.zeros(45)
    for num in data[-1]:
        last_week_vec[int(num)-1] = 1
        
    last_week_input = last_week_vec.reshape(1, -1)
    
    # 1. Random Forest 예측
    if model_type == '1':
        print("\n [Random Forest] 모델을 학습 중입니다 (학습 속도 빠름)...")
        model = RandomForestRegressor(n_estimators=100, random_state=None)
        model.fit(X, y)
        pred_probs = model.predict(last_week_input)[0]

    # 2. LSTM 예측
    elif model_type == '2':
        print("\n [LSTM] 딥러닝 모델을 학습 중입니다 (시간이 조금 걸릴 수 있습니다)...")
        try:
            # PyTorch LSTM 구현
            class LottoLSTM(nn.Module):
                def __init__(self):
                    super(LottoLSTM, self).__init__()
                    self.lstm = nn.LSTM(input_size=45, hidden_size=64, batch_first=True)
                    self.fc = nn.Linear(64, 45)
                    self.sigmoid = nn.Sigmoid()
                    
                def forward(self, x):
                    out, _ = self.lstm(x)
                    out = self.fc(out[:, -1, :])
                    return self.sigmoid(out)
                    
            # 텐서 변환: (samples, time_steps, features)
            X_tensor = torch.FloatTensor(X).unsqueeze(1)
            y_tensor = torch.FloatTensor(y)
            
            model_lstm = LottoLSTM()
            criterion = nn.MSELoss()
            optimizer = optim.Adam(model_lstm.parameters(), lr=0.01)
            
            # 빠른 데모를 위해 epochs 50
            model_lstm.train()
            print(" LSTM Epoch 학습을 진행합니다...")
            for epoch in range(50):
                optimizer.zero_grad()
                outputs = model_lstm(X_tensor)
                loss = criterion(outputs, y_tensor)
                loss.backward()
                optimizer.step()
                
            model_lstm.eval()
            last_tensor = torch.FloatTensor(last_week_input).unsqueeze(1)
            with torch.no_grad():
                pred_probs = model_lstm(last_tensor).numpy()[0]
                
        except NameError:
            print("오류: 파이토치(PyTorch) 라이브러리가 설치되지 않았습니다. 기본 Random Forest로 진행합니다.")
            model = RandomForestRegressor(n_estimators=100)
            model.fit(X, y)
            pred_probs = model.predict(last_week_input)[0]

    # 3. XGBoost/LightGBM 앙상블 예측 (단순 결합)
    elif model_type == '3':
        print("\n [XGBoost & LightGBM] 앙상블 모델을 학습 중입니다...")
        pred_probs = np.zeros(45)
        try:
            # 각 자리(1~45)에 대해 개별 모델 학습
            for i in range(45):
                y_i = y[:, i]
                # 타겟값이 모두 같으면(예: 모두 0) 스킵
                if len(np.unique(y_i)) > 1:
                    model_xgb = xgb.XGBRegressor(n_estimators=50, max_depth=3, objective='reg:squarederror', verbosity=0)
                    model_xgb.fit(X, y_i)
                    
                    # LightGBM에서 warning을 피하기 위해 column name이 있는 DataFrame으로 래핑
                    df_X = pd.DataFrame(X, columns=[f'num_{k+1}' for k in range(45)])
                    model_lgb = lgb.LGBMRegressor(n_estimators=50, max_depth=3, verbosity=-1)
                    model_lgb.fit(df_X, y_i)
                    
                    # 두 예측 모델의 평균값 적용
                    pred_xgb = model_xgb.predict(last_week_input)[0]
                    df_last_week = pd.DataFrame(last_week_input, columns=[f'num_{k+1}' for k in range(45)])
                    pred_lgb = model_lgb.predict(df_last_week)[0]
                    
                    pred_probs[i] = (pred_xgb + pred_lgb) / 2
        except NameError:
            print("오류: xgboost 또는 lightgbm이 설치되지 않았습니다. 기본 Random Forest로 진행합니다.")
            model = RandomForestRegressor(n_estimators=100)
            model.fit(X, y)
            pred_probs = model.predict(last_week_input)[0]
            
    else:
        print("알 수 없는 기법입니다. 기본 Random Forest로 진행합니다.")
        model = RandomForestRegressor(n_estimators=100)
        model.fit(X, y)
        pred_probs = model.predict(last_week_input)[0]

    recommendations = []
    seen_sets = set()
    
    # 중복 세트를 방지하기 위해 최대 시도 횟수 제한 (무한 루프 방지)
    max_attempts = num_sets * 200 # 필터 조건에 맞추기 위해 시도 횟수 증가
    attempts = 0
    
    def is_valid_lotto(nums):
        if any(n in excluded_numbers for n in nums):
            return False
            
        if not filters:
            return True
        
        total_sum = sum(nums)
        front_sum = sum(nums[:3])
        back_sum = sum(nums[3:])
        # 첫수: 십의 자리 합 (0~4)
        first_sum = sum(n // 10 for n in nums)
        # 끝수: 일의 자리 합 (0~9)
        last_sum = sum(n % 10 for n in nums)
        
        if not (filters['sum'][0] <= total_sum <= filters['sum'][1]):
            return False
        if not (filters['front_sum'][0] <= front_sum <= filters['front_sum'][1]):
            return False
        if not (filters['back_sum'][0] <= back_sum <= filters['back_sum'][1]):
            return False
        if not (filters['first'][0] <= first_sum <= filters['first'][1]):
            return False
        if not (filters['last'][0] <= last_sum <= filters['last'][1]):
            return False
            
        return True
    
    while len(recommendations) < num_sets and attempts < max_attempts:
        attempts += 1
        # 무작위성을 부여하여 예측치를 기반으로 여러 세트가 다르게 나오게 함
        # 동일한 번호가 자주 나오는 것을 방지하기 위해 noise의 비율을 살짝 늘렸습니다.
        noise = np.random.uniform(0, np.max(pred_probs)*0.3 + 0.05, size=45)
        adjusted_probs = pred_probs + noise
        
        # 포함수가 무조건 선택되도록 확률을 압도적으로 높임
        for n in included_numbers:
            if 1 <= n <= 45:
                adjusted_probs[n-1] += 99999.0
        
        # 확률이 높은 상위 6개 번호 추출
        top_6_indices = np.argsort(adjusted_probs)[-6:]
        lotto_numbers = tuple(sorted([int(idx) + 1 for idx in top_6_indices]))
        
        # 아직 추가되지 않은 새로운 조합일 때만 저장
        if lotto_numbers not in seen_sets and is_valid_lotto(lotto_numbers):
            seen_sets.add(lotto_numbers)
            recommendations.append(list(lotto_numbers))
            
    # 만약 시도 횟수를 다 소모했는데도 개수를 못 채웠다면 남은 개수만큼 무작위 랜덤으로 채움
    random_attempts = 0
    while len(recommendations) < num_sets and random_attempts < 1000:
        random_attempts += 1
        base_lotto = set(included_numbers)
        while len(base_lotto) < 6:
            base_lotto.add(int(np.random.choice(range(1, 46))))
        random_lotto = tuple(sorted(list(base_lotto)))
        
        if random_lotto not in seen_sets and is_valid_lotto(random_lotto):
            seen_sets.add(random_lotto)
            recommendations.append(list(random_lotto))
            
    # 조건이 너무 까다로워서 개수를 못 채웠을 경우 무조건 채움
    while len(recommendations) < num_sets:
        base_lotto = set(included_numbers)
        while len(base_lotto) < 6:
            base_lotto.add(int(np.random.choice(range(1, 46))))
        random_lotto = tuple(sorted(list(base_lotto)))
        
        if random_lotto not in seen_sets and not any(n in excluded_numbers for n in random_lotto):
            seen_sets.add(random_lotto)
            recommendations.append(list(random_lotto))
            
    return recommendations

def send_email(to_email, recommendations):
    # 송신자 이메일 정보 (사용자 설정 필요)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "roola95@gmail.com" # 송신자 구글 이메일
    sender_password = "yltb xegv qyjt wzml" # 구글 앱 비밀번호

    if sender_email == "your_email@gmail.com":
        print("\n[안내] 이메일을 실제로 발송하려면 소스 코드의 send_email 함수 내에 송신자 이메일과 앱 비밀번호를 설정해야 합니다.")
        return

    subject = "로또 추천 번호"
    body = "요청하신 추천 로또 번호입니다:\n\n"
    for i, nums in enumerate(recommendations, 1):
        body += f" 세트 {i}:  {nums}\n"
    body += "\n행운을 빕니다!"
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        print("\n이메일을 발송하는 중...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"성공적으로 {to_email} 주소로 이메일을 발송했습니다!")
    except Exception as e:
        print(f"이메일 발송에 실패했습니다: {e}")

def main():
    print("="*40)
    print(" 머신러닝 기반 로또 번호 추천 프로그램")
    print("="*40)
    
    excel_file = "lotto_data.xlsx"
    
    # 엑셀 파일이 없으면 샘플 생성
    if not os.path.exists(excel_file):
        create_sample_excel(excel_file)
        return

    try:
        print("\n=== 예측 기법 선택 ===")
        print(" 1. Random Forest (빠름)")
        print(" 2. LSTM (딥러닝 기반 시계열 분석)")
        print(" 3. XGBoost & LightGBM (고급 앙상블)")
        model_choice = input("▶ 번호를 선택하세요 (기본 1) : ").strip()
        if not model_choice in ['1', '2', '3']:
            model_choice = '1'

        print()
        past_weeks_input = input("▶ 엑셀에서 최근 몇 주간의 데이터를 분석할까요? (예: 10, 20) : ")
        past_weeks = int(past_weeks_input.strip())
        
        num_sets_input = input("▶ 생성할 추천 번호 조합의 수를 입력하세요 (예: 1, 4) : ")
        num_sets = int(num_sets_input.strip())
    except ValueError:
        print("오류: 올바른 숫자를 입력해주세요.")
        return

    print("\n=== 번호 필터링 조건 설정 ===")
    print("기본값을 사용하려면 그냥 Enter를 누르세요.")
    
    def get_range_input(prompt_text, default_min, default_max):
        val = input(f"{prompt_text} (기본: {default_min}~{default_max}) [예: 122 180]: ").strip()
        if not val:
            return (default_min, default_max)
        try:
            parts = val.replace(',', ' ').split()
            if len(parts) >= 2:
                return (int(parts[0]), int(parts[1]))
            else:
                print(" -> 입력 형식이 잘못되었습니다. 기본값을 사용합니다.")
                return (default_min, default_max)
        except ValueError:
            print(" -> 숫자가 아닙니다. 기본값을 사용합니다.")
            return (default_min, default_max)

    sum_range = get_range_input("1. 번호합 범위", 122, 180)
    front_sum_range = get_range_input("2. 앞수합(1~3번째) 범위", 34, 63)
    back_sum_range = get_range_input("3. 뒷수합(4~6번째) 범위", 82, 120)
    first_range = get_range_input("4. 첫수합(십의 자리 합) 범위", 7, 15)
    last_range = get_range_input("5. 끝수합(일의 자리 합) 범위", 22, 38)
    
    filters = {
        'sum': sum_range,
        'front_sum': front_sum_range,
        'back_sum': back_sum_range,
        'first': first_range,
        'last': last_range
    }

    print(f"\n[{excel_file}] 파일에서 최근 {past_weeks}주 데이터를 불러오는 중...")
    data, round_info = load_data(excel_file, past_weeks)
    
    if round_info:
        max_round, min_round = round_info
        print(f"▶ {max_round}회 ~ {min_round}회의 데이터로 분석하겠습니다.")
        
    # === 연속 미발생 번호 계산 ===
    non_appearance = {i: 0 for i in range(1, 46)}
    for num in range(1, 46):
        streak = 0
        for i in range(len(data)-1, -1, -1):
            if num in data[i]:
                break
            streak += 1
        non_appearance[num] = streak
        
    # 내림차순 정렬 후 상위 10개 추출
    sorted_non_appearance = sorted(non_appearance.items(), key=lambda x: x[1], reverse=True)[:10]
    
    print("\n=== 최근 회차 기준 연속 미발생 번호 Top 10 ===")
    for rank, (num, streak) in enumerate(sorted_non_appearance, 1):
        print(f" {rank}위: {num}번 (최근 {streak}주 연속 미발생)")
        
    excluded_input = input("\n▶ 제외할 번호를 쉼표로 구분하여 입력하세요 (예: 4, 15) [없으면 Enter]: ").strip()
    excluded_numbers = set()
    if excluded_input:
        try:
            excluded_numbers = set(int(x.strip()) for x in excluded_input.split(','))
            print(f" -> 선택된 제외수: {sorted(list(excluded_numbers))}")
        except ValueError:
            print(" -> 입력 형식이 잘못되었습니다. 제외수 없이 진행합니다.")
            
    included_input = input("\n▶ 반드시 포함할 번호(고정수)를 쉼표로 구분하여 입력하세요 (예: 3, 4) [없으면 Enter]: ").strip()
    included_numbers = set()
    if included_input:
        try:
            included_numbers = set(int(x.strip()) for x in included_input.split(','))
            print(f" -> 선택된 포함수: {sorted(list(included_numbers))}")
        except ValueError:
            print(" -> 입력 형식이 잘못되었습니다. 포함수 없이 진행합니다.")
            
    recommendations = predict_lotto(data, num_sets, model_type=model_choice, filters=filters, excluded_numbers=excluded_numbers, included_numbers=included_numbers)
    
    print("="*12, "추천 로또 번호", "="*12)
    for i, nums in enumerate(recommendations, 1):
        print(f" 세트 {i}:  {nums}")
    print("="*40)
    print("행운을 빕니다!\n")
    
    send_mail_choice = input("추천된 번호를 메일로 보내시겠습니까? (YES/NO): ").strip().upper()
    if send_mail_choice in ['Y', 'YES']:
        to_email = input("받으실 메일 주소를 입력하세요: ").strip()
        if to_email:
            send_email(to_email, recommendations)
        else:
            print("메일 주소가 입력되지 않았습니다.")

if __name__ == "__main__":
    main()
