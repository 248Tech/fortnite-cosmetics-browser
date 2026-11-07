@echo off
REM Fortnite Cosmetics Browser by 248Tech - https://github.com/248Tech/fortnite-cosmetics-browser
cd /d "%~dp0"
python -c "import PIL" 2>nul || python -m pip install --user -r requirements.txt
start "" pythonw fortnite_cosmetics_browser.pyw
