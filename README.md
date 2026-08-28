# AUG — งานตัดต่อคลินิก

รันจริงบนเครื่อง Windows ผ่าน Claude Code ในเทอร์มินัล — วิธีต่อ: [SETUP-TERMINAL.md](SETUP-TERMINAL.md)
(ลัด: โคลน repo → `powershell -ExecutionPolicy Bypass -File tools\setup.ps1` → `claude`)

โครงสร้าง:

- `.claude/skills/capcut-edit-builder/` — สกิลสร้าง CapCut draft จาก brief (ต้องรันบน Windows ที่มี CapCut)
- `tools/setup.ps1` — เช็คเครื่อง Windows ว่าพร้อมรันสกิลหรือยัง (git/python/ffprobe + โฟลเดอร์ draft)
- `jobs/<งาน>/plan/media.json` — รายการไฟล์ที่ต้องโหลด
- `jobs/<งาน>/plan/edit_plan.json` — แผนไทม์ไลน์
- `jobs/<งาน>/SCRIPT.md` — สรุปไทม์ไลน์ + สิ่งที่ต้องทำมือ

งานปัจจุบัน (W Clinic ตลาดไท ออกกอง 05/08/69):

| งาน | เคส | ซีน | ไฟล์ |
|---|---|---|---|
| `jobs/wclinic-thread-lift-05-08-69/` | CASE 1 — ร้อยไหม V-Lift (แคมเปญวันแม่) | 5 | 12 |
| `jobs/wclinic-hifu-05-08-69/` | CASE 2 — ยกกระชับ HIFU | 3 | 10 |
