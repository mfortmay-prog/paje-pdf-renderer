from fastapi import FastAPI, UploadFile, File
from pdf2image import convert_from_bytes
import io
import base64

app = FastAPI()

@app.post("/render-pdf")
async def render_pdf(file: UploadFile = File(...)):
    pdf_bytes = await file.read()

    images = convert_from_bytes(pdf_bytes)

    results = []

    for i, img in enumerate(images):
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode()

        results.append({
            "page": i + 1,
            "image_base64": encoded
        })

    return {
        "pages": len(results),
        "images": results
    }
