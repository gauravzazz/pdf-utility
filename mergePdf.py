import argparse
import os
import fitz  # PyMuPDF

def merge_pdfs(input_files, output_file, duplex_safe=False):
    """
    Merge multiple PDF files into one.
    
    duplex_safe: If True, adds a blank page if a PDF has an odd number of pages.
    """
    out_pdf = fitz.open()
    
    for file_path in input_files:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}. Skipping.")
            continue
            
        print(f"Merging: {file_path}")
        src_pdf = fitz.open(file_path)
        page_count = len(src_pdf)
        
        # Insert all pages from the source PDF
        out_pdf.insert_pdf(src_pdf)
        
        # If duplex_safe is enabled and page count is odd, add a blank page
        if duplex_safe and (page_count % 2 != 0):
            print(f"  Adding blank page to {file_path} (odd page count: {page_count})")
            # Create a blank page with the same dimensions as the last page
            last_page = src_pdf[-1]
            rect = last_page.rect
            out_pdf.new_page(width=rect.width, height=rect.height)
            
        src_pdf.close()
        
    out_pdf.save(output_file, garbage=4, deflate=True)
    out_pdf.close()
    print(f"Successfully merged {len(input_files)} files into: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Merge multiple PDF files.")
    parser.add_argument("inputs", nargs="+", help="Input PDF files to merge")
    parser.add_argument("-o", "--output", default="merged.pdf", help="Output PDF file path (default: merged.pdf)")
    parser.add_argument("--duplex", action="store_true", help="Enable duplex-safe mode (adds blank pages for odd-paged PDFs)")
    
    args = parser.parse_args()
    
    merge_pdfs(args.inputs, args.output, duplex_safe=args.duplex)

if __name__ == "__main__":
    main()
