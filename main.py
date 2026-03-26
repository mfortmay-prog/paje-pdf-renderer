from fastapi import FastAPI, UploadFile, File, Form
from typing import Optional
from pdf2image import convert_from_bytes, convert_from_path
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import io
import os
import subprocess
import base64
import cv2
import numpy as np
import requests

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
print("=== NEW VERSION DEPLOYED ===")

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
            
        print(f"Temp file exists: {os.path.exists(temp_path)}")
        print(f"Temp file size: {os.path.getsize(temp_path)}")

        # Check where poppler is
        result = subprocess.run(["which", "pdftoppm"], capture_output=True, text=True)
        print(f"pdftoppm path: {result.stdout}")

        # Try running poppler manually
        test = subprocess.run(
            ["pdftoppm", temp_path, "/tmp/test"],
            capture_output=True,
            text=True
            )

        print(f"pdftoppm return code: {test.returncode}")
        print(f"pdftoppm stderr: {test.stderr}")
            
        # Convert using file path (more reliable)
        images = convert_from_path(
            temp_path,
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
            
        print(f"Returning {len(results)} images")
        
        return {
            "report_id": report_id,
            "status": "success",
            "images": results,
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

class ImageRequest(BaseModel):
    image_url: str


@app.post("/detect-photos")
async def detect_photos(req: ImageRequest):
    try:
        print("CV DETECTOR STARTED")
        print("Image URL:", req.image_url)

        # Download image
        response = requests.get(req.image_url)
        image_bytes = np.asarray(bytearray(response.content), dtype=np.uint8)
        img = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

        if img is None:
            print("ERROR: Image failed to load")
            return []

        height, width = img.shape[:2]

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)

            # Filter small regions
            if w < width * 0.1 or h < height * 0.1:
                continue

            # Filter extreme shapes
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.3 or aspect_ratio > 5:
                continue

            results.append({
                "bbox": {
                    "x": x / width,
                    "y": y / height,
                    "w": w / width,
                    "h": h / height
                }
            })

        print("Detected regions:", len(results))

        return results

    except Exception as e:
        print("DETECT ERROR:", str(e))
        return []

client = OpenAI()

class AnalyzeRequest(BaseModel):
    image_url: str
    user_input: str = ""
    previous_result: Optional[str] = None
@app.post("/mentor/analyze-image")
async def analyze_image(req: AnalyzeRequest):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
            {
            "role": "user",
            "content": [
                {
            "type": "text",
            "text": (
            "You are an expert assistant that adapts to the user's context.\n\n"

            "Previous analysis (if any):\n"
            f"{getattr(req, 'previous_result', None) or 'None'}\n\n"

            "User additional input:\n"
            f"{req.user_input}\n\n"

            "REFINEMENT RULES:\n"
            "- Preserve Estimated Cost unless new input justifies change\n"
            "- Preserve Remedy credit unless justified\n"
            "- Do NOT increase cost arbitrarily\n"
            "- Only adjust values if user input impacts scope or severity\n"
            "- If no meaningful new information is provided, return the same values\n\n"

            "If the input is a home inspection screenshot:\n"
            "- Identify the primary defect\n"
            "- Focus ONLY on that defect\n\n"

            "Do NOT guess or assume problems.\n\n"

            "Return your answer in this format:\n\n"

            "Form Output:\n\n"

            "CRITICAL RULES:\n"
            "- Remedy MUST include 'OR provide credit of $X'\n"
            "- Remedy MUST be ONE line\n"
            "- Cost must align with credit\n\n"

            "Deficiency:\n[Component – condition observed]\n\n"
            "Remedy:\n[One line OR credit]\n\n"

            "--- Supporting Details ---\n\n"

            "Explanation:\n...\n\n"
            "Why it matters:\n...\n\n"
            "Severity:\n[Level – short reason]\n\n"
            "Estimated Cost:\n$X–$Y\n\n"
            "Recommended Actions:\n- Action\n- Action\n\n"
            "Negotiation Strategy:\nShort recommendation.\n\n"
        )
    },
    {
            "type": "image_url",
            "image_url": {"url": req.image_url}
                    }
                ]
            }
        ],
            max_tokens=600
    )

            text = response.choices[0].message.content

        return {
        "result": text
    }

except Exception as e:
       return {"error": str(e)}
