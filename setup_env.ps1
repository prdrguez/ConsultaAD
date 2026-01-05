Param(
    [switch]$InstallAdDeps
)

Write-Host "== Setup virtualenv and install dependencies =="

if (-not (Test-Path -Path .venv)) {
    Write-Host "Creating virtual environment in .venv..."
    python -m venv .venv
} else {
    Write-Host "Virtual environment .venv already exists."
}

Write-Host "Upgrading pip and installing requirements from requirements.txt..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if ($InstallAdDeps) {
    Write-Host "Installing optional AD deps: pyad, pywin32 (requires build tools)..."
    .\.venv\Scripts\python.exe -m pip install pyad pywin32
    Write-Host "Note: Installing pywin32 may require Windows build/runtime components."
}

Write-Host "Done. To activate the virtualenv in your current PowerShell session run:" 
Write-Host "    . \.venv\Scripts\Activate.ps1"
Write-Host "Then run: streamlit run consulta_ad_streamlit.py"
