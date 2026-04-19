param(
    [int]$Threads = 0
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$modsDir = Join-Path $scriptDir "mods"
$kubejsDir = Join-Path $scriptDir "kubejs"
$vineflowerJar = Join-Path $scriptDir "vineflower.jar"
$outputZip = Join-Path $scriptDir "output.zip"

if ($Threads -le 0) {
    # Default to half cores to reduce UI lag on user machines.
    $Threads = [Math]::Max(1, [Math]::Floor([Environment]::ProcessorCount / 2))
}
if ($Threads -gt 8) {
    $Threads = 8
}

if (-not (Test-Path -LiteralPath $modsDir -PathType Container)) {
    Write-Host "[ERROR] Missing mods directory: $modsDir"
    exit 1
}
if (-not (Test-Path -LiteralPath $kubejsDir -PathType Container)) {
    Write-Host "[ERROR] Missing kubejs directory: $kubejsDir"
    exit 1
}
if (-not (Test-Path -LiteralPath $vineflowerJar -PathType Leaf)) {
    Write-Host "[ERROR] Missing vineflower.jar: $vineflowerJar"
    exit 1
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Java not found in PATH"
    exit 1
}

$workRoot = Join-Path $env:TEMP ("mcpack_{0}" -f [guid]::NewGuid().ToString("N").Substring(0, 8))
$workMods = Join-Path $workRoot "mods"
$workKubejs = Join-Path $workRoot "kubejs"

try {
    New-Item -ItemType Directory -Path $workMods -Force | Out-Null
    New-Item -ItemType Directory -Path $workKubejs -Force | Out-Null

    Write-Host "[INFO] Work dir: $workRoot"
    Write-Host "[INFO] Copy kubejs (exclude assets)..."

    $null = robocopy $kubejsDir $workKubejs /E /XD (Join-Path $kubejsDir "assets")
    $roboRc = $LASTEXITCODE
    if ($roboRc -ge 8) {
        Write-Host "[ERROR] Robocopy failed, code=$roboRc"
        exit 1
    }

    # Safety pass: remove any directory named assets.
    Get-ChildItem -LiteralPath $workKubejs -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq "assets" } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }

    $jars = Get-ChildItem -LiteralPath $modsDir -File -Filter "*.jar" -ErrorAction SilentlyContinue
    Write-Host ("[INFO] Jars found: {0}, parallel threads: {1}" -f $jars.Count, $Threads)

    $running = @()
    $results = @()
    $pending = [System.Collections.Generic.Queue[object]]::new()
    foreach ($jar in $jars) {
        $pending.Enqueue($jar)
    }

    while ($pending.Count -gt 0 -or $running.Count -gt 0) {
        while ($pending.Count -gt 0 -and $running.Count -lt $Threads) {
            $jar = $pending.Dequeue()
            Write-Host ("[INFO] Decompile start: {0}" -f $jar.Name)

            $job = Start-Job -ScriptBlock {
                param(
                    [string]$JarPath,
                    [string]$JarName,
                    [string]$OutRoot,
                    [string]$Vineflower
                )

                $ErrorActionPreference = "Stop"
                $baseName = [System.IO.Path]::GetFileNameWithoutExtension($JarName)
                $outDir = Join-Path $OutRoot $baseName
                New-Item -ItemType Directory -Path $outDir -Force | Out-Null

                & java -jar $Vineflower $JarPath $outDir *> $null
                $rc = $LASTEXITCODE
                if ($rc -ne 0) {
                    Remove-Item -LiteralPath $outDir -Recurse -Force -ErrorAction SilentlyContinue
                    return [PSCustomObject]@{ Name = $JarName; Success = $false }
                }

                Get-ChildItem -LiteralPath $outDir -Directory -Recurse -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -ieq "assets" } |
                    ForEach-Object {
                        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                    }

                return [PSCustomObject]@{ Name = $JarName; Success = $true }
            } -ArgumentList $jar.FullName, $jar.Name, $workMods, $vineflowerJar

            $running += $job
        }

        if ($running.Count -gt 0) {
            $done = Wait-Job -Job $running -Any
            if ($null -ne $done) {
                $result = Receive-Job -Job $done
                Remove-Job -Job $done -Force
                $running = @($running | Where-Object { $_.Id -ne $done.Id })

                if ($null -ne $result) {
                    $results += $result
                    if ($result.Success) {
                        Write-Host ("[OK] Decompile done: {0}" -f $result.Name)
                    }
                    else {
                        Write-Host ("[WARN] Decompile failed: {0}" -f $result.Name)
                    }
                }
            }
        }
    }

    $jarCount = $results.Count
    $failCount = ($results | Where-Object { -not $_.Success }).Count
    Write-Host ("[INFO] Decompile summary: total={0}, failed={1}" -f $jarCount, $failCount)

    if (Test-Path -LiteralPath $outputZip) {
        Remove-Item -LiteralPath $outputZip -Force
    }

    Write-Host "[INFO] Building output.zip..."
    Compress-Archive -Path @($workMods, $workKubejs) -DestinationPath $outputZip -Force

    Write-Host "[OK] Build complete: $outputZip"
    Write-Host "[OK] output.zip contains: mods + kubejs (assets removed)"

    if ($failCount -gt 0) {
        Write-Host "[WARN] Some jars failed to decompile. Upload package is still generated."
    }

    exit 0
}
catch {
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message)
    exit 1
}
finally {
    if (Test-Path -LiteralPath $workRoot) {
        Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
