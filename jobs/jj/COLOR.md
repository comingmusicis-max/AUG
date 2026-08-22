# JJ — ย้อมสี

Resolve Studio 21, ชื่อโปรเจกต์ `jj` (ตัวเล็ก)

## วิธีที่ง่ายที่สุด

คลิกขวาที่ `jobs\jj\color\run.bat` → **Run as administrator**

มันไล่ให้ครบทุกขั้น หยุดรอตอนที่ต้องกด Alt+S เอง แล้วให้ดูผล dry-run ก่อนถามว่า
จะลงจริงไหม ถ้าขั้นไหนพัง มันหยุดตรงนั้นพร้อมบอกสาเหตุ ไม่ไปต่อแบบครึ่ง ๆ กลาง ๆ

ต้องเป็น Administrator เพราะโฟลเดอร์ LUT ของ Resolve อยู่ใน ProgramData

## หรือรันทีละคำสั่ง

```bash
# 1. เช็กว่าต่อ Resolve ได้
python .claude/skills/davinci-color/scripts/doctor.py

# 2. สร้าง LUT ลงโฟลเดอร์ LUT ของ Resolve (เปิด terminal แบบ Administrator)
python .claude/skills/davinci-color/scripts/make_lut.py \
    .claude/skills/davinci-color/looks/golden_hour.json --install

# 3. ที่หน้า Color เลือกคลิปแรกบน V1 กด Alt+S ห้าครั้ง ให้ได้ 6 โหนด

# 4. ดูก่อนว่าจะเกิดอะไรขึ้น
python .claude/skills/davinci-color/scripts/apply_grade.py \
    jobs/jj/color/graph.json --dry-run

# 5. ลงจริง
python .claude/skills/davinci-color/scripts/apply_grade.py jobs/jj/color/graph.json

# 6. พอกราฟนิ่งแล้ว เก็บเป็นไฟล์ไว้ ไม่ให้หายอีก
python .claude/skills/davinci-color/scripts/export_grade.py \
    --project jj --clip 1 --out jobs/jj/color --name jj_golden_hour
```

ขั้น 3 กดมือครั้งเดียวพอ — `CopyGrades` ลากโครงสร้างโหนดไปให้คลิปที่เหลือเอง

พอมี `.drx` จากขั้น 6 แล้ว รอบหน้าข้ามขั้น 3 ได้เลย ใส่ใน `graph.json` แทน:

```json
{"select": {"all": true}, "drx": "jobs/jj/color/jj_golden_hour.drx"}
```

## สิ่งที่ต้องทำมือ

| ทำอะไร | ทำไมสคริปต์ทำให้ไม่ได้ |
|---|---|
| โหนด `05 SKY` — เปิดแล้ววาด gradient ที่ฟ้า | window/qualifier สั่งผ่าน API ไม่ได้เลย |
| บอกว่าคลิปไหนคือช็อตในร่ม | ผมดูฟุตเทจไม่ได้ ต้องนายชี้ |
| โหนด `06 TRIM` ตอนแมตช์ช็อตต่อช็อต | ต้องดูตาเทียบ |

ค่าที่ตั้งมือแล้วอยากให้ถาวร เขียนกลับลง `trims` ใน `graph.json` — มันรันหลัง `match` ก็เลยไม่โดนทับ

## สองไฟ สอง look

งานนี้ถ่ายสองสภาพแสง — ดาดฟ้าตอนพระอาทิตย์ตก กับเวทีในร่มไฟทังสเตน LUT ตัวเดียว
คุมทั้งคู่ไม่ได้ เลยมีสองตัว:

| look | ใช้กับ |
|---|---|
| `golden_hour.cube` | ดาดฟ้า ย้อนแสง — เป็นค่าตั้งต้นของทุกคลิป |
| `stage_indoor.cube` | เวทีในร่ม — ดึงส้มจากไฟทังสเตนคืน เติมคอนทราสต์ที่ห้องไม่มี |

สองตัวนี้ทำมาให้ตัดกันได้: ระดับดำห่างกัน 0.008 ผิวลงที่เดียวกันห่างกัน 0.010
ต่างกันแค่ white balance — ถ้าไม่คุมตรงนี้ รอยตัดระหว่างสองซีนจะอ่านเป็นความผิดพลาด

**สิ่งที่นายต้องทำ:** ดูว่าคลิปไหนคือช็อตในร่ม แล้วใส่ชื่อลงใน `trims` ของ `graph.json`

```bash
python .claude/skills/davinci-color/scripts/apply_grade.py jobs/jj/color/graph.json --list
```

เอาชื่อที่ได้ไปวางใน `"names": []` ตอนนี้มันว่างอยู่ สคริปต์เลยข้ามแล้วบอกว่าข้าม
ซึ่งปลอดภัยกว่าเดาเอง

## รันซ้ำได้

รันซ้ำหลังตัดใหม่ได้เลย สีกลับมาเหมือนเดิมเป๊ะ — สคริปต์มาร์กคลิปที่มันเกรดเอง
ด้วยสีส้มในไทม์ไลน์ รอบต่อไปมันจำได้ว่าอันไหนงานตัวเอง (ทับได้) อันไหนคนทำมือ
(ไม่ทับ ต้องสั่ง `--force`)

## เกรดเก่า

กราฟ 14 โหนดชุดเดิม (WB ด้วย Chromatic Adaptation 5721K → 6837K, HI LIGH, EXPOS,
EFX, SAT, layer mixer) ถูกลบไปแล้ว แต่ still `1.1.1`–`1.1.7` ในแกลเลอรียังเก็บ
เกรดนั้นไว้ — คลิกขวาที่ still แล้ว Apply Grade ได้ตลอด
