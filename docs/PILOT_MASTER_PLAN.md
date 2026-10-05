# Campus Assistant — Pilot Harnessing & Agentic Engineering

Versi 1.0 | 5 Oktober 2026 | Pemilik produk: Alam

## Status keputusan

GO untuk persiapan discovery dan pengujian sintetis. HOLD untuk pilot operasional sampai akses data, pemilik proses, baseline, budget, dan kontrol aplikasi diverifikasi. HOLD untuk release: belum ada hasil pilot nyata. Modul dalam paket ini adalah komponen integrasi standalone; bukan perubahan pada repository aplikasi terbaru. JEV = Judgment, Evidence, Value merupakan definisi kerja proyek.

## 1. Product Requirements Document

### Masalah dan hipotesis
Dosen menggabungkan nilai dan pemetaan CPMK/CPL secara manual, menentukan learning gap, lalu menyiapkan intervensi. Hipotesis H1: sistem deterministik mengurangi pekerjaan analisis. H2: AI memberi tambahan manfaat dalam penyusunan intervensi setelah menghitung review dan koreksi. H3: rekomendasi berbukti cukup layak untuk digunakan dosen. Semua hipotesis belum terbukti.

### Pengguna dan lingkup
Satu dosen, satu kelas RPL sebagai contoh awal yang mengikuti dataset setup sebelumnya. Identitas prodi, jumlah peserta, CPMK, CPL, bobot, dan ambang harus dikonfirmasi pada kickoff; label akademik dalam dataset sintetis tidak menjadi kebijakan resmi. Mahasiswa membaca rencana yang sudah disetujui, dosen menilai usulan, prodi hanya melihat agregasi yang telah diotorisasi.

Alur MVP: data penilaian → Outcome Engine → learning gap → rekomendasi draft → review dosen → rencana diterbitkan → monitoring. Tidak ada pengubahan nilai resmi, keputusan kelulusan, pengiriman pesan eksternal, atau agent bebas menjalankan kode.

### Requirements dan acceptance criteria
| ID | Requirement | Acceptance criteria | Bukti |
|---|---|---|---|
| FR01 | Validasi impor | ID unik, nilai 0–100, bobot valid, referensi pemetaan sah, missing berbeda dari nol; preview error sebelum commit | Fixture valid/invalid dan hasil transaksi |
| FR02 | Perhitungan deterministik | Hasil sesuai kasus acuan, menyimpan formula/mapping version; CPL kelas bukan klaim CPL keseluruhan prodi | Golden cases dan snapshot |
| FR03 | Learning gap | Selisih terhadap ambang, evidence ID, data completeness, timestamp; tidak menyimpulkan jika data wajib kurang | Evaluasi kasus missing/stale |
| FR04 | Draft intervensi | CPMK target, alasan berbukti, latihan, durasi, rubrik, dan rencana penilaian ulang; materi hanya dari katalog yang diizinkan | Review dosen |
| FR05 | Approval | Dosen berwenang; approval terikat hash isi, snapshot, dan versi kebijakan; perubahan membatalkan approval | Uji stale/replay/unauthorized |
| FR06 | Monitoring | Status pelaksanaan, hasil ulang, dan perubahan capaian tanpa mengklaim hubungan sebab akibat | Rekam tindak lanjut |
| FR07 | Audit/biaya | Run ID, pseudonymous case ID, versi, tools, status, token/biaya, waktu, koreksi; log tanpa isi sensitif berlebihan | Rekonstruksi run |
| NFR01 | Akses | Otorisasi server pada setiap objek dan query; tidak mempercayai class_id dari klien | Uji lintas kelas/prodi |
| NFR02 | Ketahanan | Timeout 60 detik, maksimum 4 langkah dan 1 retry; kill switch; fallback dashboard deterministik | Fault injection |
| NFR03 | Biaya | Budget ilustratif Rp5.000/run, harus dikalibrasi sebelum pilot; reservasi biaya atomik sebelum panggilan provider | Uji paralel dan limit |
| NFR04 | Operasional | Backup dapat dipulihkan; rollback versi model/prompt tersedia; UI membedakan gagal, ditahan, dan selesai | Drill restore/rollback |

