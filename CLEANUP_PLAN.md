# Repo Cleanup Plan — PipelineGuard

> هدف: تبدیل ریپو از "به‌نظر می‌رسه کامله" به "واقعاً تمیز و قابل ارسال به شرکت".
> ترتیب مهم است — هر مرحله رو کامل کن قبل از رفتن به بعدی.

---

## مرحله ۱ — حذف فایل‌های اشتباه (5 دقیقه)

### مشکل
دو فایل در root هستند که نباید وجود داشته باشند:
- `git` — از یک دستور redirect اشتباه ساخته شده
- `main` — همین مشکل

### اجرا
```bash
rm git main
git add -A
git commit -m "chore: remove accidental root files"
git push
```

---

## مرحله ۲ — بررسی و پاکسازی فولدرها (15 دقیقه)

### قبل از هر چیز، وضعیت رو ببین
```bash
find . -type f | grep -v ".git" | sort
```

### فولدرهایی که باید چک کنی

**`examples/`**
```bash
ls -la examples/
```
- اگر خالیه یا فقط placeholder داره → حذف
- اگر کد قابل استفاده داره → نگه دار، ولی داخل README لینک بده

```bash
# حذف اگر بی‌ربط است
rm -rf examples/
git add -A && git commit -m "chore: remove empty examples directory"
```

**`docs/`**
```bash
ls -la docs/
```
- اگر auto-generated (مثل Sphinx output) است → حذف، چون README کافیه
- اگر دستی نوشته شده و اطلاعات مفید داره → نگه دار

**`config/`**
```bash
cat config/*
```
- باید فقط شامل config template یا default config باشه
- اگر secret یا `.env` واقعی داخلشه → فوری حذف + `.gitignore` چک کن

**`scripts/`**
```bash
ls scripts/
```
باید فقط این‌ها باشه:
- `generate_keys.py` ✓
- `simulate_load.py` ✓
- `demo.sh` ✓
- `kafka_setup.sh` (بعداً اضافه می‌شه)

اگر فایل دیگه‌ای هست که استفاده نمی‌شه → حذف.

---

## مرحله ۳ — چک `.gitignore` (10 دقیقه)

```bash
cat .gitignore
```

باید حتماً این‌ها باشن:
```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# Environment
.env
.env.*
!.env.example

# IDE
.idea/
.vscode/
*.swp

# Testing
.pytest_cache/
htmlcov/
.coverage
reports/

# OS
.DS_Store
Thumbs.db

# Keys (مهم‌ترین بخش)
*.pem
*.key
private_key*
```

اگر چیزی کم بود اضافه کن:
```bash
# مثال اضافه کردن
echo "reports/" >> .gitignore
git add .gitignore
git commit -m "chore: update gitignore"
```

### چک کن چیزی expose نشده
```bash
# ببین آیا فایل حساسی accidentally commit شده
git log --all --full-history -- "*.pem" "*.key" ".env"
```
اگر چیزی پیدا شد → بگو، باید از تاریخچه git هم پاک بشه.

---

## مرحله ۴ — بررسی `pyproject.toml` (10 دقیقه)

```bash
cat pyproject.toml
```

چک کن:
1. اسم پکیج `supermetrics` نباشه → باید `pipeline-guard` یا `pipeline_guard` باشه
2. همه dependencies نسخه دارن (نه `*`)
3. فیلدهای metadata پر شدن:
```toml
[project]
name = "pipeline-guard"
version = "0.1.0"
description = "Kafka-native pipeline reliability engine"
```

اگر اسم قدیمیه:
```bash
# ویرایش pyproject.toml
# بعد:
git add pyproject.toml
git commit -m "chore: rename package to pipeline-guard"
```

---

## مرحله ۵ — تمیز کردن `src/` (20 دقیقه)

```bash
find src/ -name "*.py" | head -50
```

دنبال اینا بگرد:

**فایل‌های تست یا debug که جا نداشتن**
```bash
find src/ -name "test_*.py" -o -name "*_test.py" -o -name "debug_*.py"
```
اگر پیدا شد → به `tests/` منتقل کن یا حذف کن.

