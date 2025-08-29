import openai
import os
import base64
import argparse
from PIL import Image
import re
import io
import webbrowser
import urllib.parse
import shutil
import sys # <-- Required for the exit command

# Initialize OpenAI client
api_key = os.environ.get('CBORG_API_KEY')
if not api_key:
    raise ValueError("API key not found. Please set the CBORG_API_KEY environment variable.")

client = openai.OpenAI(
    api_key=api_key,
    base_url="https://api.cborg.lbl.gov"
)

def encode_image_in_memory(file_path):
    """
    Opens an image, converts it to PNG in memory, and returns its base64 string.
    """
    with Image.open(file_path) as img:
        with io.BytesIO() as buffer:
            img = img.convert("RGBA")
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

def describe_image(image_path):
    """
    Sends the image to the model with a simple, general prompt.
    """
    encoded_image = encode_image_in_memory(image_path)
    
    response = client.chat.completions.create(
        model="lbl/cborg-vision",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the picture"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}}
                ]
            }
        ],
        temperature=0.0,
        stream=False
    )
    
    return response

def extract_info_from_text(response):
    """
    Uses multiple regex patterns to robustly find the title and DOI.
    """
    content = response.choices[0].message.content
    title = "Title not found"
    doi = "DOI not found"
    
    # Combine patterns to find title in prose OR in a markdown header
    title_pattern = r'(?:titled|title is)\s*["\'](.*?)(?=["\'])|\*\*Title:\*\*\s*(.*)'
    title_match = re.search(title_pattern, content, re.IGNORECASE)
    if title_match:
        title = title_match.group(1) or title_match.group(2)
        title = title.strip()

    # Look for the reliable DOI identifier first
    doi_pattern = r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)'
    doi_match = re.search(doi_pattern, content, re.IGNORECASE)
    if doi_match:
        doi_identifier = doi_match.group(1)
        cleaned_doi = doi_identifier.rstrip('.,')
        doi = f"https://doi.org/{cleaned_doi}"
        
    return title, doi

def handle_post_analysis(image_path):
    """
    Asks the user for the download outcome and moves the file accordingly.
    Includes a 'quit' option to exit the script immediately.
    """
    deletion_dir = "for_deletion"
    inspection_dir = "manual_inspection"
    os.makedirs(deletion_dir, exist_ok=True)
    os.makedirs(inspection_dir, exist_ok=True)

    while True:
        # Updated prompt to include the 'quit' option
        prompt = "\n>>> Were you successful in downloading the PDF? (yes/no/quit): "
        answer = input(prompt).lower().strip()
        
        if answer == 'yes':
            try:
                shutil.move(image_path, deletion_dir)
                print(f"\n✅ Success. Moved '{os.path.basename(image_path)}' to '{deletion_dir}/'.")
            except Exception as e:
                print(f"\n❌ Error moving file: {e}")
            break # Continue to the next image
        elif answer == 'no':
            try:
                shutil.move(image_path, inspection_dir)
                print(f"\n⚠️ Understood. Moved '{os.path.basename(image_path)}' to '{inspection_dir}/' for review.")
            except Exception as e:
                print(f"\n❌ Error moving file: {e}")
            break # Continue to the next image
        elif answer == 'quit':
            print("\n🛑 Quit command received. Exiting script.")
            sys.exit() # Terminate the program immediately
        else:
            print("Invalid input. Please enter 'yes', 'no', or 'quit'.")

def process_image(image_path):
    """
    Runs the full analysis and user interaction workflow for a single image.
    """
    try:
        api_response = describe_image(image_path)
        title, doi = extract_info_from_text(api_response)
        
        print("\n--- Analysis Results ---")
        print(f"Title: {title}")
        print(f"DOI: {doi}")
        print("----------------------")
        
        browser_opened = False
        if doi != "DOI not found":
            print(f"\nFound DOI. Opening link in your browser...")
            webbrowser.open_new_tab(doi)
            browser_opened = True
        elif title != "Title not found":
            print(f"\nNo DOI found. Searching for the title on Google...")
            search_query = urllib.parse.quote_plus(title)
            google_url = f"https://www.google.com/search?q={search_query}"
            webbrowser.open_new_tab(google_url)
            browser_opened = True

        if browser_opened:
            handle_post_analysis(image_path)
        else:
            print("\nCould not find a valid title or DOI. Moving to manual inspection.")
            inspection_dir = "manual_inspection"
            os.makedirs(inspection_dir, exist_ok=True)
            shutil.move(image_path, inspection_dir)
            print(f"Moved '{os.path.basename(image_path)}' to '{inspection_dir}/'.")

    except Exception as e:
        print(f"\n🚨 An unexpected error occurred while processing {os.path.basename(image_path)}: {e}")
        print("Moving file to 'manual_inspection' for safety.")
        inspection_dir = "manual_inspection"
        os.makedirs(inspection_dir, exist_ok=True)
        try:
            shutil.move(image_path, inspection_dir)
        except Exception as move_error:
            print(f"Could not move the file. Please check it manually. Error: {move_error}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze all scientific images in a directory.')
    parser.add_argument('directory_path', type=str, help='Path to the directory containing image files')
    args = parser.parse_args()

    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
    try:
        all_files = os.listdir(args.directory_path)
        image_files = [os.path.join(args.directory_path, f) for f in all_files if f.lower().endswith(image_extensions)]
        
        if not image_files:
            print(f"No image files found in '{args.directory_path}'.")
            exit()

    except FileNotFoundError:
        print(f"Error: Directory not found at '{args.directory_path}'")
        exit()

    total_images = len(image_files)
    print(f"Found {total_images} images to process.")
    
    for i, image_path in enumerate(image_files):
        print(f"\n================== PROCESSING IMAGE {i+1} of {total_images} ({os.path.basename(image_path)}) ==================")
        process_image(image_path)
    
    print("\n================== ALL IMAGES PROCESSED ==================")