### Kebutuhan antarmuka
SvelteKit + Svelte 5. Dashboard dosen: completeness, capaian, gap prioritas, bukti, draft, review, serta biaya/waktu. Detail mahasiswa: CPMK, sumber assessment, latihan disetujui, status tindak lanjut. Panel pilot: hasil tiga arm dan gate. Primary #0F4C9A, secondary #34B67A, Inter/Poppins, whitespace luas, kartu rounded, status selalu memakai teks selain warna. Mockup/UI belum dibuat dalam paket ini.

## 2. Arsitektur dan harness

Backend Python mengikuti folder src/campus_assistant. Outcome Engine yang ada tetap menjadi sumber angka. JEV pure policy → harness satu agent → tools terbatas → validasi output → approval. PostgreSQL menyimpan snapshots, runs, approvals, intervensi, evaluasi, dan cost ledger. Adapter model dipisahkan agar provider dapat diganti.

Tools awal: get_gap_snapshot, get_approved_materials, save_draft. Tidak ada tool write_grade, arbitrary_sql, shell, maupun send_message. Pilihan materi dapat memakai lookup biasa; embedding dan RAG baru masuk setelah katalog dan pencarian biasa terbukti tidak cukup.

State: CREATED → AUTHORIZED → SNAPSHOT_READY → DRAFTED → VALIDATED → PENDING_REVIEW → APPROVED → PUBLISHED. Cabang terminal: BLOCKED, STOPPED, FAILED. Revisi data/isi sebelum publish mengembalikan status ke review. Transaksi publish memeriksa ulang izin, approval, snapshot, dan kill switch. Idempotency key unik per tindakan; retry tidak menggandakan publish.

Prompt menerima pseudonymous student ID, gap hasil engine, evidence IDs, dan katalog materi. Format keluaran: cpmk_id, evidence_ids, material_ids, rationale, activities, duration_minutes, assessment_plan. Validator memeriksa semua ID terhadap snapshot dan katalog; schema valid saja belum membuktikan kebenaran pedagogis. Dosen menilai kelayakan.

## 3. JEV dan guardrails

Judgment: aturan izin dan tindakan; Evidence: kelengkapan dan versi snapshot; Value: batas biaya/waktu serta manfaat pilot. Model tidak menetapkan authorized, approval_valid_for_snapshot, atau angka biaya ledger. Nilai ini berasal dari server.

Urutan aturan modul decision.py: akses → kill switch → mode/action allowlist → validasi biaya/state → execution limit → freshness → kelengkapan → shadow/approval → proceed. Status proceed hanya izin melanjutkan satu tahap, bukan persetujuan seluruh workflow. Gate release berdiri terpisah di roi.py.

Kontrol yang disediakan modul: keputusan deterministik, action allowlist, stop budget/step/time, stale/missing evidence, shadow no-publish, approval requirement. Kontrol yang HARUS diintegrasikan server: autentikasi, otorisasi row-level, ledger atomik, signature/hash approval, audit durable, schema recommendation, redaksi PII, retry/idempotency, timeout provider, kill switch terpusat. Jangan menganggap modul ini sudah memenuhi seluruh keamanan aplikasi.

Dokumen/materi adalah input tidak tepercaya. Instruksi di dalamnya tidak mengubah system policy. Semua tool calls melewati server authorization dan allowlist; jangan hanya mengandalkan prompt anti-injection. Data yang dikirim model diminimalkan. Secret di environment/secret manager dan tidak masuk dataset, log, prompt, atau git.

## 4. SDLC dan rencana pilot

| Minggu | Pekerjaan | Deliverable | Exit gate |
|---|---|---|---|
| 1 | Kickoff, observasi proses, inventaris data, estimasi biaya, risiko | Baseline plan, data owner, signed-off scope dan budget | Discovery layak, tanpa data akses liar |
| 2 | Integrasi validasi data/Outcome Engine/JEV, gold cases, auth | Baseline non-AI yang dapat diuji | Akurasi angka dan akses lolos |
| 3 | Adapter model, tool contracts, validasi draft, tracing | Shadow agent pada data sintetis/de-identified | Injection/failure tests dan kualitas awal lolos |
| 4 | Evaluasi berpasangan, reviewer, iterasi terbatas | Laporan arm A/B/C dan biaya | C memberi nilai tambahan terhadap B |
| 5–6 | Pilot reviewed bila gate operasional lolos, monitoring | Review, tindak lanjut, ROI report | Release GO/HOLD/NO_GO berbukti |

