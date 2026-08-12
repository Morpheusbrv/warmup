from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF
import requests
import base64
import re
import os
import glob
import subprocess
import tempfile

app = FastAPI(title="WarmUp ProofScope - Flexo RIP Engine")

# Configuração de CORS para permitir requisições do Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PDFRequest(BaseModel):
    pdf_url: str
    dpi: int = 300

@app.get("/")
async def root():
    return {"status": "online", "message": "WarmUp ProofScope RIP Engine Operacional"}

@app.post("/analyze-pdf")
async def analyze_pdf(data: PDFRequest):
    try:
        url = data.pdf_url
        target_dpi = data.dpi

        # Trava a renderização em 300 DPI para garantir estabilidade no plano Free do Render (512MB RAM)
        render_dpi = 300 if target_dpi > 300 else target_dpi

        # Trata links de visualização do Google Drive convertendo para download direto
        drive_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
        if drive_match:
            file_id = drive_match.group(1)
            url = f"https://drive.google.com/uc?export=download&id={file_id}"

        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Não foi possível baixar o arquivo PDF.")
            
        pdf_bytes = response.content

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "input.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                raise HTTPException(status_code=400, detail="O arquivo PDF está vazio ou corrompido.")

            page = doc[0]
            rect_w, rect_h = page.rect.width, page.rect.height

            # Executa Ghostscript com o dispositivo tiffsep para fatiar as cores de processo e especiais
            gs_cmd = [
                "gs",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-sDEVICE=tiffsep",
                f"-r{render_dpi}",
                "-dTextAlphaBits=4",        # Anti-aliasing para textos finos
                "-dGraphicsAlphaBits=4",   # Anti-aliasing para traços e vetores
                "-dBufferSpace=20000000",  # Otimização de buffer para consumo reduzido de RAM
                f"-sOutputFile={os.path.join(tmpdir, 'out%d.tif')}",
                pdf_path
            ]
            
            subprocess.run(gs_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            channels_data = {}
            spot_colors = []
            composite_base64 = ""

            tif_files = glob.glob(os.path.join(tmpdir, "out1*.tif")) + glob.glob(os.path.join(tmpdir, "out1(*).tif"))

            for file_path in tif_files:
                filename = os.path.basename(file_path)
                
                tif_doc = fitz.open(file_path)
                tif_pix = tif_doc[0].get_pixmap()
                png_b64 = f"data:image/png;base64,{base64.b64encode(tif_pix.tobytes('png')).decode('utf-8')}"

                if filename == "out1.tif":
                    composite_base64 = png_b64
                else:
                    match_channel = re.search(r'\((.*?)\)', filename)
                    if match_channel:
                        channel_name = match_channel.group(1)
                        channels_data[channel_name] = png_b64
                        
                        if channel_name not in ["Cyan", "Magenta", "Yellow", "Black"]:
                            spot_colors.append(channel_name)

            return {
                "page_count": len(doc),
                "width": rect_w,
                "height": rect_h,
                "rendered_dpi": render_dpi,
                "composite_image": composite_base64,
                "spot_colors": spot_colors,
                "channels": channels_data
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
