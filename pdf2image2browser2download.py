import openai
import os
import base64
import argparse
from PIL import Image
import re
import io
import webbrowser
import urllib.parse
import shutil # <-- Required for moving files

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
    Creates 'for_deletion' and 'manual_inspection' directories if they don't exist.
    """
    # Define target directories
    deletion_dir = "for_deletion"
    inspection_dir = "manual_inspection"

    # Create directories if they don't exist
    os.makedirs(deletion_dir, exist_ok=True)
    os.makedirs(inspection_dir, exist_ok=True)

    # Loop to get valid user input
    while True:
        prompt = "\n>>> Were you successful in downloading the PDF? (yes/no): "
        answer = input(prompt).lower().strip()
        
        if answer == 'yes':
            try:
                shutil.move(image_path, deletion_dir)
                print(f"\n✅ Success. Moved '{image_path}' to '{deletion_dir}/'. Exiting.")
            except Exception as e:
                print(f"\n❌ Error moving file: {e}")
            break
        elif answer == 'no':
            try:
                shutil.move(image_path, inspection_dir)
                print(f"\n⚠️ Understood. Moved '{image_path}' to '{inspection_dir}/' for review. Exiting.")
            except Exception as e:
                print(f"\n❌ Error moving file: {e}")
            break
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze a scientific image using the Vision API.')
    parser.add_argument('image_path', type=str, help='Path to the image file to analyze')
    args = parser.parse_args()
    
    print(f"Analyzing image: {args.image_path}...")
    
    api_response = describe_image(args.image_path)
    
    title, doi = extract_info_from_text(api_response)
    
    print("--- Analysis Results ---")
    print(f"Title: {title}")
    print(f"DOI: {doi}")
    print("----------------------")
    
    # --- Browser and Fallback Logic ---
    if doi != "DOI not found":
        try:
            print(f"\nFound DOI. Opening link in your browser...")
            webbrowser.open_new_tab(doi)
            # Call the new handler function to move the file
            handle_post_analysis(args.image_path)
        except Exception as e:
            print(f"An error occurred while trying to open the browser: {e}")

    elif title != "Title not found":
        try:
            print(f"\nNo DOI found. Searching for the title on Google...")
            search_query = urllib.parse.quote_plus(title)
            google_url = f"https://www.google.com/search?q={search_query}"
            webbrowser.open_new_tab(google_url)
            # Call the new handler function to move the file
            handle_post_analysis(args.image_path)
        except Exception as e:
            print(f"An error occurred while trying to open the browser: {e}")

    else:
        print("\nCould not find a valid title or DOI to search for. Exiting.")
