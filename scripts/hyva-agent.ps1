param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("health", "transform-file", "transform-folder", "repo-scan", "repo-convert-dry-run")]
    [string]$Action,

    [string]$ApiUrl = "https://magento-ai-agent.onrender.com",
    [string]$Token,

    [string]$InputFile,
    [string]$OutputFile,

    [string]$InputRoot,
    [string]$OutputRoot,

    [string]$RepoPath = "/opt/render/project/src",
    [int]$MaxFiles = 100,
    [string]$ModifiedAfter,
    [string]$ModifiedBefore,

    [string]$BusinessContext = "Keep pricing, tax, promo, stock, and customer-group logic unchanged.",
    [switch]$PreserveBusinessLogic = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AuthHeaders {
    param([string]$TokenValue)

    if ([string]::IsNullOrWhiteSpace($TokenValue)) {
        $TokenValue = $env:MAGENTO_API_TOKEN
    }

    if ([string]::IsNullOrWhiteSpace($TokenValue)) {
        throw "Missing token. Pass -Token or set MAGENTO_API_TOKEN env var."
    }

    return @{
        "Authorization" = "Bearer $TokenValue"
        "Content-Type"  = "application/json"
    }
}

function Invoke-AgentPost {
    param(
        [string]$Uri,
        [hashtable]$Headers,
        [string]$Body
    )

    return Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers -Body $Body
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -ItemType Directory -Force | Out-Null
    }
}

function Convert-SingleFile {
    param(
        [string]$FilePath,
        [string]$OutPath,
        [string]$BaseUrl,
        [hashtable]$Headers
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        throw "Input file not found: $FilePath"
    }

    $parent = Split-Path -Parent $OutPath
    Ensure-Directory -Path $parent

    $content = Get-Content -LiteralPath $FilePath -Raw
    $body = @{ prompt = $content } | ConvertTo-Json -Compress

    $response = Invoke-AgentPost -Uri "$BaseUrl/v1/hyva-transform" -Headers $Headers -Body $body

    if ([string]::IsNullOrWhiteSpace($response.transformed_template)) {
        throw "API returned empty transformed_template for file: $FilePath"
    }

    $response.transformed_template | Set-Content -LiteralPath $OutPath -Encoding UTF8

    [PSCustomObject]@{
        input      = $FilePath
        output     = $OutPath
        request_id = $response.request_id
        model      = $response.model
    }
}

switch ($Action) {
    "health" {
        $health = Invoke-RestMethod -Method Get -Uri "$ApiUrl/health"
        $health | ConvertTo-Json -Depth 6
        break
    }

    "transform-file" {
        if ([string]::IsNullOrWhiteSpace($InputFile) -or [string]::IsNullOrWhiteSpace($OutputFile)) {
            throw "For transform-file, pass -InputFile and -OutputFile."
        }

        $headers = Get-AuthHeaders -TokenValue $Token
        $result = Convert-SingleFile -FilePath $InputFile -OutPath $OutputFile -BaseUrl $ApiUrl -Headers $headers
        $result | ConvertTo-Json -Depth 6
        break
    }

    "transform-folder" {
        if ([string]::IsNullOrWhiteSpace($InputRoot) -or [string]::IsNullOrWhiteSpace($OutputRoot)) {
            throw "For transform-folder, pass -InputRoot and -OutputRoot."
        }

        if (-not (Test-Path -LiteralPath $InputRoot)) {
            throw "InputRoot not found: $InputRoot"
        }

        $headers = Get-AuthHeaders -TokenValue $Token
        Ensure-Directory -Path $OutputRoot

        $patterns = @("*.phtml", "*.xml", "*.js")
        $converted = @()

        foreach ($pattern in $patterns) {
            Get-ChildItem -Path $InputRoot -Recurse -File -Filter $pattern | ForEach-Object {
                $src = $_.FullName
                $relative = $src.Substring($InputRoot.Length).TrimStart('\\', '/')
                $dst = Join-Path $OutputRoot $relative

                try {
                    $item = Convert-SingleFile -FilePath $src -OutPath $dst -BaseUrl $ApiUrl -Headers $headers
                    Write-Host "OK  $relative"
                    $converted += $item
                }
                catch {
                    Write-Host "ERR $relative :: $($_.Exception.Message)"
                }
            }
        }

        [PSCustomObject]@{
            action = "transform-folder"
            input_root = $InputRoot
            output_root = $OutputRoot
            converted_count = $converted.Count
            files = $converted
        } | ConvertTo-Json -Depth 8
        break
    }

    "repo-scan" {
        $headers = Get-AuthHeaders -TokenValue $Token
        $payload = @{
            repo_path = $RepoPath
            max_files = $MaxFiles
        }

        if (-not [string]::IsNullOrWhiteSpace($ModifiedAfter)) {
            $payload.modified_after = $ModifiedAfter
        }
        if (-not [string]::IsNullOrWhiteSpace($ModifiedBefore)) {
            $payload.modified_before = $ModifiedBefore
        }

        $body = $payload | ConvertTo-Json -Compress
        $response = Invoke-AgentPost -Uri "$ApiUrl/v1/repo/scan" -Headers $headers -Body $body
        $response | ConvertTo-Json -Depth 8
        break
    }

    "repo-convert-dry-run" {
        $headers = Get-AuthHeaders -TokenValue $Token
        $payload = @{
            repo_path = $RepoPath
            dry_run = $true
            run_tests = $false
            max_files = $MaxFiles
            business_context = $BusinessContext
            preserve_business_logic = [bool]$PreserveBusinessLogic
        }

        if (-not [string]::IsNullOrWhiteSpace($ModifiedAfter)) {
            $payload.modified_after = $ModifiedAfter
        }
        if (-not [string]::IsNullOrWhiteSpace($ModifiedBefore)) {
            $payload.modified_before = $ModifiedBefore
        }

        $body = $payload | ConvertTo-Json -Compress
        $response = Invoke-AgentPost -Uri "$ApiUrl/v1/repo/convert" -Headers $headers -Body $body
        $response | ConvertTo-Json -Depth 10
        break
    }
}
