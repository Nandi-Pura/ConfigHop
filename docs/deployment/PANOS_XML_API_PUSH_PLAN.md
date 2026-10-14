# Rencana Collect dan Push Konfigurasi PAN-OS melalui XML API

Status dokumen: `Proposed`

Target awal: migrasi langsung dari satu firewall Palo Alto sumber ke satu firewall Palo Alto tujuan di lab

Di luar target awal: Panorama, HA pair, production deployment, dan multi-user approval

## 1. Tujuan

Menambahkan workflow migrasi dari firewall PAN-OS lama ke firewall PAN-OS baru. ConfigHop mengambil running configuration perangkat sumber melalui XML API, memasukkannya ke pipeline analisis yang saat ini menerima upload XML, lalu engineer meninjau mapping dan perubahan di dashboard. Hasil review menjadi dasar deployment package untuk perangkat tujuan.

Alur utama: `Connect source -> Collect running config -> Parse/Analyze -> Manual review -> Build target package -> Connect target -> Preflight/Backup -> Stage/Validate -> Approve/Commit -> Verify`.

Upload XML manual tetap menjadi jalur input alternatif. Asal source (`API_COLLECTED` atau `FILE_UPLOADED`) harus terlihat pada project dan hasil review.

Fitur dianggap selesai hanya jika sistem dapat:

1. mengambil snapshot running configuration perangkat sumber tanpa memodifikasinya;
2. membuktikan asal snapshot melalui serial, model, PAN-OS version, waktu collect, dan SHA-256;
3. menjalankan analisis serta review manual yang sama untuk source dari API maupun file;
4. membuktikan identitas dan kompatibilitas target yang berbeda dari sumber;
5. mengambil backup target sebelum mutasi;
6. mengunggah dan memuat konfigurasi sebagai candidate, tanpa langsung mengaktifkannya;
7. menjalankan validasi PAN-OS dan menampilkan seluruh warning/error;
8. meminta approval terpisah sebelum commit;
9. memantau job commit sampai hasil akhir;
10. memverifikasi perangkat setelah commit;
11. menyediakan recovery yang telah diuji di lab dan audit trail yang tidak berisi secret.

## 2. Baseline Repo Saat Ini

| Area | Status sekarang | Dampak ke fitur push |
|---|---|---|
| Candidate generation | `Available` untuk target/render path yang sudah dikualifikasi | Menjadi input deployment, tetapi belum otomatis layak di-load ke device |
| Candidate validation lokal | `Available` | Hanya membuktikan parsing, inventory expectation, dan preservation scope lokal |
| Source XML upload | `Available` | Tetap tersedia sebagai alternatif collect; parser dan review harus memakai satu jalur validasi |
| Source API collection | `Unavailable` | Perlu koneksi read-only, pengambilan running config, dan provenance snapshot |
| Live firewall connection | `Unavailable` | Perlu PAN-OS XML API client baru |
| Project state | In-memory dan temporary directory | Tidak cukup untuk job deployment dan audit yang harus bertahan setelah restart |
| Raw source access | Source XML dapat diunduh dan ditampilkan pada UI lokal | Collection dari firewall perlu masking dan kebijakan akses artifact sebelum diaktifkan |
| App authentication/RBAC | `Unavailable` | Live deployment harus tetap localhost/lab sampai kontrol akses tersedia |
| Device validation/commit | `Unavailable` | Harus dibuat sebagai state machine asynchronous |
| Rollback teruji | `Unavailable` | Production gate tidak boleh dibuka |

Catatan penting: validasi candidate saat ini tidak membuktikan bahwa full configuration aman untuk target. Sebelum live load, perlu pemeriksaan khusus agar source-local settings seperti management interface, hostname, HA, admin, certificate, master-key-dependent secret, licensing-related identity, dan Panorama ownership tidak ikut menggantikan setting lokal target tanpa keputusan eksplisit.

## 3. Keputusan Arsitektur

### 3.1 Scope rilis pertama

Rilis pertama mendukung:

- direct connection ke satu firewall sumber dan satu firewall tujuan melalui management interface;
- HTTPS PAN-OS XML API;
- API key sumber dengan izin baca saja dan API key tujuan dengan izin sesuai tahap deployment, keduanya dikirim melalui header `X-PAN-KEY`;
- collect running configuration sumber sebagai default; file upload manual tetap tersedia;
- identitas sumber dan tujuan yang berbeda, dengan provenance dan hash snapshot yang terlihat di dashboard;
- target standalone/non-HA yang memiliki out-of-band management;
- full candidate import/load hanya setelah deployability gate lulus;
- tahap `Upload + Load + Validate` terpisah dari `Commit`;
- satu active deployment per serial number.

