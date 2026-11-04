[CmdletBinding()]
param(
    [switch]$SkipSourceDownload,
    [switch]$SkipBrowser
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RuntimeRoot = Join-Path $RepoRoot 'oss-tools\runtime'
$SourceRoot = Join-Path $RuntimeRoot 'sources'
$EnvironmentRoot = Join-Path $RuntimeRoot 'environments'
$LockRoot = Join-Path $RepoRoot 'oss-tools\locks'
$BasePython = (Get-Command py -ErrorAction Stop).Source

$Sources = @(
    @{ Name = 'JobSpy'; Directory = 'JobSpy'; Url = 'https://github.com/speedyapply/JobSpy.git'; Commit = 'a606f9cf077c34f6ce6cbfcc76238f57b3c20671' },
    @{ Name = 'ats-scrapers'; Directory = 'ats-scrapers'; Url = 'https://github.com/kalil0321/ats-scrapers.git'; Commit = '6b44a1badc9bfbf5cf176f75265cc5729e520e99' },
    @{ Name = 'instahyre-scraper'; Directory = 'instahyre-scraper'; Url = 'https://github.com/omkarcloud/instahyre-scraper.git'; Commit = '16a64f440e39a1545ea1322e21c6d8ef654a3358' },
    @{ Name = 'internshala-scraper'; Directory = 'internshala-scraper'; Url = 'https://github.com/omkarcloud/internshala-scraper.git'; Commit = '4755e7c83ec565e456384dffede100e9dfdc6a3d' },
    @{ Name = 'shine-scraper'; Directory = 'shine-scraper'; Url = 'https://github.com/omkarcloud/shine-scraper.git'; Commit = 'ec9c0978b71ff502bf17e6b34fd0a64d150e410c' },
    @{ Name = 'crawl4ai'; Directory = 'crawl4ai'; Url = 'https://github.com/unclecode/crawl4ai.git'; Commit = '838869bdda93f25e6d50b3f50ae9577d9b19a586' }
)

function Invoke-External([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')"
    }
}

function Ensure-Source($Spec) {
    $Path = Join-Path $SourceRoot $Spec.Directory
    if (-not (Test-Path (Join-Path $Path '.git'))) {
        if (Test-Path $Path) { throw "Source directory exists but is not a Git checkout: $Path" }
        New-Item -ItemType Directory -Force -Path $SourceRoot | Out-Null
        Invoke-External 'git' @('clone', '--filter=blob:none', '--no-checkout', $Spec.Url, $Path)
        Invoke-External 'git' @('-C', $Path, 'checkout', '--detach', $Spec.Commit)
    }
    $Actual = (& git -C $Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $Actual -ne $Spec.Commit) {
        throw "Pinned source mismatch for $($Spec.Name): expected $($Spec.Commit), found $Actual. No checkout was reset."
    }
    return $Path
}

foreach ($Spec in $Sources) {
    if (-not $SkipSourceDownload) {
        [void](Ensure-Source $Spec)
        continue
    }
    $Path = Join-Path $SourceRoot $Spec.Directory
    if (-not (Test-Path (Join-Path $Path '.git'))) { throw "Pinned source checkout is missing: $Path" }
    $Actual = (& git -C $Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $Actual -ne $Spec.Commit) {
        throw "Pinned source mismatch for $($Spec.Name): expected $($Spec.Commit), found $Actual. No checkout was reset."
    }
}

$Installations = @(
    @{ Name = 'jobspy'; Python = Join-Path $RepoRoot 'backend\.source-tools-venv\Scripts\python.exe'; Environment = Join-Path $RepoRoot 'backend\.source-tools-venv'; Source = Join-Path $SourceRoot 'JobSpy'; Lock = Join-Path $LockRoot 'jobspy-py311.lock.txt' },
    @{ Name = 'ats'; Python = Join-Path $EnvironmentRoot 'ats\Scripts\python.exe'; Environment = Join-Path $EnvironmentRoot 'ats'; Source = Join-Path $SourceRoot 'ats-scrapers'; Lock = Join-Path $LockRoot 'ats-py311.lock.txt' },
    @{ Name = 'instahyre'; Python = Join-Path $EnvironmentRoot 'instahyre\Scripts\python.exe'; Environment = Join-Path $EnvironmentRoot 'instahyre'; Source = Join-Path $SourceRoot 'instahyre-scraper'; Lock = Join-Path $LockRoot 'instahyre-py311.lock.txt' },
    @{ Name = 'internshala'; Python = Join-Path $EnvironmentRoot 'internshala\Scripts\python.exe'; Environment = Join-Path $EnvironmentRoot 'internshala'; Source = Join-Path $SourceRoot 'internshala-scraper'; Lock = Join-Path $LockRoot 'internshala-py311.lock.txt' },
    @{ Name = 'shine'; Python = Join-Path $EnvironmentRoot 'shine\Scripts\python.exe'; Environment = Join-Path $EnvironmentRoot 'shine'; Source = Join-Path $SourceRoot 'shine-scraper'; Lock = Join-Path $LockRoot 'shine-py311.lock.txt' },
    @{ Name = 'crawl4ai'; Python = Join-Path $EnvironmentRoot 'crawl4ai\Scripts\python.exe'; Environment = Join-Path $EnvironmentRoot 'crawl4ai'; Source = Join-Path $SourceRoot 'crawl4ai'; Lock = Join-Path $LockRoot 'crawl4ai-py311.lock.txt' }
)

foreach ($Install in $Installations) {
    if (-not (Test-Path $Install.Python)) {
        if ($Install.Name -eq 'jobspy' -and (Test-Path $Install.Environment)) {
            throw "Existing JobSpy environment is missing its interpreter; refusing to replace it: $($Install.Environment)"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $Install.Environment -Parent) | Out-Null
        Invoke-External $BasePython @('-3.11', '-m', 'venv', $Install.Environment)
    }
    if (-not (Test-Path $Install.Lock)) { throw "Pinned lock file is missing: $($Install.Lock)" }
    if (-not (Test-Path $Install.Source)) { throw "Pinned source checkout is missing: $($Install.Source)" }
    Invoke-External $Install.Python @('-m', 'pip', 'install', '--requirement', $Install.Lock)
    if ($Install.Name -in @('jobspy', 'ats', 'crawl4ai')) {
        Invoke-External $Install.Python @('-m', 'pip', 'install', '--no-deps', '--editable', $Install.Source)
    }
}

if (-not $SkipBrowser) {
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RuntimeRoot 'browsers'
    New-Item -ItemType Directory -Force -Path $env:PLAYWRIGHT_BROWSERS_PATH | Out-Null
    $CrawlerPython = Join-Path $EnvironmentRoot 'crawl4ai\Scripts\python.exe'
    Invoke-External $CrawlerPython @('-m', 'playwright', 'install', 'chromium')
}

Write-Output 'OSS collector setup completed. No CareerOS services or job websites were started or contacted.'
