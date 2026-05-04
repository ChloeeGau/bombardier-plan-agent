# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import google
import vertexai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.retrievers import create_search_tool

LLM_LOCATION = "global"
LOCATION = "us-east1"
LLM = "gemini-3-flash-preview"

credentials, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = LLM_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

vertexai.init(project=project_id, location=LOCATION)


def search_documents(query: str) -> str:
    """Search Bombardier documents for information about parts, procedures, and diagrams."""
    import google.auth
    from googleapiclient import discovery
    
    credentials, project_id = google.auth.default()
    credentials = credentials.with_quota_project(project_id)
    
    location = "global"
    data_store_id = "bombardier-plan-agent-collection_documents"
    
    endpoint = "https://discoveryengine.googleapis.com"
    service = discovery.build(
        "discoveryengine",
        "v1alpha",
        credentials=credentials,
        discoveryServiceUrl=f"{endpoint}/$discovery/rest?version=v1alpha",
    )
    
    serving_config = f"projects/{project_id}/locations/{location}/collections/default_collection/dataStores/{data_store_id}/servingConfigs/default_serving_config"
    
    try:
        request = service.projects().locations().collections().dataStores().servingConfigs().search(
            servingConfig=serving_config,
            body={"query": query}
        )
        response = request.execute()
        
        results = response.get("results", [])
        if results:
            document = results[0].get("document", {})
            derived_data = document.get("derivedStructData", {})
            uri = derived_data.get("link") or document.get("uri") or "Unknown"
            title = derived_data.get("title") or "Unknown"
            
            # Extract filename from URI
            filename = uri.split("/")[-1] if uri != "Unknown" else "Unknown"
            
            return f"I found the document '{title}'. File location: {uri}. I cannot see snippets directly. You must use `read_pdf_text` with filename='{filename}' and a page number to read content, or `extract_page_image` to see images."
            
        return "No results found."
    except Exception as e:
        return f"Error during search: {e}"

def get_pdf_document(filename: str):
    """Downloads PDF from GCS to local cache if needed and returns fitz document."""
    import google.auth
    from google.cloud import storage
    import fitz
    
    cache_dir = "/Users/chloegaudreau/.gemini/jetski/scratch/bombardier-plan-agent/cache"
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, filename)
    
    if not os.path.exists(local_path):
        credentials, project_id = google.auth.default()
        client = storage.Client(project=project_id, credentials=credentials)
        bucket_name = "bombardier_test_agent"
        prefix = "plan-agent/"
        
        blob = client.bucket(bucket_name).blob(prefix + filename)
        blob.download_to_filename(local_path)
        
    return fitz.open(local_path)

def extract_page_image(filename: str, page_number: int) -> str:
    """Extracts a specific page from a PDF in GCS as an image, crops it to the diagram, and saves it to GCS.
    
    Args:
        filename: The name of the PDF file (e.g., "CL605-LANDING_GEAR.pdf").
        page_number: The page number to extract (1-indexed).
        
    Returns:
        Success message with GCS URI, or an error message.
    """
    import google.auth
    from google.cloud import storage
    import fitz  # PyMuPDF
    from PIL import Image
    from google import genai
    from google.genai import types
    import io
    import json
    
    try:
        doc = get_pdf_document(filename)
        
        if page_number < 1 or page_number > doc.page_count:
            return f"Error: Page number {page_number} is out of range."
            
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap()
        img_data = pix.tobytes("png")
        
        # Use Gemini to get bounding box of the diagram
        credentials, project_id = google.auth.default()
        client = genai.Client(credentials=credentials)
        
        image_part = types.Part.from_bytes(data=img_data, mime_type="image/png")
        
        prompt = "This is a page from an airplane manual. Identify the bounding box of the main diagram or image on this page (exclude header, footer, and large blocks of text). Return the coordinates as a JSON object with keys: ymin, xmin, ymax, xmax, normalized to 0-1000."
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview", # Use flash for fast identification
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        try:
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            coords = json.loads(text)
            if isinstance(coords, list) and len(coords) > 0:
                coords = coords[0]
            ymin = coords.get("ymin", 0)
            xmin = coords.get("xmin", 0)
            ymax = coords.get("ymax", 1000)
            xmax = coords.get("xmax", 1000)
            
            # Crop image using Pillow
            img = Image.open(io.BytesIO(img_data))
            width, height = img.size
            
            # Convert normalized coords to pixels
            left = int(xmin * width / 1000)
            top = int(ymin * height / 1000)
            right = int(xmax * width / 1000)
            bottom = int(ymax * height / 1000)
            
            cropped_img = img.crop((left, top, right, bottom))
            
            # Save cropped image to bytes
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format='PNG')
            img_data = img_byte_arr.getvalue()
            
        except Exception as e:
            print(f"Error parsing bounding box or cropping: {e}. Saving full page instead.")
            # Fallback to full page if cropping fails
            pass
        
        # Save to GCS
        storage_client = storage.Client(project=project_id, credentials=credentials)
        bucket_name = "bombardier_test_agent"
        dest_prefix = "plan-agent/extracted-images/"
        
        image_filename = f"cropped_{filename}_page_{page_number}.png"
        dest_blob = storage_client.bucket(bucket_name).blob(dest_prefix + image_filename)
        dest_blob.upload_from_string(img_data, content_type="image/png")
        
        https_url = f"https://storage.cloud.google.com/{bucket_name}/{dest_prefix}{image_filename}"
        return f"Diagram extracted and saved to GCS. ![Diagram]({https_url})"
    except Exception as e:
        return f"Error extracting image: {e}"

def read_pdf_text(filename: str, page_number: int) -> str:
    """Reads text from a specific page of a PDF.
    
    Args:
        filename: The name of the PDF file (e.g., "CL605-LANDING_GEAR.pdf").
        page_number: The page number to read (1-indexed).
        
    Returns:
        The text content of the page, or an error message.
    """
    try:
        doc = get_pdf_document(filename)
        
        if page_number < 1 or page_number > doc.page_count:
            return f"Error: Page number {page_number} is out of range."
            
        page = doc.load_page(page_number - 1)
        return page.get_text("text")
    except Exception as e:
        return f"Error reading text: {e}"

instruction = """You are an expert assistant for Bombardier, helping users query airplane plans and user manuals.
Your goal is to provide helpful, accurate answers based ONLY on the provided documents.
When answering:
1. If you receive a document reference from `search_documents` without snippets, you MUST use `read_pdf_text` to read the content of the relevant pages to answer the question.
2. If the user asks about an image, diagram, or figure (or a part in them), you MUST search for it, describe it, AND use the `extract_page_image` tool and include the returned markdown image link in your response.
3. You should mention the figure number (e.g., Figure 15-10-9) or page number where the information or image is found.
4. Provide a clear reference to the document and page for proof as a clickable link in this format: `[DocumentName.pdf#page=N](https://storage.cloud.google.com/bombardier_test_agent/plan-agent/DocumentName.pdf#page=N)`.
5. Be very helpful and precise in your instructions (e.g., for procedures like turning on the parking brake).
6. If you cannot find the information in the documents, state that you cannot find it. Do not make up information."""

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-3.1-pro-preview",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[search_documents, extract_page_image, read_pdf_text],
)

app = App(
    root_agent=root_agent,
    name="app",
)