Rilis pertama tidak mendukung:

- Panorama atau `commit-all`;
- HA active/passive atau active/active;
- browser langsung memanggil firewall;
- username/password key generation dari UI;
- HTTP plaintext;
- TLS verification yang diam-diam dinonaktifkan;
- blind retry untuk import, load, commit, atau rollback;
- auto-commit setelah upload;
- klaim rollback otomatis jika management connectivity hilang;
- pengambilan uncommitted source candidate sebagai input migrasi otomatis; operator dapat meninjaunya sebagai temuan, tetapi baseline migrasi adalah running config.

### 3.2 Jalur komunikasi

```text
Browser UI
   |  localhost API, secret hanya dikirim saat membuat session
   v
ConfigHop FastAPI
   |  HTTPS + X-PAN-KEY + certificate verification/pinning
   v
PAN-OS XML API
```

Browser tidak menyimpan API key di `localStorage`, URL, project JSON, atau log. Backend memberi secret handle terpisah dan ber-TTL untuk source dan target. Source handle hanya mengizinkan operasi baca yang dibutuhkan collect, sedangkan target handle mengikuti tahap deployment. Untuk MVP lokal, secret vault dapat berupa memory-only store; sebelum production, ganti dengan OS credential manager atau external secret manager.

Source collection dan target deployment memakai koneksi yang berbeda. Project menyimpan identitas kedua perangkat, tetapi tidak menyimpan API key. Penghapusan project harus mencabut handle yang masih hidup.

### 3.3 State machine source collection dan deployment

Source collection punya state terpisah dari deployment: `SOURCE_EMPTY -> SOURCE_CONNECTING -> SOURCE_COLLECTING -> SOURCE_VERIFYING -> SOURCE_READY`, dengan terminal error `SOURCE_COLLECT_FAILED` atau `SOURCE_REVIEW_REQUIRED`. `SOURCE_READY` berarti XML telah diterima dan diparse; status itu belum berarti candidate siap di-deploy. Pada file upload, jalur parse yang sama menghasilkan `SOURCE_READY` dengan provenance berbeda.

Perubahan source snapshot, source profile, target profile, mapping, atau review harus menginvalidasi deployment package yang belum distage. Deployment yang sudah distage tetap memiliki snapshot immutable dan tidak boleh diam-diam memakai project state terbaru.

```text
CREATED
  -> PREFLIGHT_PASSED
  -> BACKUP_CAPTURED
  -> IMPORTED
  -> CANDIDATE_LOADED
  -> VALIDATING
  -> VALIDATED
  -> AWAITING_COMMIT_APPROVAL
  -> COMMIT_QUEUED
  -> COMMIT_RUNNING
  -> VERIFYING
  -> SUCCEEDED
```

Setiap tahap dapat berakhir pada `FAILED_SAFE`, `FAILED_NEEDS_OPERATOR`, atau `CANCELLED`. Recovery memakai state terpisah: `RECOVERY_REQUESTED -> BACKUP_LOADED -> RECOVERY_VALIDATING -> RECOVERY_COMMITTING -> RECOVERED`. Jangan memberi label `ROLLED_BACK` hanya karena backup tersedia; label itu hanya boleh digunakan setelah restore, commit, dan verification berhasil.

## 4. Workflow End-to-End

### 4.1 Connect source dan collect konfigurasi

Pada section `Source Configuration`, sediakan pilihan `Collect from firewall` dan `Upload XML`. Untuk collect, operator mengisi host/IP sumber, port, API key baca, serta CA certificate atau certificate fingerprint. Setelah `Test source connection`, UI menampilkan hostname, serial, model, PAN-OS version, dan TLS identity agar operator dapat memastikan perangkat yang benar.

Urutan collect read-only:

