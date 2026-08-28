# ต่อ repo นี้เข้ากับ Claude Code ในเทอร์มินัล

เซสชันบนเว็บรันอยู่ในคอนเทนเนอร์ Linux — ไม่มี CapCut ไม่เห็นไดรฟ์ `D:` และโหลด
ฟุตเทจของงานลงเครื่องคุณไม่ได้ ที่นี่ใช้ **เขียนแผน** (`plan/edit_plan.json`,
`SCRIPT.md`) ได้ดี แต่ขั้นตอนที่แตะไฟล์จริง — โหลดมีเดีย, สร้าง draft, ทำซับ —
ต้องรันบนเครื่อง Windows ที่ลง CapCut ไว้ เอกสารนี้คือวิธีย้ายไปตรงนั้น

## ติดตั้งครั้งเดียว

1. **Node.js 18 ขึ้นไป** (ถ้ายังไม่มี)

   ```powershell
   winget install OpenJS.NodeJS.LTS
   ```

2. **Claude Code** แล้วล็อกอินด้วยบัญชีเดียวกับที่ใช้บนเว็บ

   ```powershell
   npm install -g @anthropic-ai/claude-code
   claude          # ครั้งแรกจะเปิดเบราว์เซอร์ให้ล็อกอิน
   ```

3. **โคลน repo พร้อมสลับไป branch งาน**

   ```powershell
   cd C:\work
   git clone https://github.com/comingmusicis-max/AUG.git
   cd AUG
   git checkout claude/claude-terminal-integration-9xxpbi
   ```

4. **เช็คว่าเครื่องพร้อม** — สคริปต์นี้เช็ค git / python / ffprobe แล้วรัน
   `doctor.py` เพื่อบอกว่า CapCut เครื่องนี้อ่าน draft จากโฟลเดอร์ไหนจริง ๆ

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\setup.ps1
   ```

   ถ้าขาดอะไร ใส่ `-Install` ให้ลงให้ (เพิ่ม `-Whisper` ถ้าต้องถอดเสียงเอง):

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Install
   ```

   ติดตั้ง ffmpeg เสร็จต้องปิดเทอร์มินัลแล้วเปิดใหม่ PATH ถึงจะเห็น `ffprobe`

## ใช้งานประจำวัน

เปิดเทอร์มินัลที่โฟลเดอร์ repo แล้วพิมพ์:

```powershell
cd C:\work\AUG
claude
```

Claude จะเห็น `.claude/skills/capcut-edit-builder/` เอง เพราะมันอยู่ในโฟลเดอร์ที่เปิด
— สั่งงานเป็นภาษาคนได้เลย เช่น

- `โหลดมีเดียแล้วสร้าง draft ของ jobs\wclinic-hifu-05-08-69`
- `แปะ brief งานใหม่มาให้ เดี๋ยวช่วยเขียน edit plan`
- `ทำซับคาราโอเกะจาก track 4 ของโปรเจกต์ wclinic-hifu`

`.claude/settings.json` อนุญาตสคริปต์ของ skill กับ `ffprobe` ไว้แล้ว จะได้ไม่ต้องกด
ยืนยันทุกคำสั่ง คำสั่งอื่นนอกลิสต์ยังถามเหมือนเดิม

## ลำดับที่สคริปต์ทำงาน

รันมือก็ได้ ถ้าอยากข้ามการคุยกับ Claude:

```powershell
$s = ".claude\skills\capcut-edit-builder\scripts"
python $s\fetch_media.py jobs\<งาน>\plan\media.json          # โหลด + probe
python $s\fit_stills.py  jobs\<งาน>\plan\edit_plan.json --write
python $s\build_draft.py jobs\<งาน>\plan\edit_plan.json
python $s\doctor.py --expect <ชื่อโปรเจกต์>                   # ถ้า CapCut ไม่ขึ้นรายการ
```

สามข้อที่พลาดบ่อย:

- **ปิด CapCut ก่อน build** — CapCut อุ้ม draft ไว้ในหน่วยความจำ แล้วเขียนทับตอนปิด
  `build_draft.py` เลยไม่ยอมรันตอนโปรแกรมเปิดอยู่
- **build สำเร็จแต่ CapCut ไม่ขึ้นรายการ** — รัน `doctor.py --expect <ชื่อ>` ก่อนเดา
  ถ้าไฟล์อยู่บนดิสก์แล้วยังไม่ขึ้น ให้ปิด CapCut สนิทแล้วเปิดใหม่ (มันอ่านโฟลเดอร์
  ตอนเปิดเท่านั้น) ถ้าไม่มีที่ไหนเลย ให้ส่ง `--draft-root` ตามที่ doctor บอก
- **ไฟล์มีเดียลง `D:\ClinicVideo\<งาน>\` เป็นค่า default** — แก้ที่ `dest` ใน `media.json`
  ถ้าเครื่องนี้ไม่มีไดรฟ์ D

## ส่งงานกลับขึ้น repo

แผนกับ `SCRIPT.md` ควร commit กลับ ส่วนฟุตเทจไม่ต้อง (ไฟล์ใหญ่ อยู่นอก repo อยู่แล้ว)

```powershell
git add jobs
git commit -m "..."
git push -u origin claude/claude-terminal-integration-9xxpbi
```

เซสชันบนเว็บกับในเทอร์มินัลใช้ branch เดียวกัน ทำงานสลับกันได้ ขอแค่ `git pull`
ก่อนเริ่มทุกครั้ง
