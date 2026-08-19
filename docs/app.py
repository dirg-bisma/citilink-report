"""
Flight Realization Migrator — Web API + UI (FastAPI)
====================================================
Membungkus core.migrate() sebagai layanan HTTP: melayani UI web (browser)
maupun otomasi (n8n).

Endpoint:
    GET  /              -> halaman UI web (upload manual)
    GET  /health        -> cek status ({"status": "ok"})
    GET  /config        -> info UI (apakah API key diperlukan)
    POST /migrate       -> migrasi, balikan file .xlsx mentah (untuk n8n)
    POST /migrate/json  -> migrasi, balikan JSON (ringkasan + log + file base64)
                           dipakai oleh UI web
    POST /migrate/telegram -> migrasi dari file_id Telegram; unduh file dari
                           Telegram, proses, kirim hasil .xlsx balik ke chat.
                           Dipakai oleh workflow n8n (bot Telegram).
    GET  /docs           -> dokumentasi API otomatis (Swagger)

Keamanan (Fase 5):
    Endpoint /migrate & /migrate/json dilindungi API key bila environment
    variable API_KEY diset. Klien mengirim key lewat header:
        Authorization: Bearer <key>     (mis. dari n8n)
        X-API-Key: <key>                (mis. dari UI web)
    Bila API_KEY tidak diset, proteksi NONAKTIF (mode lokal/dev) dan sebuah
    peringatan dicatat di log.

Menjalankan lokal:
    pip install -r requirements-web.txt
    uvicorn app:app --reload --port 8000

Sifat: stateless. Tiap request diproses di direktori temporer yang langsung
dihapus setelah selesai; tidak ada data pengguna yang disimpan permanen.
"""

import os
import hmac
import time
import base64
import logging
import tempfile
import datetime
import threading
from pathlib import Path

import requests
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import core
import database
import auth

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# --- Keamanan: API key dari environment variable ---
API_KEY = os.environ.get("API_KEY", "").strip()
_log = logging.getLogger("uvicorn.error")
if not API_KEY:
    _log.warning(
        "API_KEY tidak diset — endpoint /migrate TERBUKA tanpa proteksi. "
        "Set environment variable API_KEY sebelum dipakai publik/n8n."
    )

# --- Token bot Telegram (untuk endpoint /migrate/telegram) ---
# Dipakai untuk mengunduh file dari Telegram (getFile) dan mengirim hasil
# balik (sendDocument). Bila kosong, endpoint /migrate/telegram menolak (500).
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    """Dependency proteksi. Terima 'X-API-Key', 'Authorization: Bearer <API_KEY>',
    atau 'Authorization: Bearer <JWT_TOKEN>'.
    """
    # 1. Cek API Key statis terlebih dahulu jika terkonfigurasi di server
    if API_KEY:
        provided = x_api_key
        if not provided and authorization:
            auth_val = authorization.strip()
            if auth_val.lower().startswith("bearer "):
                provided = auth_val[7:]
            else:
                provided = auth_val
        if provided and hmac.compare_digest(provided.strip(), API_KEY):
            return

    # 2. Cek token JWT jika authorization header disediakan
    if authorization:
        auth_val = authorization.strip()
        if auth_val.lower().startswith("bearer "):
            token = auth_val[7:]
            try:
                from jose import jwt as jose_jwt
                payload = jose_jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
                username = payload.get("sub")
                if username:
                    user = database.get_user_by_username(username)
                    if user:
                        return
            except Exception:
                pass

    # Jika API_KEY diset tapi tidak ada autentikasi yang lolos
    if API_KEY:
        _log.warning(
            f"Autentikasi ditolak. X-API-Key: {repr(x_api_key)}, "
            f"Authorization: {repr(authorization)}, "
            f"Parsed provided: {repr(provided if 'provided' in locals() else None)}"
        )
        raise HTTPException(status_code=401, detail="API key atau Token JWT tidak valid atau tidak ada.")


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str
    role: str = "user"