1. Validasi host/port, DNS, TLS identity, API permission, dan system info. Source harus direct firewall yang sesuai scope awal. Baca pending change summary bila API role mengizinkan, lalu beri warning bila candidate sumber berbeda dari running config.
2. Ambil snapshot **running configuration** lengkap melalui XML API `type=export&category=configuration`, dengan parameter snapshot yang dibuktikan pada versi PAN-OS lab. Simpan body sebagai XML config, bukan XML response wrapper. Alternatif `type=config&action=show` hanya dipakai jika bentuk outputnya terbukti setara dan kompatibel dengan parser; `action=get` merujuk candidate configuration dan tidak boleh diam-diam menjadi baseline migrasi.
3. Batasi ukuran dan waktu respons, tolak HTTP/XML API error, parse XML secara aman, lalu hitung SHA-256 dari byte mentah sebelum normalisasi.
4. Ambil system info lagi setelah export untuk memeriksa serial/model. Untuk mendeteksi perubahan running config selama collect, bandingkan revision/commit identifier sebelum dan sesudah bila tersedia dan terbukti pada versi lab; bila tidak, export ulang dan bandingkan hash kedua hasil. Ketidakcocokan menandai `COLLECT_REVIEW_REQUIRED` dan mencegah promosi snapshot.
5. Cocokkan model dari system info dengan exact source hardware profile di registry dan bandingkan PAN-OS version perangkat dengan metadata XML. Tampilkan hasilnya untuk konfirmasi operator; mismatch atau model tak dikenal memblokir candidate. Masukkan snapshot ke jalur parse, inventory, compatibility, preview, dan candidate yang sama dengan upload file. Penggantian source harus menghapus hasil review, mapping, dan candidate lama melalui invalidation yang sama.
6. Simpan `SourceSnapshot` immutable: origin `API_COLLECTED`, endpoint tanpa secret, hostname, serial, model, PAN-OS version, timestamp UTC, jenis snapshot `RUNNING`, ukuran, SHA-256, TLS fingerprint, parser status, dan warning. Untuk upload manual, isi origin `FILE_UPLOADED` dan jangan mengarang serial perangkat; deployment dari file memerlukan identitas source yang dibuktikan secara terpisah.

Jika collect gagal, project mempertahankan source sebelumnya sampai snapshot baru selesai diunduh, diparse, dan dipromosikan secara atomik. Error UI harus membedakan kegagalan koneksi, izin export, TLS, ukuran, format, dan perubahan perangkat sumber. Collect ulang menghasilkan snapshot baru, bukan menimpa bukti snapshot lama; review sebelumnya tidak berlaku sampai operator meninjau diff kedua snapshot.

Config yang dikumpulkan dapat berisi secret. Simpan artifact secara terenkripsi atau gunakan working file berumur pendek dengan akses terbatas untuk parser. Raw XML preview/download memerlukan aksi eksplisit dan masking secret secara default. Audit dan event stream hanya menampilkan metadata serta hash.

### 4.2 Connect target dan preflight read-only

UI meminta:

- hostname/IP target;
- port, default `443`;
- API key;
- CA certificate atau certificate fingerprint jika target memakai internal/self-signed certificate;
- change ticket/reference opsional untuk lab dan wajib pada production phase;
- expected serial/model dari operator.

Backend melakukan read-only checks:

1. resolve target dan menolak redirect;
2. melakukan TLS verification atau exact fingerprint pinning;
3. memanggil system info untuk hostname, serial, model, PAN-OS version, uptime, dan mode device;
4. membandingkan model/PAN-OS dengan target profile project;
5. mendeteksi Panorama-managed status, HA status, dan multi-vsys;
6. membaca commit jobs, commit locks, pending changes, dan change summary;
7. memastikan tidak ada job atau candidate milik operator lain yang akan tertimpa;
8. mencatat capability matrix perangkat berdasarkan respons aktual, bukan hanya model catalog.

Hard block pada rilis awal:

- serial/model tidak sesuai dengan konfirmasi operator atau project;
- serial target sama dengan serial source yang telah di-collect;
- provenance file upload tidak mempunyai bukti serial source yang cukup untuk memastikan target berbeda;
- target adalah Panorama atau managed-only path yang belum didukung;
- HA aktif;
- ada pending candidate changes yang bukan milik workflow ini;
- ada commit/validate job aktif atau commit lock yang tidak dimiliki ConfigHop;
- candidate project berstatus `BLOCKED`, tidak tersedia, atau SHA-256 berubah;
- source snapshot berubah atau review belum terikat ke SHA-256 source snapshot terbaru;
- target running configuration berubah setelah baseline dipakai membangun deployment package; bangun ulang package dan minta review final diff;
- target render support bukan path yang sudah dikualifikasi;
- TLS identity tidak valid;
- out-of-band recovery belum dikonfirmasi.

