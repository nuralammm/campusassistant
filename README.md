# Campus Assistant — Pilot Integration Pack v1.0

Paket standalone untuk tahap persiapan pilot satu kelas. Tidak mengubah aplikasi yang ada. Python standard library; tidak memerlukan API key, provider AI, atau data mahasiswa nyata.

## Isi
- docs/PILOT_MASTER_PLAN.md: PRD, SDLC, arsitektur, JEV, guardrails, evaluasi, ROI dan risk register.
- src/campus_assistant/pilot/decision.py: deterministic policy layer.
- src/campus_assistant/pilot/roi.py: TCO/ROI dan release gate.
- tests/test_pilot.py: uji policy dan ekonomi.
- demo.py: contoh sintetis lengkap, tanpa eksekusi tool atau publikasi.
- data/measurement_template.csv: header pencatatan tiga arm; bukan data evaluasi nyata.
- docs/VERIFICATION.md: hasil verifikasi dan batas cakupan.

## Jalankan pada Windows PowerShell
Dari folder paket hasil ekstrak:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
python demo.py
```

Jika menggunakan uv pada project yang sudah ada, gunakan `uv run python` sebagai pengganti `python`. Tidak ada dependency baru yang harus diinstal untuk modul ini.

## Integrasi ke proyek
1. Baca master plan dan isi kickoff. Jangan menjalankan ulang setup.ps1 lama untuk integrasi: file bootstrap tertentu dapat tertimpa.
2. Review perbedaan sebelum menyalin folder pilot ke src/campus_assistant/pilot dan tests ke tests/unit pada branch baru. Jangan overwrite file yang sudah ada.
3. Pasang JEV setelah authorization server dan pembentukan snapshot Outcome Engine. Context tidak boleh dibentuk langsung dari payload klien/model.
4. Implementasikan kontrol server yang disebutkan master plan: auth, approval hash, atomic budget ledger, audit, schema, timeout, idempotency.
5. Jalankan uji paket dan seluruh regression Outcome Engine yang sudah ada. Paket ini tidak menggantikan test aplikasi.
6. Mulai synthetic shadow eval. Provider live dan reviewed pilot hanya setelah gate operasional diverifikasi.

## Keputusan saat ini
GO persiapan sintetis; HOLD pilot operasional dan release. Data ROI contoh tidak boleh dipakai mengklaim keuntungan aktual.
