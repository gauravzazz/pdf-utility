import os
import argparse
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

def convert_docx_to_pdf_pure_python(docx_path, pdf_path):
    """
    Pure Python conversion for basic docx to pdf (no Office needed).
    """
    doc = Document(docx_path)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Use a standard font that supports most characters
    pdf.set_font("helvetica", size=11)
    
    for para in doc.paragraphs:
        if para.text.strip():
            # Basic text wrapping and addition
            # FPDF.multi_cell(w, h, txt, ...)
            pdf.multi_cell(0, 8, txt=para.text.encode('latin-1', 'replace').decode('latin-1'))
            pdf.ln(2)
            
    pdf.output(pdf_path)

def convert_recursive(input_path, output_path=None):
    """
    Convert Word documents to PDF recursively.
    """
    # Check if Microsoft Word is installed for docx2pdf
    has_word = os.path.exists("/Applications/Microsoft Word.app")
    
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
    
    for file_path in tqdm(word_files, desc="Converting"):
        dest_path = file_path.rsplit('.', 1)[0] + '.pdf'
        
        try:
            if has_word:
                from docx2pdf import convert
                convert(file_path, dest_path)
            else:
                # Use pure python fallback
                convert_docx_to_pdf_pure_python(file_path, dest_path)
        except Exception as e:
            print(f"\nError converting {file_path}: {e}")
                
    print("\nRecursive conversion complete.")

def main():
    parser = argparse.ArgumentParser(description="Recursively convert Word documents to PDF.")
    parser.add_argument("input", help="Input file or folder path")
    parser.add_argument("-o", "--output", help="Output file path (for single file) or folder")
    
    args = parser.parse_args()
    
    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output) if args.output else None
    
    if not os.path.exists(input_path):
        print(f"Error: Path does not exist: {input_path}")
        return

    convert_recursive(input_path, output_path)

if __name__ == "__main__":
    main()