### 4.3 Review manual dan deployability gate

Dashboard menampilkan provenance source di samping inventory, target profile, mapping antarmuka, dependency findings, semantic diff, dan raw comparison yang aman. Engineer harus menandai temuan review satu per satu; status `REVIEW_REQUIRED` tidak otomatis menjadi izin deploy. Keputusan review diikat ke source snapshot hash, pilihan target profile, mapping, renderer version, dan candidate hash. Perubahan pada salah satu input membatalkan keputusan lama.

Sebelum membuat deployment package, bandingkan source snapshot dengan versi sumber terbaru jika operator memilih `Recollect source`. Bila hash berubah, tampilkan diff dan minta review ulang. Jangan mengambil ulang source secara diam-diam saat staging, karena paket yang di-approve harus berasal dari snapshot yang terlihat di dashboard.

Sebelum upload, buat `Deployment Package` immutable yang berisi:

- project ID dan deployment ID;
- source snapshot origin, source serial (jika API collected), waktu collect, serta source, candidate, dan package SHA-256;
- target serial, model, PAN-OS version, dan hostname;
- exact mapping dan semantic diff;
- daftar accepted review findings;
- renderer/evidence version;
- target-local nodes yang dipertahankan atau sengaja diganti;
- timestamp dan actor/approval metadata.

Tambahkan policy validator untuk membandingkan candidate dengan running config target. Default-nya memblokir perubahan pada:

- management plane connectivity;
- device identity/hostname yang tidak dinyatakan;
- admin accounts dan authentication profile;
- HA configuration;
- Panorama/server ownership;
- certificates/private keys dan encrypted secrets;
- service route atau management access yang dapat memutus jalur API;
- virtual system topology di luar migration scope.

Keputusan implementasi yang direkomendasikan adalah membangun deployable candidate di atas fresh target running config, lalu menerapkan perubahan migrasi yang sudah direview. Transformation plan saat ini ditujukan ke XML source, sehingga perlu layer baru yang memetakan objek source ke target dan memeriksa precondition target. Jangan menerapkan source plan langsung pada target atau mengimpor full source-derived candidate sampai equivalence dan target-local preservation dapat dibuktikan. Diff final harus membandingkan deployable candidate dengan fresh target baseline, dan operator meninjaunya sebelum staging.

### 4.4 Backup sebelum mutasi

Ambil dan simpan sebagai artifacts:

- running configuration target;
- candidate configuration sebelum deployment;
- device state jika tersedia dan sesuai scope;
- system info;
- pending change summary;
- daftar job dan lock;
- hash, timestamp, target serial, dan TLS fingerprint.

Backup harus selesai, dapat diparse, memiliki hash, dan lolos size limit sebelum upload dimulai. Artifact disimpan terenkripsi at rest pada data directory lokal dan tidak diletakkan di repository.

### 4.5 Upload, load, dan validate

Urutan XML API:

1. `type=import&category=configuration` untuk mengunggah file dengan nama unik berbasis deployment ID;
2. `type=op` dengan `load config from <filename>` untuk memuat file ke candidate configuration;
3. baca change summary dan bandingkan dengan approved deployment package;
4. `type=op` dengan `validate full`;
5. poll job ID sampai terminal status atau timeout;
6. simpan warnings/details lengkap dan tampilkan hasilnya di UI.

Jika import atau load memiliki hasil ambigu karena timeout/network loss, jangan mengulang mutation secara otomatis. Reconnect, baca candidate/change summary, lalu tentukan apakah operasi sudah terjadi.

Jika validasi gagal, commit tetap tidak tersedia. Operator dapat memilih `Restore pre-deployment candidate` yang memuat kembali backup candidate, tetapi hasil baru dinyatakan pulih setelah verification berhasil.

### 4.6 Approval dan commit

Commit adalah aksi terpisah. UI harus meminta operator:

- membaca validation result dan warnings;
- memasukkan ulang target hostname atau suffix serial;
- mengonfirmasi candidate SHA-256/package SHA-256;
- mengisi alasan/change ticket;
- menyatakan out-of-band access tersedia.

Backend membuat approval token one-time dengan TTL dan mengikatnya ke deployment ID, source snapshot hash, target serial, target baseline hash, candidate hash, actor, serta change summary hash. Perubahan apa pun setelah approval membatalkan token. Sebelum commit, cek ulang target candidate/change summary agar perubahan operator lain tidak ikut ter-commit.

