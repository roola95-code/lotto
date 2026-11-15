@echo off
setlocal
chcp 949 > nul
title 로또 번호 자동 추출 프로그램

echo ============================================
echo   로또 원샷 자동 실행기 (LOTTO AUTO RUNNER)
echo ============================================
echo.

cd /d "%~dp0"

:: -----------------------------------------------
:: STEP 0: 최신 당첨번호 자동 수집 (동행복권)
:: -----------------------------------------------
echo [0단계 / 총 3단계] 최신 당첨번호 수집 중...
echo --------------------------------------------
python lotto_auto_update.py
if errorlevel 1 goto :error_step0
echo.
echo [성공] 0단계 완료! 최신 당첨 번호가 업데이트되었습니다.
echo.

:: -----------------------------------------------
:: STEP 1: 통계 칼럼 계산
:: -----------------------------------------------
echo [1단계 / 총 3단계] 통계 데이터 계산 중...
echo --------------------------------------------
python update_lotto_feature.py
if errorlevel 1 goto :error_step1
echo.
echo [성공] 1단계 완료! 통계 데이터 계산이 완료되었습니다.
echo.

:: -----------------------------------------------
:: STEP 2: 중복 번호 서식 처리
:: -----------------------------------------------
echo [2단계 / 총 3단계] 중복 번호 강조 서식 적용 중...
echo --------------------------------------------
python gemini-code-1785640123148.py
if errorlevel 1 goto :error_step2
echo.
echo [성공] 2단계 완료! 엑셀 서식 작업이 완료되었습니다.
echo.

:: -----------------------------------------------
:: STEP 3: 로또 번호 15세트(15,000원) 추천 번호 예측
:: -----------------------------------------------
echo [3단계 / 총 3단계] 인공지능 추천 번호 15세트 생성 중...
echo --------------------------------------------
python lotto_predictor2.py
if errorlevel 1 goto :error_step3
echo.

echo ============================================
echo   모든 단계가 성공적으로 끝났습니다!
echo   'recommended_lotto_15.txt' 파일을 확인해 보세요.
echo ============================================
echo.
pause
exit /b 0

:error_step0
echo.
echo [오류] 0단계 실패! 인터넷 연결이나 동행복권 사이트 상태를 확인해 주세요.
pause
exit /b 1

:error_step1
echo.
echo [오류] 1단계 실패! 통계 계산(update_lotto_feature.py) 중 문제가 발생했습니다.
pause
exit /b 1

:error_step2
echo.
echo [오류] 2단계 실패! 엑셀 서식 작업(gemini-code-1785640123148.py) 중 문제가 발생했습니다.
pause
exit /b 1

:error_step3
echo.
echo [오류] 3단계 실패! 번호 예측(lotto_predictor2.py) 중 문제가 발생했습니다.
pause
exit /b 1
