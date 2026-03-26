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
    f"{req.previous_result or 'None'}\n\n"

    "User additional input:\n"
    f"{req.user_input}\n\n"

    "REFINEMENT RULES:\n"
    "- Preserve Estimated Cost unless new input justifies change\n"
    "- Preserve Remedy credit unless justified\n"
    "- Do NOT increase cost arbitrarily\n"
    "- Only adjust values if user input impacts scope or severity\n\n"

    "Continue with updated analysis.\n\n"
)

    "First, determine what the user is asking:\n"
    "- Home inspection / real estate\n"
    "- Food / drink\n"
    "- Technical troubleshooting\n"
    "- Writing assistance\n"
    "- Other\n\n"

    "If the input is a home inspection screenshot:\n"
    "- Identify the primary defect\n"
    "- Explain the issue clearly\n"
    "- Explain why it matters in real-world terms\n\n"

    "If multiple defects are visible, identify the PRIMARY defect that appears most central or most detailed in the screenshot.\n"
    "Focus ONLY on that one defect.\n"
    "Ignore partial or cut-off defects at the top or bottom.\n"
    "If two defects are equally clear, ask: \"Which defect would you like to focus on?\"\n\n"

    "If no clear defect is visible, respond exactly with:\n"
    "'No clear inspection defect identified.'\n\n"

    "User additional input:\n"
    f"{req.user_input}\n\n"

    "Do NOT guess or assume problems.\n\n"

    "Return your answer in this format:\n\n"

    "Form Output:\n"
    "Provide output formatted for an inspection response form using this exact structure:\n\n"
    "CRITICAL FORMATTING RULES:\n"
    "- Each section must contain ONLY its own content\n"
    "- Do NOT include other section headers inside any section\n"
    "- Remedy MUST be ONE line only\n"
    "- Remedy MUST include: 'OR provide credit of $X'\n"
    "- Estimated Cost MUST be a realistic range and consistent with Remedy credit\n"
    "- Do NOT include '--- Supporting Details ---' inside any section content\n\n"

    "Deficiency:\n"
    "Provide a concise, inspection-style defect description.\n"
    "Format as: [Component] – [Condition observed + location].\n"
    "Use professional inspection terms such as 'observed', 'improper', 'inadequate', or 'damaged'.\n"
    "When generating Estimated Cost, ensure it aligns with the Remedy credit amount.\n"
    "The credit should fall within the estimated range.\n\n"
   
    "REFINEMENT RULES:\n"
    "If this is a refinement request:\n"
    "- Preserve previous Estimated Cost unless new information justifies a change\n"
    "- Preserve Remedy credit amount unless new information justifies a change\n"
    "- Do NOT increase cost arbitrarily\n"
    "- Only adjust values if the user's new input clearly impacts scope or severity\n\n"
    "Do NOT include explanations or full sentences.\n\n"

    "Remedy:\n"
    "Provide ONE short, direct line using form-style language.\n"
    "Start with a strong action verb.\n"
    "Do NOT use phrases like 'have a contractor' or 'it is recommended'.\n"
    "Keep it concise and directive.\n"
    "When appropriate, include a credit option using this format: 'OR provide credit of $X'.\n\n"

    "Remedy must:\n"
    "- Be ONE line only\n"
    "- Start with a strong action verb\n"
    "- Include 'OR provide credit of $X'\n"
    "- NOT include explanations or extra sections\n\n"

    "Keep both lines concise, no extra explanation, no full sentences unless necessary.\n"
    "Use decisive, professional wording. Avoid vague verbs like 'adjust'.\n"
    "Match real inspection response form style.\n\n"

    "--- Supporting Details ---\n\n"

    "Explanation:\n"
    "...\n\n"

    "Why it matters:\n"
    "...\n\n"

    "Follow-up questions:\n"
    "1. ...\n"
    "2. ...\n\n"

    "If the \"User additional input\" section is NOT empty:\n"
    "- Do NOT ask any more follow-up questions.\n"
    "- You MUST include ALL of the following sections:\n\n"

    "Severity:\n"
    "Format as: [Level] – [short justification].\n"
    "Use ONE line only.\n"
    "Do NOT use periods between sentences.\n\n"

    "Guidelines:\n"
    "- Low: cosmetic or minor issue with little immediate risk\n"
    "- Moderate: defect present that could lead to damage if not addressed\n"
    "- High: active damage, safety concern, or urgent repair needed\n\n"
                        
    "Estimated Cost:\n"
    "Provide a clean cost range using this format: $X–$Y.\n"
    "Do NOT use 'to', dashes (-), or extra words like 'typical' or 'estimated'.\n"
    "Keep it concise and easy to scan.\n\n"

    "When providing a credit amount, convert the estimated cost range into a single reasonable value (typically midpoint or slightly higher for negotiation).\n\n"
                        
    "Recommended Actions:\n"
    "Provide 2–3 short bullet points.\n"
    "Each bullet must start with a strong action verb.\n"
    "Keep each bullet concise (no extra wording or explanations).\n"
    "Do NOT include phrases like 'hire a contractor'.\n\n"

    "Negotiation Strategy:\n"
    "Provide a clear and concise recommendation.\n"
    "Use direct language such as 'Request repair prior to closing OR a credit'.\n"
    "Keep it short and focused on outcome and leverage.\n\n"

    "If any of these sections are missing, the response is incomplete.\n\n"

    "Keep everything practical, concise, and focused on helping the user make a decision."
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
