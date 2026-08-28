<#
.SYNOPSIS
    ตรวจเครื่อง Windows ว่าพร้อมรัน skill capcut-edit-builder จาก Claude Code ในเทอร์มินัลหรือยัง

.DESCRIPTION
    เช็คของที่ skill ต้องใช้จริง ๆ — git, python, ffprobe, โฟลเดอร์ draft ของ CapCut —
    แล้วบอกว่าอันไหนขาดและติดตั้งยังไง สคริปต์นี้ไม่แก้ไฟล์ในโปรเจกต์
    และไม่ติดตั้งอะไรเองถ้าไม่สั่ง -Install

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\setup.ps1
    powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Install
#>

param(
    # ติดตั้งของที่ขาดให้เลย (ffmpeg ผ่าน winget, ไลบรารีตัดพยางค์ไทยผ่าน pip)
    [switch]$Install,
    # ลงไลบรารี Whisper ด้วย — ก้อนใหญ่ ลงเฉพาะตอนต้องถอดเสียงเอง
    [switch]$Whisper
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$scripts = Join-Path $repo '.claude\skills\capcut-edit-builder\scripts'
$missing = @()

function Test-Tool($name, $cmd, $howto) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host ("  [ok]   {0,-10} {1}" -f $name, $found.Source)
        return $true
    }
    Write-Host ("  [ขาด]  {0,-10} {1}" -f $name, $howto) -ForegroundColor Yellow
    $script:missing += $name
    return $false
}

Write-Host "`n== เครื่องมือที่ต้องมี ==" -ForegroundColor Cyan
Test-Tool 'git'     'git'     'winget install Git.Git' | Out-Null
$hasPython = Test-Tool 'python'  'python'  'winget install Python.Python.3.12'
$hasFfprobe = Test-Tool 'ffprobe' 'ffprobe' 'winget install Gyan.FFmpeg'
Test-Tool 'claude'  'claude'  'npm install -g @anthropic-ai/claude-code' | Out-Null

if ($Install -and -not $hasFfprobe) {
    Write-Host "`nกำลังติดตั้ง ffmpeg..." -ForegroundColor Cyan
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "ติดตั้งแล้ว — ต้อง 'ปิดเทอร์มินัลแล้วเปิดใหม่' PATH ถึงจะเห็น ffprobe" -ForegroundColor Yellow
}

if ($Install -and $hasPython) {
    Write-Host "`nกำลังติดตั้งไลบรารีตัดพยางค์ไทย (สำหรับซับคาราโอเกะ)..." -ForegroundColor Cyan
    python -m pip install --quiet --upgrade pythainlp python-crfsuite
    if ($Whisper) {
        Write-Host "กำลังติดตั้ง faster-whisper (ก้อนใหญ่ ใช้เวลาสักพัก)..." -ForegroundColor Cyan
        python -m pip install --quiet --upgrade faster-whisper
    }
}

# doctor.py คือคำตอบว่า CapCut เครื่องนี้อ่าน draft จากโฟลเดอร์ไหน ค่า default
# ใน build_draft.py เป็นแค่การเดา — CapCut ย้ายโฟลเดอร์นี้มาหลายเวอร์ชันแล้ว
if ($hasPython) {
    Write-Host "`n== โฟลเดอร์ draft ของ CapCut ==" -ForegroundColor Cyan
    python (Join-Path $scripts 'doctor.py')
} else {
    Write-Host "`nข้าม doctor.py เพราะยังไม่มี python" -ForegroundColor Yellow
}

Write-Host "`n== สรุป ==" -ForegroundColor Cyan
if ($missing.Count -gt 0) {
    Write-Host ("ยังขาด: " + ($missing -join ', ')) -ForegroundColor Yellow
    Write-Host "ลงให้ครบก่อน แล้วรันสคริปต์นี้ซ้ำ (หรือรันด้วย -Install)"
} else {
    Write-Host "ครบแล้ว" -ForegroundColor Green
}
Write-Host "`nขั้นต่อไป: cd $repo แล้วพิมพ์  claude"
Write-Host "ในเซสชัน ให้พูดงานที่จะทำได้เลย เช่น 'สร้าง draft ของ jobs\wclinic-hifu-05-08-69'`n"
