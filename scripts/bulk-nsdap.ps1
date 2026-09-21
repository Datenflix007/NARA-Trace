[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Destination,

    [ValidateSet('Metadata', 'FullDataset')]
    [string]$Mode = 'Metadata',

    [switch]$ConfirmFullDataset
)

$ErrorActionPreference = 'Stop'
$aws = Get-Command aws -ErrorAction SilentlyContinue
if ($null -eq $aws) {
    throw 'AWS CLI wurde nicht gefunden. Installiere zuerst AWS CLI v2 und starte dieses Skript erneut.'
}

if ($Mode -eq 'FullDataset' -and -not $ConfirmFullDataset) {
    throw 'Der Vollbestand enthaelt TIFFs und PDFs in sehr grossem Umfang. Wiederhole bewusst mit -Mode FullDataset -ConfirmFullDataset.'
}

$target = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Path $target -Force | Out-Null

$arguments = @('s3', 'sync', 's3://nara-nsdap/', $target, '--no-sign-request', '--only-show-errors')
if ($Mode -eq 'Metadata') {
    # JSON contains NARA's OCR and frame provenance. It supports local search
    # without an accidental download of the 16+ million image objects.
    $arguments += @('--exclude', '*', '--include', '*.json')
}

Write-Host "NARA NSDAP Bulk-Download: $Mode"
Write-Host "Ziel: $target"
if ($Mode -eq 'Metadata') {
    Write-Host 'Es werden nur Roll-JSON-Dateien mit OCR und Provenienz geladen, keine TIFFs oder PDFs.'
    Write-Warning 'Auch der JSON-Bulkbestand ist deutlich groesser als der von NARATrace verwaltete SQLite-Index.'
} else {
    Write-Warning 'Der Vollbestand ist sehr gross und kann erheblichen lokalen Speicher beanspruchen.'
}

& $aws.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "AWS CLI wurde mit Exit-Code $LASTEXITCODE beendet."
}
