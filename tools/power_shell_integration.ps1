function Invoke-CodeFix {
    param(
        [Parameter(Mandatory=$true)]
        [string] $Cmd,

        [string] $BackendUrl = "http://localhost:8000/api/diagnose",
        [string] $Filename = "last-run.out",
        [string] $Language = "bash"
    )

    $tempFile = Join-Path $env:TEMP "codefix_stderr.txt"
    # Run the command and capture stderr
    # For PowerShell you can redirect streams
    iex "$Cmd 2> $tempFile"
    $stderr = Get-Content $tempFile -Raw

    # Build a minimal payload
    $payload = @{
        filename = $Filename
        language = $Language
        code = ""
        stderr = $stderr
        mode = "quick"
        persona = "expert"
    } | ConvertTo-Json

    try {
        $resp = Invoke-RestMethod -Uri $BackendUrl -Method Post -Body $payload -ContentType "application/json"
        Write-Host "CodeFix AI Diagnosis:" -ForegroundColor Cyan
        Write-Host $resp.diagnosis
    } catch {
        Write-Host "Error contacting CodeFix backend: $_" -ForegroundColor Red
    }
}
