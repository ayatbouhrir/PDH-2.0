$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$projectRoot = Split-Path $PSScriptRoot -Parent
$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($uv) {
    $uvPath = $uv.Source
} else {
    $uvDir = Join-Path $projectRoot '.local\tools\uv'
    $uvPath = Join-Path $uvDir 'uv.exe'
    if (-not (Test-Path -LiteralPath $uvPath)) {
        if ($env:PROCESSOR_ARCHITECTURE -notin @('AMD64', 'ARM64')) {
            throw 'Windows 64 bits est requis.'
        }
        $target = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64-pc-windows-msvc' } else { 'x86_64-pc-windows-msvc' }
        $archiveName = "uv-$target.zip"
        $baseUrl = 'https://github.com/astral-sh/uv/releases/download/0.12.19'
        New-Item -ItemType Directory -Force -Path $uvDir | Out-Null
        $archivePath = Join-Path $uvDir $archiveName
        Write-Host 'Installation locale de uv et de Python si necessaire...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing "$baseUrl/$archiveName" -OutFile $archivePath
        $checksum = (Invoke-WebRequest -UseBasicParsing "$baseUrl/$archiveName.sha256").Content
        if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::ASCII.GetString($checksum) }
        $expected = ([string]$checksum).Trim().Split(' ')[0]
        $stream = [IO.File]::OpenRead($archivePath)
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '') }
        finally { $stream.Dispose(); $algorithm.Dispose() }
        if ($actual -ne $expected) {
            throw 'La verification SHA256 de uv a echoue. Relancez apres avoir verifie la connexion.'
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
        $safeRoot = [IO.Path]::GetFullPath($uvDir).TrimEnd('\') + '\'
        try {
            foreach ($entry in $zip.Entries) {
                $targetPath = [IO.Path]::GetFullPath([IO.Path]::Combine($uvDir, $entry.FullName))
                if (-not $targetPath.StartsWith($safeRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Chemin invalide dans une archive uv.' }
                if ([string]::IsNullOrEmpty($entry.Name)) {
                    [IO.Directory]::CreateDirectory($targetPath) | Out-Null
                } else {
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($targetPath)) | Out-Null
                    [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $targetPath, $true)
                }
            }
        } finally { $zip.Dispose() }
        if (-not (Test-Path -LiteralPath $uvPath)) { throw 'Archive uv incomplete.' }
    }
}
& $uvPath run --no-project --python 3.12 (Join-Path $projectRoot 'run.py') @args
exit $LASTEXITCODE
