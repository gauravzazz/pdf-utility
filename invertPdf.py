import os
import argparse
import numpy as np
import fitz  # PyMuPDF
from PIL import Image


def brightness_map(arr: np.ndarray) -> np.ndarray:
    """
    Compute perceived brightness from RGB image.
    Returns float array in range 0..255.
    """
    r = arr[:, :, 0].astype(np.float32)
    g = arr[:, :, 1].astype(np.float32)
    b = arr[:, :, 2].astype(np.float32)
    return 0.299 * r + 0.587 * g + 0.114 * b


def process_image_for_print(
    img: Image.Image,
    dark_threshold: int = 115,
    near_black_threshold: int = 45,
    output_mode: str = "gray",
    aggressive: bool = False,
) -> Image.Image:
    """
    Convert dark backgrounds to light backgrounds for printing.
    """
    img = img.convert("RGB")
    arr = np.array(img)
    bright = brightness_map(arr)

    # Calculate average brightness to detect if the page is "Dark Mode"
    avg_brightness = np.mean(bright)
    is_dark_mode = avg_brightness < 128

    if output_mode == "color":
        out = arr.copy()
        if is_dark_mode:
            # Full inversion for dark mode colors
            out = 255 - out
        
        # Whitening: push near-white pixels to pure white
        bright_out = brightness_map(out)
        white_mask = bright_out > 240
        out[white_mask] = 255
        
        return Image.fromarray(out.astype(np.uint8))

    # Grayscale path (default)
    gray = bright.copy()

    if is_dark_mode:
        # Full inversion for dark mode pages
        gray = 255 - gray
        
        # Aggressive contrast: push very light grays to pure white (ink save)
        gray[gray > 235] = 255
        
        # Push very dark grays to pure black (text contrast)
        gray[gray < 30] = 0
        
        if aggressive:
            # Further lighten mid-tones
            mid_light_mask = (gray > 180) & (gray < 235)
            gray[mid_light_mask] = np.clip(gray[mid_light_mask] + 30, 0, 255)
    else:
        # Light mode page: minimal changes, just ink saving
        # Push almost-white backgrounds to pure white
        gray[gray > 250] = 255
        
        if aggressive:
            # Subtle lightening of entire page
            gray = np.clip(gray.astype(np.float32) * 1.05, 0, 255).astype(np.uint8)

    gray = np.clip(gray, 0, 255).astype(np.uint8)

    if output_mode == "bw":
        threshold = 170 if aggressive else 140
        bw = np.where(gray > threshold, 255, 0).astype(np.uint8)
        return Image.fromarray(bw, mode="L")

    return Image.fromarray(gray, mode="L")


def pil_to_pdf_bytes(img: Image.Image) -> bytes:
    """
    Convert PIL image to single-page PDF bytes.
    """
    import io

    buf = io.BytesIO()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(buf, format="PDF", resolution=300.0)
    return buf.getvalue()


def convert_pdf(
    input_pdf: str,
    output_pdf: str,
    dpi: int = 220,
    dark_threshold: int = 115,
    near_black_threshold: int = 45,
    output_mode: str = "gray",
    aggressive: bool = False,
):
    src = fitz.open(input_pdf)
    out = fitz.open()

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    total_pages = len(src)
    print(f"Processing {total_pages} pages...")

    for i, page in enumerate(src):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "RGB" if pix.n < 4 else "RGBA"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        if mode == "RGBA":
            img = img.convert("RGB")

        processed = process_image_for_print(
            img,
            dark_threshold=dark_threshold,
            near_black_threshold=near_black_threshold,
            output_mode=output_mode,
            aggressive=aggressive,
        )

        # Convert processed PIL page back into PDF page
        pdf_bytes = pil_to_pdf_bytes(processed)
        temp_pdf = fitz.open("pdf", pdf_bytes)
        out.insert_pdf(temp_pdf)
        temp_pdf.close()

        print(f"Done page {i + 1}/{total_pages}")

    out.save(output_pdf, garbage=4, deflate=True)
    out.close()
    src.close()
    print(f"Saved: {output_pdf}")


def convert_image(
    input_image: str,
    output_image: str,
    dark_threshold: int = 115,
    near_black_threshold: int = 45,
    output_mode: str = "gray",
    aggressive: bool = False,
):
    img = Image.open(input_image)
    processed = process_image_for_print(
        img,
        dark_threshold=dark_threshold,
        near_black_threshold=near_black_threshold,
        output_mode=output_mode,
        aggressive=aggressive,
    )
    processed.save(output_image)
    print(f"Saved: {output_image}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert dark-theme PDF/image to print-friendly light output."
    )
    parser.add_argument("input", help="Input PDF or image path")
    parser.add_argument("output", help="Output PDF or image path")
    parser.add_argument("--dpi", type=int, default=220, help="Raster DPI for PDFs (default: 220)")
    parser.add_argument(
        "--dark-threshold",
        type=int,
        default=115,
        help="Brightness below this is treated as dark (default: 115)",
    )
    parser.add_argument(
        "--near-black-threshold",
        type=int,
        default=45,
        help="Very dark pixels below this are strongly whitened (default: 45)",
    )
    parser.add_argument(
        "--mode",
        choices=["gray", "bw", "color"],
        default="gray",
        help="Output mode: gray, bw, or color (default: gray)",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="More aggressive whitening and ink reduction",
    )

    args = parser.parse_args()

    input_path = args.input
    output_path = args.output

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ext = os.path.splitext(input_path)[1].lower()

    if ext == ".pdf":
        convert_pdf(
            input_pdf=input_path,
            output_pdf=output_path,
            dpi=args.dpi,
            dark_threshold=args.dark_threshold,
            near_black_threshold=args.near_black_threshold,
            output_mode=args.mode,
            aggressive=args.aggressive,
        )
    else:
        convert_image(
            input_image=input_path,
            output_image=output_path,
            dark_threshold=args.dark_threshold,
            near_black_threshold=args.near_black_threshold,
            output_mode=args.mode,
            aggressive=args.aggressive,
        )


if __name__ == "__main__":
    main()