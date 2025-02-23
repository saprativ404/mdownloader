import os
import requests
from bs4 import BeautifulSoup

def download_images(url, download_folder="images"):
    # Create download folder if it doesn't exist
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # Retrieve the webpage content
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to retrieve the webpage.")
        return

    # Parse the webpage with BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")
    img_tags = soup.find_all("img")
    print(f"Found {len(img_tags)} images.")

    for img in img_tags:
        src = img.get("src")
        if not src:
            continue

        # Handle relative URLs by joining them with the base URL
        if not src.startswith("http"):
            src = requests.compat.urljoin(url, src)

        try:
            # Get the image data
            img_response = requests.get(src)
            img_response.raise_for_status()
            img_data = img_response.content

            # Extract a filename from the URL, or assign a default one
            img_filename = os.path.basename(src)
            if not img_filename:
                img_filename = "image.jpg"

            # Save the image data to a file
            file_path = os.path.join(download_folder, img_filename)
            with open(file_path, "wb") as f:
                f.write(img_data)
            print(f"Downloaded: {img_filename}")
        except Exception as e:
            print(f"Error downloading {src}: {e}")

if __name__ == "__main__":
    website_url = input("Enter the website URL: ").strip()
    download_images(website_url)
