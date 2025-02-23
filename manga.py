import os
import re
import time
import logging
import requests
import urllib.parse
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# For Selenium fallback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
BASE_DIR = os.getcwd()
SESSION = requests.Session()

# Updated headers for chapmanganato.to
CUSTOM_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/112.0.0.0 Safari/537.36'),
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://chapmanganato.to/',
    'Connection': 'keep-alive'
}

def fetch_page_links_selenium(url: str) -> list:
    """
    Fetch image URLs using Selenium (headless Chrome) to bypass 403 blocks.
    """
    try:
        options = Options()
        options.headless = True
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)  # Ensure ChromeDriver is installed and in PATH
        driver.get(url)
        time.sleep(3)  # Allow time for page to load
        page_source = driver.page_source
        driver.quit()
        soup = BeautifulSoup(page_source, 'html.parser')
        container = soup.find("div", class_="container-chapter-reader")
        if not container:
            logging.error("Container with class 'container-chapter-reader' not found (Selenium).")
            return []
        imgs = container.find_all("img")
        page_urls = [img.get('src') for img in imgs if img.get('src')]
        return page_urls
    except Exception as e:
        logging.error(f"Selenium failed in fetch_page_links: {e}")
        return []

def fetch_page_links(url: str) -> list:
    """
    Try to fetch image URLs using requests first; if that fails, fallback to Selenium.
    """
    retry_attempts = 5
    for attempt in range(retry_attempts):
        try:
            response = SESSION.get(url, headers=CUSTOM_HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            container = soup.find("div", class_="container-chapter-reader")
            if container:
                imgs = container.find_all("img")
                return [img.get('src') for img in imgs if img.get('src')]
            else:
                logging.info("Container not found with requests; using Selenium fallback.")
                return fetch_page_links_selenium(url)
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching page links with requests (attempt {attempt+1}/{retry_attempts}): {e}")
            if attempt < retry_attempts - 1:
                time.sleep(2 ** attempt)
            else:
                logging.info("Using Selenium fallback after repeated failures.")
                return fetch_page_links_selenium(url)
    return []

def fetch_chapter_links_selenium(series_url: str) -> dict:
    """
    Fetch chapter links using Selenium (headless Chrome) as a fallback.
    """
    try:
        options = Options()
        options.headless = True
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)
        driver.get(series_url)
        time.sleep(3)
        page_source = driver.page_source
        driver.quit()
        soup = BeautifulSoup(page_source, 'html.parser')
        chapters = soup.find_all("a", class_="chapter-name text-nowrap")
        chapter_dict = {ch.text.strip(): ch.get('href') for ch in chapters if ch.get('href')}
        return chapter_dict
    except Exception as e:
        logging.error(f"Selenium failed in fetch_chapter_links: {e}")
        return {}

def fetch_chapter_links(series_url: str) -> dict:
    """
    Try to fetch chapter links using requests; if repeated attempts fail, fallback to Selenium.
    """
    retry_attempts = 5
    for attempt in range(retry_attempts):
        try:
            response = SESSION.get(series_url, headers=CUSTOM_HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            chapters = soup.find_all("a", class_="chapter-name text-nowrap")
            chapter_dict = {ch.text.strip(): ch.get('href') for ch in chapters if ch.get('href')}
            if chapter_dict:
                return chapter_dict
            else:
                logging.info("No chapter links found with requests; using Selenium fallback.")
                return fetch_chapter_links_selenium(series_url)
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching chapter links with requests (attempt {attempt+1}/{retry_attempts}): {e}")
            if attempt < retry_attempts - 1:
                time.sleep(2 ** attempt)
            else:
                logging.info("Using Selenium fallback for chapter links after repeated failures.")
                return fetch_chapter_links_selenium(series_url)
    return {}

def sort_chapters(chapters: dict) -> dict:
    """
    Sort the chapters based on the numerical part of their names.
    Returns a sorted dictionary.
    """
    def extract_chapter_number(chapter_name: str) -> float:
        match = re.search(r'Chapter (\d+(?:\.\d+)?)', chapter_name)
        return float(match.group(1)) if match else float('inf')
    sorted_items = sorted(chapters.items(), key=lambda x: extract_chapter_number(x[0]))
    return dict(sorted_items)

def download_and_process_image(filename: str, url: str):
    """
    Download an image from 'url', verify it, convert to RGB with a white background,
    and save it to 'filename'.
    """
    retry_attempts = 5
    for attempt in range(retry_attempts):
        try:
            parsed_url = urllib.parse.urlparse(url)
            headers = {
                'Accept': 'image/png,image/svg+xml,image/*;q=0.8,video/*;q=0.8,*/*;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/112.0.0.0 Safari/537.36'),
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://chapmanganato.to/',
                'Connection': 'keep-alive'
            }
            response = SESSION.get(url, headers=headers, stream=True)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                raise Exception(f"Invalid content type: {content_type}")
            with open(filename, 'wb') as f:
                f.write(response.content)
            with Image.open(filename) as img:
                img.verify()
            with Image.open(filename).convert("RGBA") as input_image:
                new_image = Image.new("RGB", input_image.size, "WHITE")
                new_image.paste(input_image, (0, 0), input_image)
                new_image.save(filename, quality=95)
            logging.info(f"Downloaded image: {filename}")
            break
        except (requests.exceptions.RequestException, UnidentifiedImageError, Exception) as e:
            logging.error(f"Error downloading image {filename} (attempt {attempt+1}/{retry_attempts}): {e}")
            if os.path.exists(filename):
                os.remove(filename)
            if attempt < retry_attempts - 1:
                time.sleep(2 ** attempt)
            else:
                error_filename = f"error_{os.path.basename(filename)}.html"
                if 'response' in locals() and response is not None:
                    with open(error_filename, 'wb') as f:
                        f.write(response.content)
                logging.error(f"Saved error response to {error_filename}")

