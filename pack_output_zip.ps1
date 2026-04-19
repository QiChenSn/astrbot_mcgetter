param(
    [int]$Threads = 0,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$modsDir = Join-Path $scriptDir "mods"
$kubejsDir = Join-Path $scriptDir "kubejs"
$vineflowerJar = Join-Path $scriptDir "vineflower.jar"
$outputZip = Join-Path $scriptDir "output.zip"

if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $LogFile = Join-Path $scriptDir "pack_output_zip.last.log"
}

if (Test-Path -LiteralPath $LogFile) {
    Remove-Item -LiteralPath $LogFile -Force -ErrorAction SilentlyContinue
}

$script:ProgressPercent = 0
$script:ProgressStatus = "Starting"

function Get-ProgressBarText {
    param(
        [int]$Percent,
        [string]$Status
    )

    $width = 30
    $p = [Math]::Min(100, [Math]::Max(0, $Percent))
    $filled = [Math]::Floor($width * $p / 100)
    $empty = $width - $filled
    $bar = ("#" * $filled) + ("-" * $empty)
    return ("[PROGRESS] [{0}] {1,3}% {2}" -f $bar, $p, $Status)
}

function Render-LiveView {
    if ($Host.Name -eq "ConsoleHost") {
        Clear-Host
    }

    if (Test-Path -LiteralPath $LogFile) {
        Get-Content -LiteralPath $LogFile -Tail 50
    }

    Write-Host ""
    Write-Host (Get-ProgressBarText -Percent $script:ProgressPercent -Status $script:ProgressStatus)
}

function Write-Log {
    param(
        [ValidateSet("INFO", "WARN", "ERROR", "OK")]
        [string]$Level,
        [string]$Message
    )

    $line = "[{0}] {1}" -f $Level, $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Render-LiveView
}

function Set-ProgressState {
    param(
        [int]$Percent,
        [string]$Status
    )

    $script:ProgressPercent = [Math]::Min(100, [Math]::Max(0, $Percent))
    $script:ProgressStatus = $Status
    Render-LiveView
}

if ($Threads -le 0) {
    # Default to half cores to reduce UI lag on user machines.
    $Threads = [Math]::Max(1, [Math]::Floor([Environment]::ProcessorCount / 2))
}
if ($Threads -gt 8) {
    $Threads = 8
}

if (-not (Test-Path -LiteralPath $modsDir -PathType Container)) {
    Write-Log -Level "ERROR" -Message "Missing mods directory: $modsDir"
    exit 1
}
if (-not (Test-Path -LiteralPath $kubejsDir -PathType Container)) {
    Write-Log -Level "ERROR" -Message "Missing kubejs directory: $kubejsDir"
    exit 1
}
if (-not (Test-Path -LiteralPath $vineflowerJar -PathType Leaf)) {
    Write-Log -Level "ERROR" -Message "Missing vineflower.jar: $vineflowerJar"
    exit 1
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Log -Level "ERROR" -Message "Java not found in PATH"
    exit 1
}

$workRoot = Join-Path $env:TEMP ("mcpack_{0}" -f [guid]::NewGuid().ToString("N").Substring(0, 8))
$workMods = Join-Path $workRoot "mods"
$workKubejs = Join-Path $workRoot "kubejs"

try {
    Set-ProgressState -Percent 2 -Status "Preparing workspace"
    New-Item -ItemType Directory -Path $workMods -Force | Out-Null
    New-Item -ItemType Directory -Path $workKubejs -Force | Out-Null

    Write-Log -Level "INFO" -Message "Prepare temporary workspace"
    Set-ProgressState -Percent 10 -Status "Copy kubejs"
    Write-Log -Level "INFO" -Message "Copy kubejs (exclude assets)..."

    $null = robocopy $kubejsDir $workKubejs /E /XD (Join-Path $kubejsDir "assets")
    $roboRc = $LASTEXITCODE
    if ($roboRc -ge 8) {
        Write-Log -Level "ERROR" -Message "Robocopy failed, code=$roboRc"
        exit 1
    }

    # Safety pass: remove any directory named assets.
    Get-ChildItem -LiteralPath $workKubejs -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq "assets" } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }

    $jars = Get-ChildItem -LiteralPath $modsDir -File -Filter "*.jar" -ErrorAction SilentlyContinue
    $jarCount = $jars.Count
    Set-ProgressState -Percent 20 -Status "Prepare decompile"
    Write-Log -Level "INFO" -Message ("Jars found: {0}, threads: {1}" -f $jarCount, $Threads)

    if ($jarCount -eq 0) {
        Write-Log -Level "WARN" -Message "No jars found under mods"
    }
    else {
        # Use Vineflower's own batch mode with a speed-first option set.
        $vfArgs = @(
            "--folder",
            "--threads=$Threads",
            "-dgs=0", # decompile-generics off
            "-din=0", # decompile-inner off
            "-rsy=0", # keep synthetic markers (less post-processing)
            "-rbr=0", # keep bridge markers (less post-processing)
            "--silent" # keep this last among options; it ends option parsing in Vineflower CLI
        )
        foreach ($jar in $jars) {
            $vfArgs += $jar.FullName
        }
        $vfArgs += $workMods

        Set-ProgressState -Percent 30 -Status "Running Vineflower"
        Write-Log -Level "INFO" -Message "Running Vineflower batch decompile..."
        & java -jar $vineflowerJar @vfArgs
        $vfRc = $LASTEXITCODE
        if ($vfRc -ne 0) {
            throw "Vineflower batch decompile failed with exit code $vfRc"
        }

        Set-ProgressState -Percent 80 -Status "Post-processing outputs"

        # Safety pass: remove any directory named assets under decompiled mods output.
        Get-ChildItem -LiteralPath $workMods -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ieq "assets" } |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
    }

    if (Test-Path -LiteralPath $outputZip) {
        Remove-Item -LiteralPath $outputZip -Force
    }

    Set-ProgressState -Percent 88 -Status "Building zip"
    Write-Log -Level "INFO" -Message "Building output.zip (fast mode)..."
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $workRoot,
        $outputZip,
        [System.IO.Compression.CompressionLevel]::Fastest,
        $false
    )

    Set-ProgressState -Percent 100 -Status "Done"
    Write-Log -Level "OK" -Message "Build complete: $outputZip"
    Write-Log -Level "OK" -Message "output.zip contains: mods + kubejs (assets removed)"
    Write-Log -Level "INFO" -Message ("Vineflower batch finished, jars processed: {0}" -f $jarCount)

    exit 0
}
catch {
    Set-ProgressState -Percent $script:ProgressPercent -Status "Failed"
    Write-Log -Level "ERROR" -Message $_.Exception.Message
    exit 1
}
finally {
    if (Test-Path -LiteralPath $workRoot) {
        Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
