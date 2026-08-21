@echo off
REM ==========================================================
REM  W Clinic ตลาดไท - CASE 2 : HIFU
REM  รันบน Windows ที่มี CapCut เท่านั้น
REM  ใช้: ดับเบิลคลิกไฟล์นี้ หรือเปิด cmd แล้วพิมพ์ run_windows.bat
REM  ใส่ draft root เองได้:  run_windows.bat "E:\CapCut\Drafts"
REM ==========================================================
setlocal
cd /d "%~dp0\..\.."

set S=.claude\skills\capcut-edit-builder\scripts
set J=jobs\wclinic-hifu-05-08-69\plan

echo [1/5] ตรวจ Python
python --version >nul 2>&1
if errorlevel 1 (
  echo    ไม่พบ Python - ติดตั้งจาก https://python.org แล้วติ๊ก "Add to PATH"
  goto :fail
)

echo [2/5] ตรวจ ffprobe
ffprobe -version >nul 2>&1
if errorlevel 1 (
  echo    ไม่พบ ffprobe - ติดตั้ง ffmpeg แล้วใส่ใน PATH
  echo    winget install Gyan.FFmpeg   ^(แล้วเปิด cmd ใหม่^)
  goto :fail
)

echo [3/5] โหลดไฟล์จาก Dropbox
python %S%\fetch_media.py %J%\media.json
if errorlevel 1 goto :fail

echo [4/5] คำนวณความยาวรูปนิ่งซีน 2 จากเสียงจริง
python %S%\fit_stills.py %J%\edit_plan.json --write
if errorlevel 1 goto :fail

echo [5/5] สร้าง CapCut draft  ^(ปิด CapCut ก่อน^)
if "%~1"=="" (
  python %S%\build_draft.py %J%\edit_plan.json
) else (
  python %S%\build_draft.py %J%\edit_plan.json --draft-root "%~1"
)
if errorlevel 1 goto :fail

echo.
echo เสร็จแล้ว - เปิด CapCut แล้วดูว่าเห็นโปรเจกต์ wclinic-hifu-05-08-69 ไหม
echo ถ้าไม่เห็น ให้รัน:  python %S%\doctor.py --expect wclinic-hifu-05-08-69
goto :end

:fail
echo.
echo หยุดกลางทาง - อ่านข้อความ error ด้านบน
:end
pause
endlocal
