import os
import argparse
import subprocess
from docx import Document
from fpdf import FPDF
from tqdm import tqdm

def find_word_files(input_folder):
    """
    Recursively find all Word documents (.doc, .docx) in a folder.
    """
    word_files = []
    for root, dirs, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith((".docx", ".doc")) and not file.startswith("~$"):
                word_files.append(os.path.join(root, file))
    return word_files

def convert_docx_to_pdf_soffice(docx_path, out_dir):
    """
    Use LibreOffice soffice for high-quality conversion.
    """
    # Check common paths for soffice
    soffice_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not os.path.exists(soffice_path):
        soffice_path = "soffice" # Hope it's in PATH
    
    cmd = [
        soffice_path,
        "--headless",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        docx_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def convert_docx_to_pdf_pure_python(docx_path, pdf_path):
    """
    Pure Python conversion for docx to pdf with basic styling (bold, italic, headers).
    Fallback if no Office is installed.
    """
    doc = Document(docx_path)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Base font
    pdf.set_font("helvetica", size=11)
    
    for para in doc.paragraphs:
        if para.text.strip():
            # Check for heading levels (more robust check)
            if para.style and hasattr(para.style, 'name') and para.style.name.startswith('Heading'):
                pdf.set_font("helvetica", "B", 14)
                pdf.multi_cell(0, 10, text=para.text.encode('latin-1', 'replace').decode('latin-1'))
                pdf.ln(2)
                pdf.set_font("helvetica", size=11)
            else:
                # Handle runs for bold/italic within paragraph
                for run in para.runs:
                    style = ""
                    if run.bold: style += "B"
                    if run.italic: style += "I"
                    
                    pdf.set_font("helvetica", style, size=11)
                    clean_text = run.text.encode('latin-1', 'replace').decode('latin-1')
                    pdf.write(5, clean_text)
                pdf.ln(8) # Paragraph spacing
            
    pdf.output(pdf_path)

def convert_recursive(input_path):
    """
    Convert Word documents to PDF recursively.
    """
    # Check for engines
    has_word = os.path.exists("/Applications/Microsoft Word.app")
    has_libre = os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    
    if os.path.isfile(input_path):
        word_files = [input_path]
    elif os.path.isdir(input_path):
        word_files = find_word_files(input_path)
    else:
        print(f"Error: Path does not exist: {input_path}")
        return

    if not word_files:
        print("No Word documents found.")
        return

    print(f"Found {len(word_files)} Word documents.")
    print(f"Using Conversion Engine: {'MS Word' if has_word else 'LibreOffice' if has_libre else 'Pure-Python (Basic)'}")
    
    for file_path in tqdm(word_files, desc="Converting"):
        try:
            if has_word:
                from docx2pdf import convert
                convert(file_path)
            elif has_libre:
                out_dir = os.path.dirname(file_path)
                convert_docx_to_pdf_soffice(file_path, out_dir)
            else:
                # Use pure python fallback
                dest_path = file_path.rsplit('.', 1)[0] + '.pdf'
                convert_docx_to_pdf_pure_python(file_path, dest_path)
        except Exception as e:
            print(f"\nError converting {file_path}: {e}")
                
    print("\nRecursive conversion complete.")

def main():
    parser = argparse.ArgumentParser(description="Recursively convert Word documents to PDF.")
    parser.add_argument("input", help="Input file or folder path")
    
    args = parser.parse_args()
    input_path = os.path.abspath(args.input)
    
    if not os.path.exists(input_path):
        print(f"Error: Path does not exist: {input_path}")
        return

    convert_recursive(input_path)

if __name__ == "__main__":
    main()
