import csv
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings

from .profiling import MAX_BYTES, preview, profile, read_table
from .store import DatasetStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datasets", tags=["datasets"])


class Dataset(BaseModel):
    id: UUID
    name: str
    sheet: str | None
    row_count: int
    created_at: datetime


def get_store():
    store = DatasetStore(get_settings().database_url)
    try:
        store.initialize()
        yield store
    except psycopg.Error:
        logger.exception("Dataset database operation failed")
        raise HTTPException(503, "Veritabanına erişilemiyor. Lütfen tekrar deneyin.") from None


@router.post("", response_model=Dataset, status_code=201)
def upload_dataset(
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    store: DatasetStore = Depends(get_store),
):
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise HTTPException(415, "Yalnızca CSV ve XLSX dosyaları kabul edilir.")
    id = uuid4()
    directory = Path(get_settings().data_dir) / str(id)
    try:
        directory.mkdir(parents=True)
        path = directory / ("original" + suffix)
        size = 0
        with path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Dosya boyutu 50 MB sınırını aşıyor.")
                target.write(chunk)
        if size == 0:
            raise HTTPException(422, "Dosya boş.")
        try:
            frame, selected = read_table(path, suffix, sheet)
            outputs = {"profile": profile(frame), "preview": preview(frame)}
        except (ValueError, csv.Error, UnicodeError, KeyError, IndexError) as exc:
            raise HTTPException(422, f"Dosya okunamadı: {exc}") from exc
        except Exception as exc:
            logger.info("Invalid dataset format", exc_info=True)
            raise HTTPException(422, "Dosya okunamadı. Dosya biçimini kontrol edin.") from exc
        for key, value in outputs.items():
            (directory / f"{key}.json").write_text(
                json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8"
            )
        return store.insert(id, name, selected, len(frame))
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        file.file.close()


@router.get("", response_model=list[Dataset])
def list_datasets(store: DatasetStore = Depends(get_store)):
    return store.list()


def artifact(id: UUID, kind: str, store: DatasetStore):
    if store.get(id) is None:
        raise HTTPException(404, "Veri kümesi bulunamadı.")
    path = Path(get_settings().data_dir) / str(id) / f"{kind}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(503, "Veri kümesi dosyası okunamıyor.") from None


@router.get("/{id}/profile")
def dataset_profile(id: UUID, store: DatasetStore = Depends(get_store)):
    return artifact(id, "profile", store)


@router.get("/{id}/preview")
def dataset_preview(id: UUID, store: DatasetStore = Depends(get_store)):
    return artifact(id, "preview", store)
