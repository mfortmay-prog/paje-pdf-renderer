from fastapi import FastAPI, UploadFile, File, Form
from pdf2image import convert_from_bytes
import io
import base64

app = FastAPI()

@app.post("/render-pdf")
async def render_pdf(
    report_id: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        pdf_bytes = await file.read()

        images = convert_from_bytes(pdf_bytes)

        results = []

    for i, img in enumerate(images):
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode()

        results.append({
            "page_number": i + 1,
            "image_base64": encoded
        })

    return {
        "report_id": report_id,
    "status": "success",
    "page_images": results,
    "meta": {
        "total_pages": len(results)
    }
}
    except Exception as e:
        return {
            "report_id": report_id,
            "status": "error",
            "error": {
                "code": "PDF_RENDER_FAILED",
                "message": "Failed to process PDF",
                "details": str(e)
            }
        }
