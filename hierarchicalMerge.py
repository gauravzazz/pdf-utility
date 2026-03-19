import os
import subprocess
from glob import glob

def merge_recursively(root_dir, final_output):
    """
    1. For each subfolder containing PDFs, merge them into a temp category PDF.
    2. Merge all category PDFs into the final output.
    """
    root_dir = os.path.abspath(root_dir)
    category_pdfs = []
    
    # We walk and find folders with PDFs
    for root, dirs, files in os.walk(root_dir):
        pdf_files = [os.path.join(root, f) for f in files if f.lower().endswith('.pdf') and not f.endswith('_MergedCategory.pdf')]
        
        if pdf_files:
            # Sort files to maintain some order (e.g. alphabetical)
            pdf_files.sort()
            
            category_name = os.path.basename(root) or "Root"
            temp_output = os.path.join(root, f"{category_name}_MergedCategory.pdf")
            
            print(f"Merging category: {category_name} ({len(pdf_files)} files)")
            
            # Use the existing mergePdf.py script
            cmd = [
                "/opt/miniconda3/bin/python3",
                "/Users/gauravupadhyay/Desktop/Scripts/mergePdf.py",
                *pdf_files,
                "--duplex",
                "-o", temp_output
            ]
            
            try:
                subprocess.run(cmd, check=True)
                category_pdfs.append(temp_output)
            except subprocess.CalledProcessError as e:
                print(f"Error merging category {category_name}: {e}")

    if not category_pdfs:
        print("No PDFs found to merge.")
        return

    # Final merge of all category PDFs
    print(f"Performing final merge of {len(category_pdfs)} categories into {final_output}")
    
    # Sort category PDFs if needed (maybe by folder structure order)
    category_pdfs.sort()
    
    cmd = [
        "/opt/miniconda3/bin/python3",
        "/Users/gauravupadhyay/Desktop/Scripts/mergePdf.py",
        *category_pdfs,
        "--duplex",
        "-o", final_output
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully created final merged PDF: {final_output}")
    except subprocess.CalledProcessError as e:
        print(f"Error in final merge: {e}")

if __name__ == "__main__":
    target = "/Users/gauravupadhyay/Downloads/Order_9345037578"
    output = "/Users/gauravupadhyay/Downloads/Order_9345037578_Final.pdf"
    merge_recursively(target, output)