Commit menggunakan XML API `type=commit`, menangkap job ID, lalu mem-poll `show jobs id`. Status `success` dari request enqueue bukan bukti commit selesai. Deployment baru `SUCCEEDED` setelah job result sukses dan post-commit verification lulus.

### 4.7 Post-commit verification

Minimum verification:

- API target kembali reachable;
- serial, model, dan hostname masih sesuai;
- running configuration hash/semantic projection cocok dengan approved package;
- tidak ada unexpected pending changes;
- expected interfaces, zones, virtual routers, routes, objects, dan policies ditemukan;
- commit warnings disimpan dan ditampilkan;
- management path tetap tersedia.

Functional dataplane checks seperti routing adjacency, tunnel, HA, policy hit, dan traffic synthetic tetap `Planned` sampai ada test harness lab. UI tidak boleh menyebut deployment “healthy” jika yang terbukti hanya configuration commit.

## 5. Backend Design

Struktur modul yang disarankan:

```text
backend/src/confighop_deploy/
  client.py          # HTTP transport, TLS, timeout, redaction
  xml_response.py    # defused XML parsing dan PAN-OS error normalization
  commands.py        # typed request builders
  credentials.py     # opaque secret handle + TTL
  collection.py      # read-only source export dan consistency checks
  policy.py          # source/target preflight dan deployability gates
  artifacts.py       # source/backup/package storage + hashing/encryption
  models.py          # deployment, event, approval, artifact metadata
  repository.py      # SQLite persistence
  orchestrator.py    # state transitions dan reconciliation
  verifier.py        # pre/post-commit verification
```

Di `confighop_api`, ekstrak ingest XML saat ini dari `upload_source()` menjadi service bersama untuk file upload dan API collection. Service hanya mempromosikan source baru setelah validasi selesai dan harus menyimpan `SourceSnapshot` bersama project. Pertahankan existing source jika collect gagal. UI dan API harus membaca provenance ini dari `ProjectView`/`SourceView`. Endpoint download source yang sekarang tersedia harus mengikuti aturan masking/reveal dan akses yang sama setelah source API collection diaktifkan.

Aturan client:

- HTTPS only;
- API key di `X-PAN-KEY`, bukan query string;
- `POST` untuk request yang berisi sensitive data;
- connect/read/overall timeout terpisah;
- maximum response, source export, dan upload size;
- XML parsing dengan entity expansion disabled;
- no redirects;
- structured error mapping dari HTTP error, XML `<response status="error">`, dan job failure;
- redact API key, credentials, full XML secret nodes, dan sensitive query/body fields;
- retry otomatis hanya untuk safe read/poll dengan backoff dan jitter;
- mutation memakai idempotency/reconciliation logic, bukan blind retry.
- source export harus memisahkan respons file XML dari `<response status="error">`; jangan menganggap HTTP 200 sebagai export berhasil.

Persistence minimum:

- SQLite untuk source snapshot metadata, deployment, state transitions, device identity, approvals, dan event audit;
- encrypted artifact directory untuk source snapshot, backup, dan deployment package;
- per-device advisory lock berdasarkan serial;
- startup reconciliation untuk job berstatus non-terminal;
- retention policy dan explicit delete/export audit action.

## 6. API Contract ConfigHop

Endpoint yang disarankan:

| Method | Endpoint | Fungsi |
|---|---|---|
| `POST` | `/api/v1/device-sessions/test` | Test koneksi dengan `role=source` atau `role=target`, kembalikan identity/capabilities dan secret handle ber-TTL |
| `POST` | `/api/v1/projects/{project_id}/source/collect` | Export running config dari source handle, parse melalui ingest bersama, simpan provenance dan hash |
| `GET` | `/api/v1/projects/{project_id}/source/provenance` | Baca asal, identitas, snapshot kind, hash, waktu, dan status tanpa raw XML atau secret |
| `POST` | `/api/v1/projects/{project_id}/deployment-packages` | Freeze candidate, hashes, target identity, diff, dan review decisions |
| `POST` | `/api/v1/deployments` | Buat deployment dari package dan secret handle |
| `POST` | `/api/v1/deployments/{id}/preflight` | Jalankan checks read-only |
| `POST` | `/api/v1/deployments/{id}/stage` | Backup, import, load, dan validate |
| `GET` | `/api/v1/deployments/{id}` | Status/state/event summary |
| `GET` | `/api/v1/deployments/{id}/events` | Poll/SSE event stream tanpa secret |
| `POST` | `/api/v1/deployments/{id}/approval` | Buat approval terikat hash dan TTL |
| `POST` | `/api/v1/deployments/{id}/commit` | Enqueue commit menggunakan approval token |
| `POST` | `/api/v1/deployments/{id}/reconcile` | Read-only recovery setelah ambiguous network result |
| `POST` | `/api/v1/deployments/{id}/recover` | Load/validate/commit backup melalui workflow recovery |
| `POST` | `/api/v1/deployments/{id}/cancel` | Cancel hanya pada state yang aman |

