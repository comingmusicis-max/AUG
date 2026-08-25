# AUG — งานตัดต่อคลินิก

โครงสร้าง:

- `.claude/skills/capcut-edit-builder/` — สกิลสร้าง CapCut draft จาก brief (ต้องรันบน Windows ที่มี CapCut)
- `jobs/<งาน>/plan/media.json` — รายการไฟล์ที่ต้องโหลด
- `jobs/<งาน>/plan/edit_plan.json` — แผนไทม์ไลน์
- `jobs/<งาน>/SCRIPT.md` — สรุปไทม์ไลน์ + สิ่งที่ต้องทำมือ

## งานทั้งหมด

| งาน | เคส | ซีน | ไฟล์ |
|---|---|---|---|
| `jobs/wclinic-thread-lift-05-08-69/` | W Clinic ตลาดไท — ร้อยไหม V-Lift (แคมเปญวันแม่) | 5 | 12 |
| `jobs/wclinic-hifu-05-08-69/` | W Clinic ตลาดไท — ยกกระชับ HIFU | 3 | 10 |
| `jobs/theface-13-07-69/` | THE FACE — ร้อยไหม Fix Face ยกกรอบหน้า | 7 | 18 |
| `jobs/vipha-filler-temple-03-08-69/` | Vipha Clinic — Filler ขมับ | 8 | 18 |
| `jobs/wrinkle-jaw-03-08-69/` | ริ้วรอย + กราม (ยังไม่ทราบชื่อคลินิก) | 7 | 25 |

สามงานล่างยังรอไฟล์เพิ่มก่อนจะปิดได้ — อ่านหัวข้อ "จุดที่ตีความไว้" ใน `SCRIPT.md` ของแต่ละงาน

## เกรดสีให้ทั้งงานเท่ากัน

```bat
python .claude\skills\capcut-edit-builder\scripts\match_grade.py D:\ClinicVideo\<งาน> --preview
python .claude\skills\capcut-edit-builder\scripts\match_grade.py D:\ClinicVideo\<งาน> --write
```

รันครั้งแรกวัดอย่างเดียว — ได้ `grade_report.json` กับภาพเทียบก่อน/หลังใน `grade_preview/`
รันครั้งที่สองเรนเดอร์ไฟล์ที่ปรับแล้วลง `graded/` ซึ่งเป็นโฟลเดอร์ที่ `media_dir` ในแผนชี้ไว้อยู่แล้ว

โทนที่ตั้งไว้ (สว่างขึ้น ขาวอมอุ่น ดำยกขึ้นเล็กน้อย สีลดลงนิดหน่อย) แก้ได้ที่ตัวแปร `SOFT`
บนหัวไฟล์ `match_grade.py` แล้วรัน `--preview` ดูใหม่
