# Implementation review — v0.2

## PRD implementation mapping
FR01: tabel nilai, impor CSV preview/confirm, validasi all-or-nothing dan pemeriksaan revision tersedia.
FR02–03: Outcome Engine, versi formula, evidence ID, missing, CPL course scope tersedia.
FR04: draft template deterministik; katalog materi dan provider AI belum ada.
FR05: content immutable; approval dan publication menjadi satu transaksi dosen; stale snapshot diblokir. Tidak ada edit content endpoint.
FR06: penolakan draft, status selesai, catatan dan nilai hasil tindak lanjut tersedia; nilai hasil tidak mengganti assessment resmi.
FR07: audit actions dan baseline measurement tersedia; token/cost agent belum relevan tanpa provider.

## Formula yang dibekukan
CPMK = jumlah score × assessment weight; bobot assessment dalam setiap CPMK harus tepat 1. Missing satu assessment membuat CPMK incomplete. CPL mata kuliah = rata-rata berbobot semua CPMK yang memetakan CPL, dibagi jumlah bobot masuk. Bobot keluar tiap CPMK harus tepat 1; jumlah bobot masuk CPL boleh berbeda. Hitung Decimal sebelum rounding half-up 2 desimal, lalu serialize angka. Ini kebijakan pilot, bukan asumsi universal formula institusi.

## Kontrol yang diuji
Authorization object/class membership, session revoke, idempotency, missing evidence, stale snapshot, kill switch, measurement duplicates, invalid scores/weights, ROI hard gates. Akses sesungguhnya menggunakan user session di server, tidak memakai boolean dari klien.

## Temuan review dan debt
- Tidak ada endpoint tool arbitrary SQL, shell, atau provider LLM; prompt injection tooling belum ada permukaan pada versi ini.
- Password seed operator-supplied, session token hashed, cookie HttpOnly; login gagal generik dan verifikasi unknown user equal-cost.
- Rate limit login in-memory per proses. Session cleanup otomatis dan IP map eviction belum ada. Perlu shared limiter sebelum multi-worker.
- SQLite tidak memiliki row-level FOR UPDATE. Pilot lokal satu proses saja. PostgreSQL class row lock mengurutkan update skor dan approval; perlu concurrency regression pada database nyata.
- Revision kelas global menginvalidasi semua draft jika skor satu mahasiswa berubah: konservatif tetapi dapat meningkatkan beban review. Per-student revision ditunda.
- Audit durable per transaksi tetapi belum immutable/tamper-evident dan ekspor outcome CSV tersedia; export audit belum tersedia.
- Header security/CSP, multi-role institution auth, reset credentials, monitoring, retention dan restore drill belum selesai.
- Baseline measurement dapat memasukkan arm C secara manual; label bukan bukti provider AI benar-benar digunakan. Reviewer wajib memvalidasi protokol.
- Draft approved immutable dan tercatat; belum ada portal mahasiswa atau pengiriman eksternal.

Tidak ada klaim siap produksi. Operational/release gate tetap HOLD. Jangan memakai data mahasiswa nyata sampai otorisasi institusi dan hard gates terpenuhi.

## Referensi
https://svelte.dev/docs/kit/adapter-node
https://fastapi.tiangolo.com/advanced/security/http-basic-auth/ (prinsip secrets comparison; implementasi pilot memakai opaque session, bukan HTTP Basic)