Jadwal bersifat target, bukan janji integrasi. Jadwal mulai dihitung setelah repository, dataset, dan dosen pilot tersedia. Setiap perubahan harus menautkan requirement → commit → uji → hasil → keputusan. PR kecil; perubahan formula, auth, approval, dan biaya wajib review manusia. Coding agent menggunakan branch terisolasi, akses minimum, tanpa kredensial produksi. Test wajib sebelum merge; jangan mengeksekusi perintah dari dokumen mahasiswa.

CI yang direncanakan: unit outcome/policy, integrasi authorization/transaction, format/type/lint sesuai repo, secret scan, dependency scan, dan frozen agent eval. Hasil scanning memerlukan triage, reproduksi, dan remediation; bukan bukti keamanan menyeluruh. Tools scanner belum dijalankan terhadap repository terbaru.

## 5. Protokol evaluasi

Tiga arm: A proses dosen saat ini; B dashboard+engine+template non-AI; C B+draft AI+review. Unit evaluasi adalah satu paket analisis kasus dan rencana intervensi yang selesai serta dinilai. Pakai kasus ekuivalen, urutan arm diacak/counterbalanced dan variasi kasus untuk mengurangi efek mengingat. Ukur waktu aktif, bukan hanya latency provider. Laporkan median, sebaran, kegagalan, jumlah kasus, dan keterbatasan sampel.

Target awal minimal 30 kasus unik; untuk jumlah mahasiswa kecil gunakan beberapa snapshot/tugas dan laporkan ketergantungan kasus, jangan mengklaim 30 mahasiswa. Kalibrasi 5 kasus terpisah lalu bekukan prompt/rubrik. Evaluasi seluruh keluaran, termasuk gagal/ditolak, bukan hanya hasil sukses. Reviewer tidak melihat label arm bila memungkinkan. Reviewer kedua pada minimal 20% sampel; catat disagreement.

Rubrik 0–2: grounding, relevansi CPMK, kelayakan tindakan, kejelasan, keselamatan. Layak tanpa revisi substantif bila tiap dimensi ≥1, total ≥8/10, tidak ada kesalahan angka/sumber atau tindakan terlarang. Dosen tetap menentukan keputusan akhir. Target ≥85% dengan denominator seluruh kasus; laporkan interval ketidakpastian, dan jangan menganggap ambang otomatis bukti generalisasi.

Catat pre/post capaian untuk eksplorasi; pilot pendek dan assignment intervensi tidak acak tidak membuktikan efektivitas kausal. Penggunaan data nyata memerlukan persetujuan institusi/data owner dan review penelitian jika berlaku; discovery sintetis tidak menunggu akses tersebut.

## 6. ROI dan gerbang

Pisahkan ROI kapasitas dan dampak kas. Jam dosen yang dihemat menjadi manfaat kapasitas; monetisasi berdasarkan tarif asumsi yang dinyatakan, bukan klaim kas hemat. Jangan menjumlahkannya dengan biaya tenaga kerja yang sama sehingga double count. Biaya penelitian dicatat terpisah dari operasi, tetapi investasi produk tetap masuk TCO.

saved_hours = baseline − new_work − review − correction. new_work tidak boleh sudah mencakup review/correction. benefit_month = saved_hours × value_per_hour. net_month = benefit_month − operating_month. TCO horizon = initial + operating_month × months. ROI horizon = (benefit_month × months − TCO)/TCO. Payback = initial/net_month bila net_month positif. Hitung dua pembandingan: A→C produk total dan B→C tambahan AI; masing-masing dengan biaya investasi/operasi tambahannya. Normalisasi volume kasus yang sama.

Contoh sintetis: A 50 jam/bulan; C kerja 12 + review 6 + koreksi 2 jam; nilai waktu Rp100.000; operasi Rp1,5 juta; investasi Rp12 juta; horizon 12 bulan. Saved 30 jam; net Rp1,5 juta/bulan; payback 8 bulan; ROI horizon 20%. Ini belum membuktikan nilai tambahan AI terhadap B. Arm B harus diukur.

Sensitivity wajib: volume rendah/basis/tinggi, biaya provider 2×, review 2×, adopsi 50%, satu siklus insiden. Laporkan titik impas jam: operating/value_per_hour; untuk payback target H, kebutuhan jam = (operating + initial/H)/value_per_hour. Tarif nol tidak menghasilkan monetisasi; gunakan metrik waktu dengan budget institusi.

