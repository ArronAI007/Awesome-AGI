from pdf2image import convert_from_path
import os

def convert_pdf_to_images(pdf_path):
    """
    Converts each page of a PDF into JPEG images and saves them in a directory named after the PDF file.

    Args:
    - pdf_path (str): Path to the PDF file.

    Returns:
    - list: List of image file paths saved.
    """
    # Create a directory based on the PDF filename
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = f"{pdf_name}_images"
    os.makedirs(output_dir, exist_ok=True)

    # Convert each page of the PDF into images
    images = convert_from_path(pdf_path)
    saved_image_paths = []
    for i, img in enumerate(images):
        image_path = os.path.join(output_dir, f'page{i}.jpg')
        img.save(image_path, 'JPEG')
        saved_image_paths.append(image_path)
    
    return saved_image_paths

# Example usage:
pdf_path = "outlier-or-laggard-divergence-and-convergence-in-the-uks-recent-inflation-performance.pdf"
saved_paths = convert_pdf_to_images(pdf_path)
print("Images saved to:", saved_paths)
