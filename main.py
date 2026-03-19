from fastapi import FastAPI, UploadFile, File, Form
from typing import Optional
from pdf2image import convert_from_bytes, convert_from_path
import requests
import io
import os
import base64

app = FastAPI()

@app.post("/render-pdf")
async def render_pdf(
    report_id: str = Form(None),
    file: UploadFile = File(None),
    pdf_url: str = Form(None)
):
    try:
        report_id = report_id or "unknown"

        if file:
            pdf_bytes = await file.read()

        elif pdf_url:
            response = requests.get(pdf_url)
            pdf_bytes = response.content

        else:
            raise Exception("No file or pdf_url provided")

        # Save PDF to temp file
        temp_path = "/tmp/input.pdf"

        with open(temp_path, "wb") as f:
            f.write(pdf_bytes)

        # Convert using file path (more reliable)
        images = convert_from_path(
            temp_path,
            poppler_path="/usr/bin",
            first_page=1,
            last_page=10,
            fmt="png",
            thread_count=1,
            use_pdftocairo=True
        )

        print(f"Converted {len(images)} pages from file {temp_path}")
        
        print(f"Temp file exists: {os.path.exists(temp_path)}")

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