def download_images_concurrently(urls: list, download_dir: str):
    """
    Download all images concurrently from the list 'urls' and save them into 'download_dir'.
    """
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx, url in enumerate(urls, start=1):
            filename = os.path.join(download_dir, f"{idx}.jpg")
            futures.append(executor.submit(download_and_process_image, filename, url))
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                logging.error(f"An image download failed: {exc}")

def download_chapter(chapter_name: str, chapter_url: str):
    """
    Download all manga images for a given chapter from 'chapter_url' and save them
    in a directory named after 'chapter_name'.
    """
    logging.info(f"Downloading chapter '{chapter_name}' from {chapter_url}")
    page_urls = fetch_page_links(chapter_url)
    if not page_urls:
        logging.error("No page images found for this chapter.")
        return
    num_pages = len(page_urls)
    logging.info(f"Found {num_pages} pages for chapter '{chapter_name}'")
    chapter_dir = os.path.join(BASE_DIR, chapter_name)
    os.makedirs(chapter_dir, exist_ok=True)
    download_images_concurrently(page_urls, chapter_dir)
    logging.info(f"Chapter '{chapter_name}' downloaded successfully in folder: {chapter_dir}")

def convert_chapter_to_pdf(chapter_name: str):
    """
    Convert all JPG images in the chapter folder to a single PDF file.
    """
    chapter_dir = os.path.join(BASE_DIR, chapter_name)
    if not os.path.exists(chapter_dir):
        logging.error(f"Chapter folder {chapter_dir} does not exist.")
        return
    image_files = [f for f in os.listdir(chapter_dir) if f.lower().endswith('.jpg')]
    if not image_files:
        logging.error("No images found in the chapter folder.")
        return
    image_files.sort(key=lambda x: int(re.findall(r'\d+', x)[0]))
    
    images = []
    for file in image_files:
        file_path = os.path.join(chapter_dir, file)
        try:
            img = Image.open(file_path).convert("RGB")
            images.append(img)
        except Exception as e:
            logging.error(f"Error opening image {file_path}: {e}")
            return

    pdf_filename = os.path.join(chapter_dir, f"{chapter_name}.pdf")
    try:
        if images:
            images[0].save(pdf_filename, save_all=True, append_images=images[1:], quality=95)
            logging.info(f"PDF saved as {pdf_filename}")
        else:
            logging.error("No images to convert.")
    except Exception as e:
        logging.error(f"Error saving PDF: {e}")

def convert_all_chapters_to_pdf(chapters: dict):
    """
    Convert all downloaded chapter folders to PDFs.
    """
    for chapter_name in chapters:
        logging.info(f"Converting chapter '{chapter_name}' to PDF...")
        convert_chapter_to_pdf(chapter_name)
        logging.info(f"Chapter '{chapter_name}' conversion to PDF completed.")

# ----------------- GUI Section using Tkinter -----------------

class MangaDownloaderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Manga Chapter Downloader")
        self.geometry("750x650")
        self.create_widgets()
        self.chapters = {}

    def create_widgets(self):
        self.url_label = ttk.Label(self, text="Enter the URL of the manga series:")
        self.url_label.pack(pady=5)
        self.url_entry = ttk.Entry(self, width=80)
        self.url_entry.pack(pady=5)
        self.fetch_button = ttk.Button(self, text="Fetch Chapters", command=self.fetch_chapters)
        self.fetch_button.pack(pady=5)
        self.chapter_listbox = tk.Listbox(self, width=80, height=10)
        self.chapter_listbox.pack(pady=10)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.chapter_listbox.yview)
        self.chapter_listbox.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.download_selected_button = ttk.Button(self, text="Download Selected Chapter", command=self.download_selected_chapter)
        self.download_selected_button.pack(pady=5)
        self.download_all_button = ttk.Button(self, text="Download All Chapters", command=self.download_all_chapters)
        self.download_all_button.pack(pady=5)
        self.convert_selected_button = ttk.Button(self, text="Convert Selected Chapter to PDF", command=self.convert_selected_to_pdf)
        self.convert_selected_button.pack(pady=5)
        self.convert_all_button = ttk.Button(self, text="Convert All Chapters to PDF", command=self.convert_all_to_pdf)
        self.convert_all_button.pack(pady=5)
        self.log_text = scrolledtext.ScrolledText(self, width=80, height=10)
        self.log_text.pack(pady=10)
        self.log("GUI Initialized.")

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def fetch_chapters(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL.")
            return
        self.log(f"Fetching chapters from {url}...")
        try:
            chapters = fetch_chapter_links(url)
            chapters = {name: link for name, link in chapters.items() if "Chapter" in name}
            chapters = sort_chapters(chapters)
            self.chapters = chapters
            self.chapter_listbox.delete(0, tk.END)
            for name in chapters:
                self.chapter_listbox.insert(tk.END, name)
            self.log(f"Found {len(chapters)} chapters.")
        except Exception as e:
            self.log(f"Error fetching chapters: {e}")
            messagebox.showerror("Error", f"Error fetching chapters: {e}")

    def download_selected_chapter(self):
        selection = self.chapter_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "Please select a chapter from the list.")
            return
        chapter_name = self.chapter_listbox.get(selection[0])
        chapter_url = self.chapters.get(chapter_name)
        self.log(f"Downloading chapter: {chapter_name}")
        threading.Thread(target=download_chapter, args=(chapter_name, chapter_url), daemon=True).start()
        self.log(f"Download for chapter '{chapter_name}' started.")

    def download_all_chapters(self):
        if not self.chapters:
            messagebox.showerror("Error", "No chapters to download. Fetch chapters first.")
            return
        self.log("Starting download of all chapters...")
        for chapter_name, chapter_url in self.chapters.items():
            self.log(f"Downloading chapter: {chapter_name}")
            threading.Thread(target=download_chapter, args=(chapter_name, chapter_url), daemon=True).start()
        self.log("Download for all chapters started.")

    def convert_selected_to_pdf(self):
        selection = self.chapter_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "Please select a chapter to convert.")
            return
        chapter_name = self.chapter_listbox.get(selection[0])
        self.log(f"Converting chapter '{chapter_name}' images to PDF...")
        threading.Thread(target=self.threaded_pdf_conversion, args=(chapter_name,), daemon=True).start()

    def threaded_pdf_conversion(self, chapter_name):
        try:
            convert_chapter_to_pdf(chapter_name)
            self.after(0, lambda: self.log(f"PDF conversion completed for chapter '{chapter_name}'."))
        except Exception as e:
            self.after(0, lambda: self.log(f"Error converting chapter '{chapter_name}' to PDF: {e}"))

    def convert_all_to_pdf(self):
        if not self.chapters:
            messagebox.showerror("Error", "No chapters available. Please fetch chapters first.")
            return
        self.log("Starting PDF conversion for all chapters...")
        threading.Thread(target=self.threaded_all_pdf_conversion, daemon=True).start()

    def threaded_all_pdf_conversion(self):
        try:
            convert_all_chapters_to_pdf(self.chapters)
            self.after(0, lambda: self.log("PDF conversion completed for all chapters."))
        except Exception as e:
            self.after(0, lambda: self.log(f"Error during bulk PDF conversion: {e}"))

def main():
    app = MangaDownloaderGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