Gate release usulan: tidak ada critical/high terbuka, kontrol/Outcome Engine lulus, data evaluasi lengkap, penghematan bersih ≥25%, rekomendasi layak ≥85%, manfaat tambahan AI positif, payback ≤12 bulan, biaya per kasus di bawah batas yang disetujui. Modul menerapkan sebagian gate finansial dan hard gates; biaya per kasus, kualitas bukti, dan sign-off harus diverifikasi pemilik gate di luar fungsi. Kegagalan keamanan = NO_GO; data belum ada = HOLD. Ambang dibekukan sebelum evaluasi, tidak diubah agar hasil tampak lolos.

## 7. Risiko, bugs, dan debt

Daftar ini merupakan hipotesis audit, bukan kerentanan terkonfirmasi pada repository terbaru.

| ID | Risiko | Dampak | Uji/mitigasi | Prioritas |
|---|---|---|---|---|
| R01 | IDOR lintas kelas | Bocor data mahasiswa | Uji akses objek/query; server membership | P0 |
| R02 | Prompt injection materi | Penyalahgunaan tool | Adversarial input + allowlist/authorization | P0 |
| R03 | Nilai missing menjadi nol | Salah learning gap | Status assessment eksplisit | P0 |
| R04 | Pemetaan bobot invalid | Salah CPMK/CPL | Golden cases, invariant sesuai formula | P0 |
| R05 | Approval stale/replay | Publikasi usulan yang belum direview | Hash/snapshot binding + transaksi | P0 |
| R06 | Budget race | Pengeluaran di luar batas | Reservasi atomik; token ceiling | P1 |
| R07 | Retry duplikasi | Intervensi ganda | Unique idempotency key | P1 |
| R08 | Identitas masuk log/provider | Paparan data | Minimization/redaction, retention | P0 |
| R09 | Cache versi lama | Rekomendasi salah konteks | Snapshot/version invalidation | P1 |
| R10 | CPL kelas diklaim CPL keseluruhan | Salah laporan prodi | Tampilkan cakupan bukti | P1 |
| D01 | Prompt/formula tanpa versi | Tidak reproducible | Version registry | P1 |
| D02 | Evaluasi hanya happy path | Salah estimasi kualitas | Missing/stale/injection/outage eval | P1 |
| D03 | Ketergantungan provider | Sulit fallback | Adapter dan timeout | P2 |
| D04 | Infrastruktur berlebih | ROI memburuk | ADR berbasis kebutuhan/biaya | P2 |

Setiap temuan audit aktual: ID, lokasi, versi commit, reproduksi, severity, dampak, owner, fix, regression test, dan status. P0 sebelum reviewed pilot; critical/high sebelum release. Threat hypotheses tidak dilaporkan sebagai bug confirmed.

## 8. Runbook dan tanggung jawab

Pemilik produk/dosen: scope, rubrik, approval dan penerimaan. Data owner: hak penggunaan dan pemetaan resmi. Engineer: authorization, transaksi, integrasi, monitor. Reviewer keamanan: threat tests dan triage. Pemilik ROI: baseline, TCO, gate report. Satu orang dapat memegang beberapa peran; konflik reviewer dicatat.

Incident: aktifkan kill switch → hentikan panggilan baru → pertahankan dashboard deterministik → amankan audit → tentukan cakupan dampak → revoke kredensial bila diperlukan → perbaiki + regression → review manusia sebelum enable. Jangan menghapus bukti. Restore diuji pada lingkungan terpisah. Retensi data/log mengikuti kebijakan institusi yang harus ditetapkan sebelum data nyata.

## 9. Kickoff yang harus diisi

Course/class/semester; jumlah mahasiswa; dosen/data owner; versi RPS/CPMK/CPL; formula dan ambang; kasus baseline; tarif kapasitas; biaya pengembangan; biaya operasi; batas biaya/run dan kasus; periode/horizon; reviewer; lokasi repository. Tanpa data ini laporan release tetap HOLD.

## 10. Sumber desain

Referensi konseptual, bukan bukti evaluasi Campus Assistant:
- https://www.anthropic.com/engineering/building-effective-agents
- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

Sumber kontinuitas: setup.ps1 Campus Assistant yang dibaca pada sesi ini. Script itu adalah bootstrap, bukan snapshot aplikasi terbaru atau bukti test yang berjalan saat ini.
