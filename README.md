# Campus Assistant v0.2 — Academic Outcome Pilot

Aplikasi baru untuk pilot satu kelas: Outcome Engine deterministik, API FastAPI, database SQLAlchemy + Alembic, dan dashboard SvelteKit/Svelte 5. Data awal sintetis. JEV memeriksa izin, bukti, versi snapshot, dan penghentian tindakan. Draft intervensi saat ini berbasis aturan; tidak memakai layanan AI berbayar.

## Dashboard lengkap

- **Ringkasan kelas:** capaian CPMK dinamis dan learning gap.
- **Data Akademik:** tambah kelas/mahasiswa, ubah nama, tabel input nilai, pengaturan CPMK/CPL/assessment, preview dan konfirmasi impor CSV, riwayat perubahan.
- **Intervensi:** draft, persetujuan, penolakan dengan alasan, pencatatan selesai dan hasil tindak lanjut.
- **Evaluasi pilot:** pengukuran waktu/biaya per kasus.
- **Laporan & ekspor:** tabel CPMK/CPL, ekspor CSV dan kalkulator skenario ROI (bukan keputusan release otomatis).

Setelah memperbarui branch, jalankan `uv run alembic upgrade head` untuk kolom tindak lanjut. Pilih kelas di Data Akademik, lalu gunakan tautan Ringkasan/Laporan untuk kelas tersebut.

## Yang sudah tersedia
- Login dosen dengan session opaque 8 jam, token disimpan sebagai hash di database.
- Password PBKDF2; cookie frontend HttpOnly dan SameSite; backend diakses melalui server SvelteKit.
- Membership kelas diperiksa pada setiap endpoint akademik.
- Assessment → CPMK → CPL untuk cakupan mata kuliah; missing berbeda dari nol.
- Draft intervensi idempotent, evidence assessment, approval dosen atomik, audit.
- Pembaruan nilai sintetis melalui API, snapshot berubah dan approval draft lama ditahan.
- Pencatatan kasus A/B/C dan kalkulator ROI/TCO; release tetap HOLD tanpa bukti.
- SQLite untuk percobaan lokal, PostgreSQL untuk tahap integrasi berikutnya.

## Menjalankan di Windows PowerShell

Prasyarat: Python 3.12+, uv, Node.js 22.12+ atau 24+, npm. Buka folder repository. Jika perubahan ini belum di-merge, checkout branch PR dahulu:

```powershell
git fetch origin
git switch feat/campus-assistant-mvp
uv sync --extra dev
uv run alembic upgrade head
$env:DEMO_PASSWORD = Read-Host 'Tetapkan password demo minimal 12 karakter'
uv run python -m campus_assistant.api.seed
uv run uvicorn campus_assistant.api.main:app --host 127.0.0.1 --port 8000
```

Password tersebut digunakan akun `dosen`. Seed hanya membuat kelas awal jika belum ada, tidak mereset password atau nilai. Jangan gunakan password akun pribadi. Database lokal `campus.db` tidak masuk git. `Read-Host` di atas memasukkan password ke environment proses lokal; tutup terminal ketika selesai.

Terminal kedua:

```powershell
cd frontend
npm ci
npm run dev
```

Buka http://localhost:5173. Login `dosen` dengan password seed. API docs: http://127.0.0.1:8000/docs. API memerlukan bearer token dari `/auth/login`. Frontend menjalankan pemanggilan API dari server; tidak membutuhkan CORS permissive.

## Alur penggunaan
1. Ringkasan kelas menampilkan 10 mahasiswa sintetis, 3 CPMK, 2 CPL.
2. STD-003 memiliki skor 78/52/69; CPMK gap 0/23/11; CPL 70,20/64,40.
3. Pilih Buat draft; buka Intervensi, periksa bukti dan latihan, lalu Setujui.
4. STD-010 memiliki nilai belum lengkap dan tidak dapat dibuatkan intervensi final.
5. Evaluasi pilot: masukkan case_id, arm dan waktu kerja/review/koreksi secara terpisah. Arm C hanya untuk evaluasi setelah AI tersedia. Tidak ada klaim ROI otomatis dari jumlah record.

## PostgreSQL (opsional)

Docker dipakai untuk database saja. Pada terminal yang sama:

```powershell
$env:POSTGRES_PASSWORD = Read-Host 'Password database baru'
docker compose -f infrastructure/compose.yaml up -d
$env:DATABASE_URL = 'postgresql+psycopg://campus:PASSWORD_URL_ENCODED@localhost:5432/campus_assistant'
uv run alembic upgrade head
uv run python -m campus_assistant.api.seed
uv run uvicorn campus_assistant.api.main:app --host 127.0.0.1 --port 8000
```

Ganti PASSWORD_URL_ENCODED dengan password database yang sudah di-URL-encode. SQLite dan PostgreSQL adalah database berbeda; seed kembali diperlukan. Jangan hapus volume database tanpa backup. Compose bind hanya ke localhost; tidak menyertakan kredensial tetap.

## Verifikasi

```powershell
uv run pytest -q
cd frontend
npm run check
npm run build
```

E2E membutuhkan kedua server aktif dan seed sintetis:

```powershell
$env:DEMO_PASSWORD = Read-Host 'Password seed sintetis'
npx playwright install chromium
npx playwright test --workers=1
```

Playwright menambah pengukuran dan draft pada database sintetis; jangan arahkan ke data produksi. Default WEB_URL http://127.0.0.1:5173. Frontend build adapter-node: set API_URL, ORIGIN, HOST dan PORT sesuai lingkungan, lalu `npm start`. Gunakan HTTPS bila di luar localhost.

## Struktur

```text
src/campus_assistant/
  outcomes.py          # perhitungan deterministik
  api/                 # models, auth, seed dan FastAPI
  pilot/               # JEV dan ROI
frontend/              # SvelteKit, UI dan browser tests
migrations/            # skema Alembic berversi
infrastructure/        # PostgreSQL compose
tests/                # unit dan API integration
docs/                 # spesifikasi, pilot dan verification
```

## Batas versi ini

Pilot dosen dengan beberapa kelas; belum portal mahasiswa/prodi, edit teks draft, integrasi kampus, atau provider LLM. Setiap ID mahasiswa unik secara global dalam pilot; belum mendukung satu mahasiswa terdaftar di beberapa kelas. Catatan hasil intervensi tidak mengubah nilai assessment secara otomatis. Tidak ada perubahan nilai resmi. Rate limit login bersifat per-proses, bukan distributed. SQLite untuk satu proses lokal; perilaku konkurensi/PostgreSQL perlu verifikasi sebelum pilot operasional. Audit mencatat tindakan dalam database, belum tamper-evident. Kredensial/reset password, retention, HTTPS dan operasional institusi perlu rancangan sebelum release. Status GO untuk percobaan sintetis, HOLD untuk data nyata dan release. Lihatdocs/IMPLEMENTATION_REVIEW.md.
