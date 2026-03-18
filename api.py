import os
import shutil
import uuid
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import invertPdf
import mergePdf

app = FastAPI(title="PDF Utility API")

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

@app.post("/invert")
async def invert_endpoint(
    file: UploadFile = File(...),
    dpi: int = Form(220),
    mode: str = Form("gray"),
    aggressive: bool = Form(False)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    session_id = str(uuid.uuid4())
    input_path = os.path.join(TEMP_DIR, f"{session_id}_input.pdf")
    output_path = os.path.join(TEMP_DIR, f"{session_id}_inverted.pdf")
    
    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        invertPdf.convert_pdf(
            input_pdf=input_path,
            output_pdf=output_path,
            dpi=dpi,
            output_mode=mode,
            aggressive=aggressive
        )
        
        return FileResponse(output_path, filename=f"inverted_{file.filename}", media_type="application/pdf")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # Finally block removed for now to ensure file persists during response; 
    # a production app would use BackgroundTasks to clean up.

@app.post("/merge")
async def merge_endpoint(
    files: List[UploadFile] = File(...),
    duplex: bool = Form(False)
):
    session_id = str(uuid.uuid4())
    input_paths = []
    output_path = os.path.join(TEMP_DIR, f"{session_id}_merged.pdf")
    
    try:
        for i, file in enumerate(files):
            input_path = os.path.join(TEMP_DIR, f"{session_id}_input_{i}.pdf")
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            input_paths.append(input_path)
        
        mergePdf.merge_pdfs(input_paths, output_path, duplex_safe=duplex)
        
        return FileResponse(output_path, filename="merged.pdf", media_type="application/pdf")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
