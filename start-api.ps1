Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
az login
venv\Scripts\uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000