`POST /source/collect` mengubah project lokal, tetapi hanya melakukan operasi read-only pada firewall sumber. Endpoint itu memakai `Idempotency-Key` untuk mencegah collect ganda yang tidak disengaja. Semua mutation deployment juga menerima `Idempotency-Key`. API mengembalikan `409` untuk transition yang salah, `423` untuk device lock, `422` untuk failed gate, dan error code domain yang stabil. API key atau raw secret tidak pernah dikembalikan dalam response.

## 7. UI Plan

Perbarui section `Source Configuration` yang sudah ada, lalu tambahkan section deployment setelah `Migration Results`. Progression yang terlihat di dashboard:

1. `Choose source`: pilih `Collect from firewall` atau `Upload XML`; kedua jalur berakhir pada inventory yang sama.
2. `Connect source`: isi host, port, API key baca, dan CA/fingerprint; `Test source connection` menampilkan identitas perangkat.
3. `Collect running config`: tampilkan progress export, status parse, ukuran, waktu collect, SHA-256, dan provenance. Jika collect gagal, source lama tetap terlihat dengan label yang jelas.
4. `Review migration`: tampilkan source dan target model, mapping manual, warnings, semantic diff, serta keputusan engineer yang terikat ke snapshot hash.
5. `Candidate ready`: tampilkan candidate SHA, target profile, findings, dan deployability status.
6. `Connect target`: host, port, API key target, CA/fingerprint, expected serial, dan tombol `Test target connection`.
7. `Preflight`: identity target, locks/jobs, pending changes, HA/Panorama status, dan hard blockers.
8. `Stage candidate`: backup, upload, load, change summary, serta validate progress.
9. `Awaiting approval`: validation output, warnings, exact target confirmation, dan change ticket.
10. `Commit`: job queue/running progress dengan timestamps.
11. `Verify`: evidence per check dan final state.
12. `Recovery`: tampil bila state mendukung recovery, dengan dampak dan confirmation terpisah.

UI state wajib:

- source empty, source connecting, collecting, parsing, source review required;
- target connecting, staging, polling, awaiting approval, committing, verifying;
- success;
- source authentication/export/TLS/format errors;
- validation failed;
- connection lost dengan hasil mutation ambigu;
- device busy/locked;
- credentials expired;
- recovery required;
- audit/export available.

Tombol harus menyatakan aksi aktual: `Test Source Connection`, `Collect Running Config`, `Test Target Connection`, `Back Up and Stage Candidate`, `Validate on Firewall`, dan `Commit Validated Candidate`. Tampilkan source serial dan target serial bersamaan pada confirmation. Jika keduanya sama, hentikan alur.

## 8. Security Requirements

- Tetap bind backend ke `127.0.0.1` selama belum ada app authentication dan RBAC.
- Tambahkan production feature flag yang default-nya `off`, misalnya `CONFIGHOP_LIVE_DEPLOYMENT=disabled`.
- Tambahkan allowlist/denylist source dan target network serta proteksi SSRF; resolve DNS sekali per session dan verifikasi peer address.
- Jangan menerima URL lengkap dari UI; terima host dan port terstruktur.
- API key tidak boleh masuk access log, exception, telemetry, browser storage, screenshot artifact, atau audit payload.
- Gunakan least-privilege PAN-OS admin role terpisah: source hanya untuk system info/config export dan read-only checks; target untuk op, import/export, config read, dan commit sesuai phase.
- Certificate verification default wajib. Lab override hanya melalui explicit fingerprint pinning yang terlihat di UI dan audit.
- Rate-limit connection test dan secret failures.
- Encrypt source XML, target backups, dan deployment package; sediakan retention/delete policy. Raw config bisa memuat password hash, shared secret, dan private material.
- Mask raw XML di dashboard secara default; batasi raw download/reveal dan jangan kirim XML penuh ke telemetry atau error response.
- Audit setiap state transition, actor, source/target serial, artifact hash, approval, request category, response code, dan job ID tanpa menyimpan secret.

