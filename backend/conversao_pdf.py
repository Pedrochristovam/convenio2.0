"""Conversão DOCX -> PDF fiel ao modelo (caixas de seleção, tabelas e destaques do Word)."""

import logging
import os
import shutil
import subprocess
import tempfile
import threading

logger = logging.getLogger(__name__)

WD_FORMAT_PDF = 17
# Uma conversão por vez: cada uma abre uma instância própria do Word, que pesa na memória
_trava = threading.Lock()


class ConversaoPdfIndisponivel(RuntimeError):
    pass


def _via_word(origem: str, destino: str) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(origem, ReadOnly=True, AddToRecentFiles=False)
        try:
            doc.SaveAs2(destino, FileFormat=WD_FORMAT_PDF)
        finally:
            doc.Close(False)
    finally:
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def _via_libreoffice(origem: str, pasta: str) -> None:
    soffice = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
    if not os.path.exists(soffice):
        raise FileNotFoundError("LibreOffice não encontrado")
    # Perfil fixo: sem ele cada conversão recria o perfil do zero, o que leva minutos na CPU do Render gratuito
    perfil = "file:///" + os.path.join(tempfile.gettempdir(), "lo_perfil_convenio").replace("\\", "/").lstrip("/")
    subprocess.run(
        [soffice, f"-env:UserInstallation={perfil}", "--headless", "--norestore", "--convert-to", "pdf", "--outdir", pasta, origem],
        check=True, capture_output=True, timeout=int(os.getenv("PDF_TIMEOUT", "600")),
    )


def docx_para_pdf(conteudo: bytes) -> bytes:
    with _trava, tempfile.TemporaryDirectory(prefix="ad_pdf_") as pasta:
        origem = os.path.join(pasta, "minuta.docx")
        destino = os.path.join(pasta, "minuta.pdf")
        with open(origem, "wb") as f:
            f.write(conteudo)
        erros = []
        for nome, conversor in (("Word", lambda: _via_word(origem, destino)), ("LibreOffice", lambda: _via_libreoffice(origem, pasta))):
            try:
                conversor()
                if os.path.exists(destino):
                    with open(destino, "rb") as f:
                        return f.read()
            except Exception as exc:
                logger.warning("Conversão PDF via %s falhou: %s", nome, exc)
                erros.append(f"{nome}: {exc}")
        raise ConversaoPdfIndisponivel(
            "Não foi possível gerar o PDF (é preciso ter o Microsoft Word ou o LibreOffice instalado). " + " | ".join(erros)
        )