**فایل‌های `__init__.py` خالی که باید محتوا داشتن**
```bash
find src/ -name "__init__.py" -empty
```
این‌ها معمولاً باشن فرقی نمی‌کنه، ولی اگر فولدری هست که `__init__.py` نداره:
```bash
find src/ -type d | while read d; do
  if [ ! -f "$d/__init__.py" ]; then echo "MISSING: $d/__init__.py"; fi
done
```

**imports استفاده نشده یا broken**
```bash
pip install --break-system-packages ruff
ruff check src/ --select F401  # unused imports
```

---

## مرحله ۶ — بررسی `BENCHMARKS.md` (5 دقیقه)

```bash
cat BENCHMARKS.md
```

اگر placeholder text دارد (مثل "X ms" یا "TBD"):

دو گزینه داری:
1. **اجرای واقعی** — stack رو بالا بیار، locust رو اجرا کن، اعداد واقعی بذار
2. **حذف موقت** — فایل رو به `BENCHMARKS.md.todo` تغییر نام بده تا اعداد واقعی داشته باشی

```bash
# گزینه ۲ — موقت
mv BENCHMARKS.md BENCHMARKS_TODO.md
echo "BENCHMARKS_TODO.md" >> .gitignore
git add -A
git commit -m "chore: hide placeholder benchmarks until real data available"
```

---

## مرحله ۷ — Rename ریپو در GitHub (5 دقیقه)

1. GitHub.com → باز کن ریپو `Aliipou/Supermetrics`
2. **Settings** → بالای صفحه
3. قسمت **Repository name**
4. تغییر به: `pipeline-guard`
5. کلیک **Rename**

بعد local:
```bash
git remote set-url origin https://github.com/Aliipou/pipeline-guard
git remote -v  # تأیید
```

---

## مرحله ۸ — README بررسی نهایی (15 دقیقه)

```bash
# ببین هنوز کلمه Supermetrics جایی هست
grep -ri "supermetrics" . --include="*.py" --include="*.md" --include="*.toml" --include="*.yml"
```

هر جایی که `supermetrics` بود → تغییر به `pipeline-guard` یا `PipelineGuard`.

بعد README از بالا تا پایین بخوان و چک کن:
- لینک‌های broken نداره
- Quick Start واقعاً کار می‌کنه (خودت اجرا کن)
- اعداد performance واقعی‌اند

---

## مرحله ۹ — یک اجرای کامل (30 دقیقه)

قبل از اینکه ریپو رو به کسی نشون بدی، از صفر اجرا کن:

```bash
# clone تازه در یک فولدر جدید
cd /tmp
git clone https://github.com/Aliipou/pipeline-guard
cd pipeline-guard

# دقیقاً همون دستورات README
python scripts/generate_keys.py
cd deploy/docker
docker compose up --build

# صبر کن تا همه سرویس‌ها healthy بشن
# بعد:
python scripts/simulate_load.py

# چک کن همه چیز کار می‌کنه
curl http://localhost:8000/health
curl http://localhost:8000/docs  # در browser باز کن
```

اگر چیزی کار نکرد → fix کن. اگر همه چیز کار کرد → commit نهایی:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## چک‌لیست نهایی

قبل از اینکه به Aiven پیام بدی:

- [ ] فایل‌های `git` و `main` از root حذف شدن
- [ ] هیچ `.env` یا key واقعی در ریپو نیست
- [ ] اسم ریپو در GitHub شده `pipeline-guard`
- [ ] هیچ کلمه `supermetrics` در کد نمونده
- [ ] Quick Start از صفر کار می‌کنه
- [ ] BENCHMARKS.md یا اعداد واقعی دارد یا حذف شده
- [ ] tag `v0.1.0` زده شده

---

## ترتیب اجرا (خلاصه)

```
روز ۱ (یک ساعت):
  مرحله ۱ → ۲ → ۳ → ۴

روز ۲ (یک ساعت):
  مرحله ۵ → ۶ → ۷ → ۸

روز ۳ (یک ساعت):
  مرحله ۹ — اجرای کامل و تأیید
```

بعد از این سه روز، ریپو آماده‌ست.
بعد می‌ری سراغ Kafka integration از `CLAUDE_KAFKA.md`.