## 9. Delivery Phases

### P0: Source collection dan no-mutation connectivity

- Metadata source snapshot, deployment model, state machine, audit event, dan device lock.
- Secure XML API client, response parser, redaction, TLS pinning, dan timeout policy.
- API source collection untuk running config, provenance, dan parser ingest bersama dengan file upload.
- UI `Collect from firewall`, `Test Source Connection`, source identity, snapshot status, dan read-only target preflight.
- Penyimpanan source XML terenkripsi atau working file berumur pendek dengan akses terbatas, serta masking pada raw preview/download.
- Fake PAN-OS server untuk deterministic source export dan target read-only tests.
- Live deployment feature flag tetap `off`.

Exit gate: collect read-only dari lab source menghasilkan inventory yang setara dengan upload file yang sama; snapshot hash, waktu, dan serial terlihat; collect gagal tidak mengganti source lama; source dan target identity terbukti; log scan tidak menemukan API key atau raw XML.

### P1: Lab staging tanpa commit

- Immutable deployment package dan deployability policy.
- Manual review mengikat keputusan engineer ke source snapshot hash, target profile, dan mapping; recollect menginvalidasi review/package lama.
- Build deployable candidate dari fresh target running config dengan source-to-target mapping yang telah direview dan final diff terhadap target.
- Running/candidate backup artifacts.
- Import, load, full validate, job polling, dan change-summary verification.
- Restore pre-deployment candidate tanpa commit.
- UI progress/error/ambiguous-result states.

Exit gate: staging dan validation lulus di firewall lab untuk source yang dikumpulkan via API; target-local settings tetap utuh; invalid candidate diblokir; timeout setelah mutation dapat direconcile tanpa duplicate mutation.

### P2: Lab commit dan recovery drill

- Approval token terikat hash/target dengan TTL.
- Commit orchestration dan job polling.
- Post-commit verification.
- Backup restore, validation, recovery commit, dan verification.
- Simulasi loss of API connectivity dan operator handoff ke out-of-band path.

Exit gate: minimum dua siklus deploy dan restore berhasil pada lab target; satu negative drill terdokumentasi; tidak ada langkah recovery yang hanya bersifat teoritis.

### P3: Production hardening

- App authentication, RBAC, separation of duties, durable secret manager.
- Signed audit export, retention, backup encryption/key rotation.
- Production target allowlist dan change-management integration.
- HA/Panorama diperlakukan sebagai workstream terpisah dengan lab gate sendiri.
- Canary/pilot pada target non-critical dengan approved runbook.

Exit gate: security review, operator runbook, recovery drill, browser UAT, dan production approval selesai. Hanya pada tahap ini label UI boleh berubah dari `Lab deployment` menjadi `Production available`.

## 10. Test Strategy

### Unit

- XML success/error/job response parsing;
- binary configuration export versus XML API error response detection;
- source provenance, size/hash, dan atomic replacement;
- source profile/serial/PAN-OS consistency serta source-target serial mismatch;
- collect ulang menginvalidasi review, candidate, dan package;
- malformed/oversized/XXE response rejection;
- state transition table;
- secret redaction;
- TLS/fingerprint policy;
- hash-bound approval invalidation;
- retry versus reconcile decisions;
- target-local preservation policy.
- source-to-target transformation preconditions terhadap fresh target baseline.

### Integration dengan fake PAN-OS server

- auth failure dan permission denied;
- source export success/timeout/truncation/error XML;
- source config dengan pending uncommitted candidate tetap memakai running snapshot;
- source berubah saat collect atau recollect;
- model/serial/PAN-OS mismatch;
- self-signed/changed certificate;
- import success/failure/timeout;
- load success dengan lost response;
- validation queued/success/failure/timeout;
- concurrent commit lock/job;
- commit enqueue success tetapi final job failure;
- service restart dan reconciliation;
- recovery path.

### Browser UAT