app = FastAPI(
    title="Flight Realization Migrator API",
    description=(
        "API migrasi realisasi penerbangan Citilink. Unggah file master, form "
        "realisasi, dan (opsional) PDF PPRP; terima form realisasi terisi."
    ),
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    """Inisialisasi database SQLite saat aplikasi FastAPI dimulai."""
    database.init_db()


@app.post("/auth/login")
def login(payload: UserLogin):
    user = database.get_user_by_username(payload.username)
    if not user or not auth.verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(
            status_code=400,
            detail="Username atau password salah."
        )
    access_token = auth.create_access_token(data={"sub": user["username"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"]
    }


@app.post("/auth/register")
def register(payload: UserRegister, current_user: dict = Depends(auth.RoleChecker(["admin"]))):
    if payload.role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Role tidak valid. Harus 'admin' atau 'user'.")
    
    hashed = auth.get_password_hash(payload.password)
    new_user = database.create_user(payload.username, hashed, payload.role)
    if not new_user:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar.")
    return {
        "id": new_user["id"],
        "username": new_user["username"],
        "role": new_user["role"]
    }


@app.get("/auth/me")
def get_me(current_user: dict = Depends(auth.get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"]
    }


# Ekstensi yang diizinkan per jenis input
MASTER_EXTS = {".xls", ".xlsx", ".xlsm"}
FORM_EXTS = {".xlsx", ".xlsm"}
PDF_EXTS = {".pdf"}

XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _check_ext(filename: str, allowed: set, label: str) -> str:
    """Validasi ekstensi file; kembalikan suffix (lowercase) bila valid."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ekstensi {label} tidak didukung: '{suffix or '(kosong)'}'. "
                f"Diperbolehkan: {', '.join(sorted(allowed))}"
            ),
        )
    return suffix


async def _run_migration(master, form, month, year, hub, pprp, start_date=None, end_date=None, timezone_mode="default", wtt=None):
    """Proses migrasi dari satu atau beberapa file master terunggah.
    
    Kembalikan (data, summary, download_name).
    """
    master_files = master if isinstance(master, list) else [master]
    
    # JITU: Tulis log request ke file
    with open("server_run.log", "a", encoding="utf-8") as lf:
        lf.write(f"\n========================================\n")
        lf.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n")
        lf.write(f"Master files: {[m.filename for m in master_files]}\n")
        lf.write(f"Form file: {form.filename}\n")
        lf.write(f"Month: {month}, Year: {year}, Hub: {hub}\n")
        lf.write(f"Start date input: {start_date}, End date input: {end_date}\n")
    
    # Validasi file master dan form
    for m in master_files:
        _check_ext(m.filename, MASTER_EXTS, "master")
    _check_ext(form.filename, FORM_EXTS, "form realisasi")
    
    # Validasi PDF PPRP dan WTT
    pdf_files = [p for p in (pprp or []) if p and p.filename]
    for p in pdf_files:
        _check_ext(p.filename, PDF_EXTS, "PDF PPRP")
        
    wtt_files = [w for w in (wtt or []) if w and w.filename]
    for w in wtt_files:
        _check_ext(w.filename, PDF_EXTS, "PDF WTT")
        
    parsed_start = None
    if start_date:
        try:
            parsed_start = datetime.date.fromisoformat(start_date)
        except ValueError:
            pass
            
    if parsed_start:
        if month is None:
            month = parsed_start.month
        if year is None:
            year = parsed_start.year

    parsed_end = None
    if end_date:
        try:
            parsed_end = datetime.date.fromisoformat(end_date)
        except ValueError:
            pass
            
    with tempfile.TemporaryDirectory(prefix="migrasi_") as tmp:
        tmp_path = Path(tmp)
        form_path = tmp_path / "form.xlsx"
        output_path = tmp_path / "output.xlsx"
        
        # Tulis form template
        form_path.write_bytes(await form.read())
        
        # Tulis master files
        master_paths = []
        for i, m in enumerate(master_files):
            suffix = Path(m.filename).suffix.lower()
            mp = tmp_path / f"master_{i}{suffix}"
            mp.write_bytes(await m.read())
            master_paths.append(str(mp))
            
        # Tulis PDF files (PPRP)
        pdf_paths = []
        for i, p in enumerate(pdf_files):
            pp = tmp_path / f"pprp_{i}.pdf"
            pp.write_bytes(await p.read())
            pdf_paths.append(str(pp))
            
        # Tulis PDF files (WTT)
        wtt_paths = []
        for i, w in enumerate(wtt_files):
            wp = tmp_path / f"wtt_{i}.pdf"
            wp.write_bytes(await w.read())
            wtt_paths.append(str(wp))
            
        # Tentukan jenis migrasi
        is_single = len(master_paths) == 1
        
        try:
            if is_single:
                # Coba deteksi bulan & tahun secara otomatis dari file master
                detected_month, detected_year = core.detect_master_month_and_year(master_paths[0])
                actual_month = detected_month if detected_month is not None else month
                actual_year = detected_year if detected_year is not None else year
                
                # JITU & TEMBUS: Pastikan filter tanggal (jika diisi) selalu merujuk pada bulan & tahun aktual yang dimigrasikan
                import calendar
                _, last_day = calendar.monthrange(actual_year, actual_month)
                
                if parsed_start:
                    if parsed_start.month != actual_month or parsed_start.year != actual_year:
                        start_day = min(parsed_start.day, last_day)
                        parsed_start = datetime.date(actual_year, actual_month, start_day)
                        
                if parsed_end:
                    if parsed_end.month != actual_month or parsed_end.year != actual_year:
                        end_day = min(parsed_end.day, last_day)
                        parsed_end = datetime.date(actual_year, actual_month, end_day)
                
                # Jika filter tanggal kosong, kita isi secara eksplisit dengan rentang penuh agar aman
                if not parsed_start:
                    parsed_start = datetime.date(actual_year, actual_month, 1)
                if not parsed_end:
                    parsed_end = datetime.date(actual_year, actual_month, last_day)
                
                summary = core.migrate(
                    master_path=master_paths[0],
                    form_path=str(form_path),
                    output_path=str(output_path),
                    month=actual_month,
                    year=actual_year,
                    hub=hub,
                    pdf_paths=pdf_paths,
                    start_date=parsed_start,
                    end_date=parsed_end,
                    timezone_mode=timezone_mode,
                    wtt_paths=wtt_paths
                )
                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                mode_str = timezone_mode.upper()
                download_name = f"realisasi_{hub.upper()}_{actual_year}_{now_str}_{mode_str}.xlsx"
            else:
                summary = core.migrate_multi(
                    master_paths=master_paths,
                    form_path=str(form_path),
                    output_path=str(output_path),
                    hub=hub,
                    pdf_paths=pdf_paths,
                    timezone_mode=timezone_mode,
                    wtt_paths=wtt_paths
                )
                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                mode_str = timezone_mode.upper()
                download_name = f"realisasi_{hub.upper()}_ANNUAL_{now_str}_{mode_str}.xlsx"
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            with open("server_run.log", "a", encoding="utf-8") as lf:
                lf.write(f"ERROR: {type(e).__name__}: {e}\nTraceback: {tb}\n")
            traceback.print_exc()
            raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
            
        # JITU: Tulis log sukses
        with open("server_run.log", "a", encoding="utf-8") as lf:
            lf.write(f"SUCCESS: {download_name}\n")
            lf.write(f"Filled rows: {summary.get('filled_rows')}\n")
            lf.write(f"Inserted blocks: {summary.get('inserted_blocks')}\n")
            lf.write(f"Log: {summary.get('log')}\n")
            
        data = output_path.read_bytes()
        
    return data, summary, download_name


@app.get("/health")
def health():
    """Health check untuk monitoring (Sumopod/n8n). Tidak diproteksi."""
    return {"status": "ok"}


@app.get("/config")
def config():
    """Info untuk UI: apakah server memerlukan API key. Tidak membocorkan key."""
    return {"auth_required": bool(API_KEY)}


@app.post("/migrate", dependencies=[Depends(require_api_key)])
async def migrate_endpoint(
    master: list[UploadFile] = File(..., description="Data Ground Handling Punctuality (.xls/.xlsx)"),
    form: UploadFile = File(..., description="Template form realisasi (.xlsx)"),
    month: int = Form(None, description="Bulan (1-12)"),
    year: int = Form(None, description="Tahun"),
    hub: str = Form("SUB", description="Kode hub keberangkatan (default SUB)"),
    pprp: list[UploadFile] = File(default=[], description="Surat PPRP (.pdf), boleh lebih dari satu"),
    wtt: list[UploadFile] = File(default=[], description="Dokumen WTT (.pdf), boleh lebih dari satu"),
    start_date: str = Form(None, description="Tanggal Mulai filter (YYYY-MM-DD)"),
    end_date: str = Form(None, description="Tanggal Selesai filter (YYYY-MM-DD)"),
    timezone_mode: str = Form("default", description="Format konversi waktu: default, utc, atau local"),
):
    """Migrasi -> file .xlsx mentah (cocok untuk n8n / unduhan langsung).

    Ringkasan hasil ada di header respons: X-Filled-Rows, X-Inserted-Blocks.
    Proteksi: kirim header 'Authorization: Bearer <API_KEY>' atau 'X-API-Key'.
    """
    data, summary, download_name = await _run_migration(
        master, form, month, year, hub, pprp, start_date, end_date, timezone_mode, wtt
    )
    return Response(
        content=data,
        media_type=XLSX_MEDIA,
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Filled-Rows": str(summary["filled_rows"]),
            "X-Inserted-Blocks": str(summary["inserted_blocks"]),
        },
    )


@app.post("/migrate/json", dependencies=[Depends(require_api_key)])
async def migrate_json_endpoint(
    master: list[UploadFile] = File(...),
    form: UploadFile = File(...),
    month: int = Form(None),
    year: int = Form(None),
    hub: str = Form("SUB"),
    pprp: list[UploadFile] = File(default=[]),
    wtt: list[UploadFile] = File(default=[]),
    start_date: str = Form(None),
    end_date: str = Form(None),
    timezone_mode: str = Form("default"),
):
    """Migrasi -> JSON (ringkasan + log + file base64). Dipakai UI web."""
    data, summary, download_name = await _run_migration(
        master, form, month, year, hub, pprp, start_date, end_date, timezone_mode, wtt
    )
    return JSONResponse({
        "filled_rows": summary["filled_rows"],
        "inserted_blocks": summary["inserted_blocks"],
        "results": summary.get("results", []),
        "log": summary["log"],
        "filename": download_name,
        "file_base64": base64.b64encode(data).decode("ascii"),
    })


# ----------------------------------------------------------------------------
# Endpoint Telegram (dipakai workflow n8n)
# ----------------------------------------------------------------------------

class TgFile(BaseModel):
    """Referensi satu file di Telegram (dari update bot)."""
    file_id: str
    file_name: str | None = None


class TelegramMigrateRequest(BaseModel):
    """Payload dari n8n untuk migrasi berbasis file Telegram."""
    chat_id: int
    master: TgFile
    form: TgFile
    pprp: list[TgFile] = []
    token: str | None = None  # token sesi; bila diisi, PPRP diambil dari store server
    month: int
    year: int
    hub: str = "SUB"


class TgPprpAdd(BaseModel):
    """Satu PPRP yang ditambahkan ke sesi (anti race-condition)."""
    chat_id: int
    token: str
    file_id: str
    file_name: str | None = None


# ---------------------------------------------------------------------------
# Akumulasi PPRP per sesi Telegram — aman dari race-condition.
#
# Saat >1 PDF dikirim nyaris bersamaan, n8n menjalankan eksekusi paralel dan
# akumulasi di state n8n bisa saling menimpa (last-write-wins). Di sini
# penambahan dilindungi threading.Lock sehingga selalu atomic. Sesi dibedakan
# dengan `token` (dibuat n8n saat /migrasi). Key store: "chat_id:token".
#
# PENTING: state ini in-memory -> aplikasi WAJIB berjalan 1 worker uvicorn
# (default). Jangan menjalankan dengan --workers > 1 tanpa store bersama.
# ---------------------------------------------------------------------------
_tg_pprp_store: dict[str, dict] = {}
_tg_pprp_lock = threading.Lock()
_TG_PPRP_TTL = 3600  # detik; entri sesi lebih tua dari ini dianggap basi & dibuang


def _tg_pprp_purge_locked() -> None:
    """Buang sesi kadaluarsa. Harus dipanggil saat memegang _tg_pprp_lock."""
    now = time.time()
    stale = [k for k, v in _tg_pprp_store.items() if now - v["ts"] > _TG_PPRP_TTL]
    for k in stale:
        _tg_pprp_store.pop(k, None)


@app.post("/migrate/telegram/pprp")
def telegram_add_pprp(req: TgPprpAdd):
    """Tambah satu PPRP ke sesi (atomic). Kembalikan jumlah PPRP terkini.

    Dedupe berdasarkan file_id agar retry/duplikasi tidak menggandakan.
    """
    _log.info(f"PPRP Store: Adding file {req.file_name} (ID: {req.file_id}) for chat_id={req.chat_id}, token={req.token}")
    key = f"{req.chat_id}:{req.token}"
    with _tg_pprp_lock:
        _tg_pprp_purge_locked()
        entry = _tg_pprp_store.setdefault(key, {"ts": time.time(), "items": []})
        entry["ts"] = time.time()
        if not any(it["file_id"] == req.file_id for it in entry["items"]):
            entry["items"].append(
                {"file_id": req.file_id, "file_name": req.file_name}
            )
        count = len(entry["items"])
    return {"ok": True, "count": count}


def _tg_api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _tg_download(file_id: str, dest: Path) -> None:
    """Unduh file Telegram (by file_id) ke path lokal `dest`."""
    r = requests.get(_tg_api("getFile"), params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    info = r.json()
    if not info.get("ok"):
        raise RuntimeError(f"getFile gagal: {info}")
    file_path = info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    fr = requests.get(url, timeout=60)
    fr.raise_for_status()
    dest.write_bytes(fr.content)


def _tg_send_message(chat_id: int, text: str) -> None:
    """Kirim pesan teks (best-effort; kegagalan hanya dicatat)."""
    try:
        requests.post(
            _tg_api("sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=30,
        )
    except Exception:
        _log.exception("Gagal mengirim pesan Telegram")


def _tg_send_document(chat_id: int, path: Path, caption: str | None = None) -> None:
    """Kirim file dokumen ke chat Telegram."""
    with path.open("rb") as f:
        files = {"document": (path.name, f, XLSX_MEDIA)}
        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        r = requests.post(_tg_api("sendDocument"), data=data, files=files, timeout=120)
    r.raise_for_status()


def _need_ext(file_name: str | None, allowed: set, label: str) -> str:
    """Validasi ekstensi dari nama file; ValueError bila tidak didukung."""
    suffix = Path(file_name or "").suffix.lower()
    if suffix not in allowed:
        raise ValueError(
            f"Ekstensi {label} tidak didukung: '{suffix or '(kosong)'}'. "
            f"Diperbolehkan: {', '.join(sorted(allowed))}"
        )
    return suffix


@app.post("/migrate/telegram")
def migrate_telegram_endpoint(req: TelegramMigrateRequest):
    """Migrasi dari file Telegram → kirim hasil balik ke chat via bot.

    n8n cukup mengirim JSON (chat_id + file_id master/form/pprp + bulan/tahun/
    hub). Server mengunduh file dari Telegram, menjalankan migrasi, lalu
    mengirim `output.xlsx` balik ke chat. Balikan JSON berisi ringkasan.
    Proteksi: header 'Authorization: Bearer <API_KEY>'.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="TELEGRAM_BOT_TOKEN belum diset di server.",
        )

    try:
        master_suffix = _need_ext(req.master.file_name, MASTER_EXTS, "master")
        _need_ext(req.form.file_name, FORM_EXTS, "form realisasi")

        # Daftar PPRP: bila ada token, ambil dari store server (akumulasi
        # atomic) lalu bersihkan sesinya; jika tidak, pakai yang di body.
        pprp_list = list(req.pprp)
        _log.info(f"Telegram Migration call: chat_id={req.chat_id}, token={req.token}, req.pprp count={len(req.pprp)}")
        
        target_token = req.token
        if not target_token or target_token == "None" or target_token == "null":
            prefix = f"{req.chat_id}:"
            with _tg_pprp_lock:
                matching_keys = [k for k in _tg_pprp_store.keys() if k.startswith(prefix)]
                if matching_keys:
                    newest_key = max(matching_keys, key=lambda k: _tg_pprp_store[k]["ts"])
                    target_token = newest_key.split(":", 1)[1]
                    _log.info(f"Telegram Migration: Fallback resolved token={target_token} from keys={matching_keys}")

        if target_token and target_token != "None" and target_token != "null":
            key = f"{req.chat_id}:{target_token}"
            with _tg_pprp_lock:
                entry = _tg_pprp_store.pop(key, None)
            if entry:
                pprp_list = [TgFile(**it) for it in entry["items"]]
                _log.info(f"Telegram Migration: retrieved {len(pprp_list)} items from store using key {key}")
            else:
                _log.info(f"Telegram Migration: no entry found in store for key {key}")

        with tempfile.TemporaryDirectory(prefix="migrasi_tg_") as tmp:
            tmp_path = Path(tmp)
            master_path = tmp_path / f"master{master_suffix}"
            form_path = tmp_path / "form.xlsx"
            output_path = tmp_path / "output.xlsx"

            _tg_download(req.master.file_id, master_path)
            _tg_download(req.form.file_id, form_path)

            pdf_paths = []
            for i, p in enumerate(pprp_list):
                pp = tmp_path / f"pprp_{i}.pdf"
                _tg_download(p.file_id, pp)
                pdf_paths.append(str(pp))

            _log.info(f"Telegram Migration: Downloaded {len(pdf_paths)} PDF files successfully: {[p.file_name for p in pprp_list]}")

            summary = core.migrate(
                master_path=str(master_path),
                form_path=str(form_path),
                output_path=str(output_path),
                month=req.month,
                year=req.year,
                hub=req.hub,
                pdf_paths=pdf_paths,
                log=lambda msg: _log.info(f"Migrator: {msg}"),
            )

            download_name = f"realisasi_{req.hub.upper()}_{req.month:02d}_{req.year}.xlsx"
            final_path = tmp_path / download_name
            output_path.rename(final_path)
            caption = (
                f"✅ Migrasi selesai.\n"
                f"{summary['filled_rows']} baris terisi, "
                f"{summary['inserted_blocks']} blok perubahan."
            )
            _tg_send_document(req.chat_id, final_path, caption)
    except Exception as e:
        _tg_send_message(req.chat_id, f"❌ Migrasi gagal: {type(e).__name__}: {e}")
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")

    return {
        "ok": True,
        "filled_rows": summary["filled_rows"],
        "inserted_blocks": summary["inserted_blocks"],
    }


@app.get("/")
def root():
    """Sajikan UI web bila tersedia; jika belum, tampilkan info API."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({
        "app": "Flight Realization Migrator API",
        "endpoints": {"health": "/health", "migrate": "POST /migrate", "docs": "/docs"},
    })


# UI aset statis (dipasang bila folder ada)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
