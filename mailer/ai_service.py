import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError, ClientError

load_dotenv()

def generate_email_content(receiver_name, description, subject=None, tone='professional', document_text=None):
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from .env file.")

    client = genai.Client(api_key=api_key)

    prompt = f"Write an email to {receiver_name}.\n"
    prompt += f"Desired Tone: {tone.capitalize()}\n"
    
    if subject:
        prompt += f"Requested Subject Hint: {subject}\n"
        
    prompt += f"Core Description & Goal: {description}\n"

    if document_text:
        prompt += f"\nReference Context from Uploaded Document:\n\"\"\"\n{document_text}\n\"\"\"\n"

    prompt += (
        "\nOutput Instructions:\n"
        "1. Maintain a clean, precise email format matched strictly to the requested tone.\n"
        "2. Do NOT use placeholder tokens like [Your Name] or [Insert Title].\n"
        "3. If a subject was provided, output ONLY the email body.\n"
        "4. If no subject was provided, put the subject on line 1 formatted exactly as 'SUBJECT: <Your Subject>' followed by a blank line, then the body."
    )

    candidate_models = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-pro',
    ]

    response = None
    last_exception = None

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    break
            except (ServerError, ClientError) as e:
                last_exception = e
                time.sleep(1)
                continue
        if response and response.text:
            break

    if not response or not response.text:
        raise Exception(f"AI Service temporary overload. Please try again later. Details: {last_exception}")

    response_text = response.text.strip()

    if not subject and "SUBJECT:" in response_text:
        lines = response_text.split('\n')
        new_subject = lines[0].replace('SUBJECT:', '').strip()
        body = '\n'.join(lines[1:]).strip()
        return new_subject, body

    return subject or "No Subject", response_text