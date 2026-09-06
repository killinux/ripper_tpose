<#
.SYNOPSIS
  Render dance previews for exported ROE PMX models.

.DESCRIPTION
  Imports <id>\blend\pmx\<stem>\<stem>.pmx together with a VMD and writes
  <id>\blend\pmx\<stem>_dance.mp4 (plus the .blend it was rendered from).

  A preview older than its PMX is skipped-with-a-warning rather than silently
  kept: the rig defects only show in motion, so a stale mp4 gets read as a
  defect in a model that has already been fixed. Use -Force to redo one anyway.

.EXAMPLE
  .\render_pmx_dance.ps1 -Only a02,g12,j10

.EXAMPLE
  .\render_pmx_dance.ps1 -PerCharacter     # one per character, highest outfit number

.EXAMPLE
  .\render_pmx_dance.ps1 -Stale            # everything whose preview is out of date
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\roe_exports",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$Vmd = "E:\Downloads\mmd\来杯好茶摇一摇2026.6.14by小王动画\适配【原神】芙宁娜.vmd",
    [string]$Bgm = "E:\Downloads\mmd\来杯好茶摇一摇2026.6.14by小王动画\BGM.wav",
    [string[]]$Only,
    [int]$Frames = 0,
    # One Blender per model. A 2291-frame EEVEE render is several minutes, so
    # rendering a handful one after another is an afternoon; four at once is not.
    [int]$Parallel = 4,
    # One video per character rather than per outfit: the letter is the
    # character and the number is the outfit, so this keeps the highest number.
    [switch]$PerCharacter,
    [switch]$Stale,
    [switch]$List,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$workerPy = Join-Path $scriptDir 'render_pmx_dance.py'
foreach ($required in @($BlenderExe, $workerPy, $Vmd)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "not found: $required"
    }
}
if ($Bgm -and -not (Test-Path -LiteralPath $Bgm)) { $Bgm = '-' }

# One job per PMX, not per directory: an outfit variant lives beside the base
# model in the same character folder (a08 holds pc_a08_hd and pc_a08_outfit1_hd).
$jobs = @()
foreach ($dir in Get-ChildItem -LiteralPath $SourceRoot -Directory | Sort-Object Name) {
    if ($Only -and $dir.Name -notin $Only) { continue }
    foreach ($pmx in Get-ChildItem -LiteralPath (Join-Path $dir.FullName 'blend\pmx') `
            -Filter '*.pmx' -Recurse -ErrorAction SilentlyContinue | Sort-Object Name) {
        $stem = [IO.Path]::GetFileNameWithoutExtension($pmx.Name)
        $mp4 = Join-Path $dir.FullName ("blend\pmx\{0}_dance.mp4" -f $stem)
        $exists = Test-Path -LiteralPath $mp4
        $current = $exists -and
            ((Get-Item -LiteralPath $mp4).LastWriteTime -ge $pmx.LastWriteTime)
        # pc_a08_outfit1_hd -> letter a, outfit 8, variant 1
        $code = if ($stem -match '^pc_([a-z])(\d+)(?:_outfit(\d+))?') {
            [pscustomobject]@{ Letter = $Matches[1]; Number = [int]$Matches[2]
                               Variant = if ($Matches[3]) { [int]$Matches[3] } else { 0 } }
        } else { $null }
        $jobs += [pscustomobject]@{
            Id = $dir.Name; Stem = $stem; Code = $code; Exists = $exists
            Pmx = $pmx.FullName; Mp4 = $mp4; UpToDate = $current
        }
    }
}

if ($PerCharacter) {
    # The letter is the character and the number is the outfit, so one video per
    # letter means the highest-numbered outfit that actually has a PMX.
    $jobs = @($jobs | Where-Object { $_.Code } |
        Group-Object { $_.Code.Letter } |
        ForEach-Object {
            $_.Group | Sort-Object { $_.Code.Number }, { $_.Code.Variant } |
                Select-Object -Last 1
        } | Sort-Object { $_.Code.Letter })
}
if ($Stale) { $jobs = @($jobs | Where-Object { -not $_.UpToDate }) }

if ($List) {
    $jobs | ForEach-Object {
        $state = if ($_.UpToDate) { 'up to date' }
                 elseif ($_.Exists) { 'STALE     ' }
                 else { 'missing   ' }
        "{0,-22} {1}  {2}" -f $_.Stem, $state, $_.Mp4
    }
    return
}
if (-not $jobs) { Write-Host 'nothing to render'; return }

$todo = @($jobs | Where-Object { $Force -or -not $_.UpToDate })
foreach ($skipped in @($jobs | Where-Object { $_.UpToDate -and -not $Force })) {
    Write-Host ("{0}: up to date, skipping (use -Force to redo)" -f $skipped.Stem) `
        -ForegroundColor DarkGray
}
if (-not $todo) { Write-Host 'everything is up to date'; return }

$logDir = Join-Path ([IO.Path]::GetTempPath()) 'roe_dance_logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$running = @()
$queue = [System.Collections.Queue]::new(@($todo))
$done = 0
while ($queue.Count -gt 0 -or $running.Count -gt 0) {
    while ($queue.Count -gt 0 -and $running.Count -lt [Math]::Max(1, $Parallel)) {
        $job = $queue.Dequeue()
        $arguments = @('--background', '--python', $workerPy, '--',
                       $job.Pmx, $Vmd, $Bgm, $job.Mp4)
        if ($Frames -gt 0) { $arguments += [string]$Frames }
        $log = Join-Path $logDir ($job.Stem + '.log')
        $process = Start-Process -FilePath $BlenderExe -ArgumentList $arguments `
            -NoNewWindow -PassThru -RedirectStandardOutput $log `
            -RedirectStandardError (Join-Path $logDir ($job.Stem + '.err'))
        Write-Host ("start {0}" -f $job.Stem) -ForegroundColor Cyan
        $running += [pscustomobject]@{ Job = $job; Process = $process; Log = $log }
    }
    Start-Sleep -Seconds 5
    foreach ($slot in @($running | Where-Object { $_.Process.HasExited })) {
        $done++
        $text = if (Test-Path -LiteralPath $slot.Log) { Get-Content -LiteralPath $slot.Log -Raw } else { '' }
        if ($text -match 'ROE_DANCE_DONE') {
            $size = [math]::Round((Get-Item -LiteralPath $slot.Job.Mp4).Length / 1MB, 1)
            Write-Host ("[{0}/{1}] {2} -> {3} ({4} MB)" -f $done, $todo.Count,
                $slot.Job.Stem, $slot.Job.Mp4, $size) -ForegroundColor DarkGreen
        } else {
            Write-Host ("[{0}/{1}] {2} FAILED, see {3}" -f $done, $todo.Count,
                $slot.Job.Stem, $slot.Log) -ForegroundColor Red
        }
        $running = @($running | Where-Object { $_ -ne $slot })
    }
}
