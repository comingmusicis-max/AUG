# JJ — ย้อมสี

Resolve Studio 21, โปรเจกต์ `jj`, Timeline 1

**ไทม์ไลน์มีคลิปเดียว: `C0001.MP4` ยาวคลุมทั้ง 12 นาที** V2 ว่าง เสียงอยู่ A1 จากคลิปเดียวกัน

## วิธีที่ง่ายที่สุด

คลิกขวาที่ `jobs\jj\color\run.bat` → **Run as administrator**

มันไล่ให้ครบทุกขั้น หยุดรอตอนที่ต้องเพิ่มโหนดเอง แล้วให้ดูผล dry-run ก่อนถามว่า
จะลงจริงไหม ถ้าขั้นไหนพัง มันหยุดตรงนั้นพร้อมบอกสาเหตุ ไม่ไปต่อแบบครึ่ง ๆ กลาง ๆ

ต้องเป็น Administrator เพราะโฟลเดอร์ LUT ของ Resolve อยู่ใน ProgramData

## หรือรันทีละคำสั่ง

```bash
python .claude/skills/davinci-color/scripts/doctor.py

python .claude/skills/davinci-color/scripts/make_lut.py jobs/jj/color/jj_c0001.json --install

# หน้า Color เลือก C0001.MP4 แล้วเพิ่มโหนดจนมี 6 โหนด (Alt+S ทีละอัน)
# ถ้ากราฟว่าง คลิกขวาที่ node editor > Add Node > Add Serial ก่อน

python .claude/skills/davinci-color/scripts/apply_grade.py jobs/jj/color/graph.json --dry-run
python .claude/skills/davinci-color/scripts/apply_grade.py jobs/jj/color/graph.json

python .claude/skills/davinci-color/scripts/export_grade.py \
    --project jj --clip 1 --out jobs/jj/color --name jj_golden_hour
```

## ทำไมไม่ใช้ golden_hour.cube

ภาพอ้างอิงที่ส่งมาตอนแรกเป็นดาดฟ้าย้อนแสงตอนพระอาทิตย์ตก แต่ฟุตเทจจริงคือ
**ห้องซ้อมในร่ม** — คนละเรื่องกัน เอา `golden_hour` มาใส่จะได้:

| | ต้นฉบับ | golden_hour | jj_c0001 |
|---|---|---|---|
| เสื้อดำ | 0.07 | **0.11** หมอกเทาในห้องปิด | 0.055 |
| ผ้าม่านน้ำเงิน | 0.13,0.16,0.34 | **0.17**,0.19,0.35 อุ่นขึ้น 30% | 0.12,0.15,0.36 |

`jj_c0001.json` ทำมาสำหรับคลิปนี้: WB เดิมใกล้ถูกอยู่แล้วเลยแก้เบา ๆ
เติมคอนทราสต์ที่ห้องไม่มี ปล่อยให้ม่านน้ำเงินกับเบสเขียวเป็นตัวรับแซต
และกันผิวไว้หนัก (`skin_protect: 0.8`) เพราะเธอคือทั้งเฟรม

ถ้ายังอยากได้อารมณ์ golden hour จริง ๆ บอกได้ ผมปรับ `jj_c0001.json` ให้อุ่นขึ้น
โดยไม่พาหมอกกับ cast ผิด ๆ มาด้วย

## ไม่มี match ไม่มี trims

สองอย่างนั้นมีไว้กระจายกราฟไปหลายคลิป งานนี้คลิปเดียว ไม่มีอะไรให้กระจาย
ผมตัดออกจาก `graph.json` แล้ว

`select` ใช้ `name_contains: "C0001"` เลยไม่แคร์นามสกุลหรือตัวพิมพ์เล็กใหญ่

## กราฟ 6 โหนด

| โหนด | ทำอะไร | ใครตั้ง |
|---|---|---|
| `01 BALANCE` | handle เปล่า ๆ WB ห้องนี้ใกล้ถูกแล้ว | คนทำ ถ้าช่วงไหนหลุด |
| `02 EXPOSURE` | ดันเลเวลก่อนเข้า look | สคริปต์ |
| `03 LOOK` | `jj_c0001.cube` | สคริปต์ |
| `04 SKIN` | ดึงแซตคืนที่ผิว | สคริปต์ |
| `05 WINDOW` | **เปล่าและปิดไว้** — window ที่ตัวนักร้อง หรือ vignette กดวงดนตรี | คนทำ |
| `06 TRIM` | คำสุดท้าย หลังดูจนจบ | คนทำ |

## รันซ้ำได้

รันซ้ำหลังตัดใหม่ได้เลย สีกลับมาเหมือนเดิมเป๊ะ — สคริปต์มาร์กคลิปที่มันเกรดเอง
ด้วยสีส้มในไทม์ไลน์ รอบต่อไปมันจำได้ว่าอันไหนงานตัวเอง (ทับได้) อันไหนคนทำมือ
(ไม่ทับ ต้องสั่ง `--force`)

## เกรดเก่า

กราฟ 14 โหนดชุดเดิม (WB ด้วย Chromatic Adaptation 5721K → 6837K, HI LIGH, EXPOS,
EFX, SAT, layer mixer) ถูกลบไปแล้ว แต่ still `1.1.1`–`1.1.7` ในแกลเลอรียังเก็บ
เกรดนั้นไว้ — คลิกขวาที่ still แล้ว Apply Grade ได้ตลอด

หมายเหตุ: โหนด WB เดิมเป็น **OFX (Chromatic Adaptation)** ซึ่ง API แตะพารามิเตอร์
ไม่ได้เลย ถ้าอยากได้กลับมาต้องตั้งมือ แล้ว `export_grade.py` เก็บเป็น `.drx` ไว้
