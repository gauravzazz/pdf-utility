# PDF Utility Scripts

A collection of professional Python scripts for processing PDF files, optimized for print-friendly output and efficient document merging.

## Features

- **Invert PDF (`invertPdf.py`)**: 
  - Automatically detects "Dark Mode" pages.
  - Inverts the colors of dark-mode pages (black background -> white background, white text -> black text).
  - Optimizes for printing by whitening near-white pixels and boosting contrast.
- **Merge PDF (`mergePdf.py`)**: 
  - Standard back-to-back PDF merging.
  - **Duplex-Safe Mode**: Automatically adds a blank page after any document with an odd number of pages to ensure perfect alignment for double-sided printing.

## Requirements

- Python 3.10+
- PyMuPDF (`fitz`)
- PIL (`Pillow`)
- NumPy

## Installation

```bash
pip install pymupdf pillow numpy
```

## Usage

### Invert
```bash
python invertPdf.py input.pdf output.pdf
```

### Merge
```bash
python mergePdf.py file1.pdf file2.pdf --duplex -o result.pdf
```

## API

Coming soon: A FastAPI wrapper for these utilities!