- keyboard/focus dan readable error states;
- switch antara upload XML dan collect API tanpa kehilangan source lama sebelum collect sukses;
- source serial, waktu collect, hash, dan origin terlihat sebelum review;
- collect ulang menghapus review lama dan menampilkan diff source snapshots;
- secret tidak pernah muncul kembali setelah submit;
- refresh/resume deployment;
- exact confirmation dan expired approval;
- progress polling/SSE disconnect;
- commit button tidak tersedia sebelum seluruh gate lulus;
- recovery tidak ditampilkan sebagai sukses sebelum verification.

### Physical/virtual lab

- supported PAN-OS trains dan exact target models;
- collect dari physical/virtual source melalui API, lalu verifikasi parity parser dengan export manual dari perangkat yang sama;
- migration drill penuh: collect source A, review manual, stage/validate/commit ke target B dengan serial berbeda;
- export API gagal atau source berubah selama pengambilan;
- clean device dan device dengan pending changes;
- invalid candidate;
- management certificate rotation/mismatch;
- API interruption saat load, validate, dan commit;
- backup restore dan post-restore verification;
- out-of-band recovery drill.

Targeted unit/integration checks tidak boleh dilaporkan sebagai bukti production readiness. Browser UAT dan lab-device evidence harus dilaporkan terpisah.

## 11. Definition of Done

Fitur baru dapat disebut `Lab Available` jika:

- seluruh P0 sampai P2 exit gate lulus;
- source running configuration dapat di-collect via API dengan izin baca dan masuk ke pipeline analisis yang sama dengan upload XML;
- UI menunjukkan provenance, identitas source, waktu collect, dan hash; source lama tetap utuh jika collect gagal;
- perubahan source snapshot membatalkan review dan deployment package lama;
- engineer telah meninjau mapping, findings, dan final diff terhadap target sebelum staging;
- source dan target serial berbeda dan terverifikasi;
- hanya candidate `READY` atau explicitly reviewed path yang memenuhi deployability policy dapat distage;
- backup artifacts tersedia dan terverifikasi sebelum mutasi;
- commit selalu memerlukan approval baru yang terikat hash dan target;
- setiap async job dipantau sampai terminal result;
- ambiguous mutation direconcile, bukan diulang secara buta;
- secret redaction dan TLS validation dibuktikan oleh test;
- recovery berhasil pada perangkat lab;
- UI menunjukkan source, target identity, latest state, warning, failure, dan audit evidence secara eksplisit;
- README tetap menyatakan batas `lab only` dan fitur flag default `off`.

## 12. Open Decisions Sebelum Implementasi

1. Apakah P1 akan mengimpor candidate yang diturunkan langsung dari source, atau membuat full deployable candidate baru dari fresh running config target lalu menerapkan reviewed transformation secara lokal? Rekomendasi: pilihan kedua, lalu import/load satu file immutable.
2. Perangkat lab mana yang pertama menjadi source dan target? Catat model, versi PAN-OS, dan izin API keduanya sebelum menetapkan evidence matrix.
3. Parameter export mana yang menghasilkan full running config dengan root `<config>` pada versi PAN-OS lab? Buktikan juga perilaku saat source memiliki uncommitted candidate changes.
4. Untuk source dari upload manual, bukti identitas apa yang cukup sebelum deployment? Rekomendasi: sambungkan read-only ke source dan cocokkan hash running snapshot dengan file yang di-upload.
5. Apakah artifact encryption menggunakan Windows DPAPI/credential manager untuk local-first atau library cross-platform dengan operator-provided key?
6. Apakah v1 hanya single-vsys? Rekomendasi: ya, sampai multi-vsys scope dan partial validation terbukti.
7. Berapa retention source snapshots, target backups, deployment artifacts, dan audit events?
8. Siapa yang boleh approve commit pada production phase, dan apakah harus berbeda dari pembuat package?

## 13. Referensi Vendor

- [PAN-OS XML API request types and actions](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions)
- [API authentication and security](https://docs.paloaltonetworks.com/ngfw/api/api-authentication-and-security)
- [Import files through the XML API](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/import-files-api)
- [Run operational mode commands](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/run-operational-mode-commands-api)
- [Commit through the XML API](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/commit)
- [Export files through the XML API](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/export-files-api)
- [Configuration API: running and candidate configuration access](https://docs.paloaltonetworks.com/ngfw/api/pan-os-xml-api-request-types-and-actions/configuration-api)
- [Commit configuration changes and validation behavior](https://docs.paloaltonetworks.com/ngfw/pan-os-cli-quick-start/use-the-cli/commit-configuration-changes)
