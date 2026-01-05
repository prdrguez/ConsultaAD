@echo off
echo == Setup virtualenv and install dependencies ==

if not exist .venv (
  echo Creating virtual environment in .venv...
  python -m venv .venv
) else (
  echo Virtual environment .venv already exists.
)

echo Upgrading pip and installing requirements from requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

if "%1"=="-InstallAdDeps" (
  echo Installing optional AD deps: pyad, pywin32 (may require build/runtime components)...
  .venv\Scripts\python.exe -m pip install pyad pywin32
)

echo.
echo Done. To activate the virtualenv run:
echo    .\.venv\Scripts\activate.bat
echo Then run:
echo    streamlit run consulta_ad_streamlit.py
pause