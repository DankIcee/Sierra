from flask import Flask, render_template, request, send_file
import os
from dotenv import load_dotenv
import docx
from docx.shared import Pt, Inches
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT, WD_TAB_ALIGNMENT
from PyPDF2 import PdfReader
from anthropic import Anthropic
from PIL import Image, ExifTags
import io
import fitz  # PyMuPDF for image extraction
import re
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')

client = Anthropic(api_key=anthropic_api_key)

modern_font = "Calibri"  # Or "Arial" as per preference

def fix_image_orientation(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = dict(image._getexif().items())

        if exif[orientation] == 3:
            image = image.rotate(180, expand=True)
        elif exif[orientation] == 6:
            image = image.rotate(270, expand=True)
        elif exif[orientation] == 8:
            image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        # EXIF data not available, use a more cautious heuristic
        width, height = image.size
        if width > height and width / height > 1.5:
            # Only rotate if the image is significantly wider than it is tall
            image = image.rotate(90, expand=True)
    return image

def extract_cv_information(cv_text):
    prompt = (
        "You are an AI assistant that extracts and formats information from resumes. "
        "Given the following CV text, please extract and format ALL relevant information "
        "into a well-structured, professional-looking resume. Scan word documents with text in tables better, scan as much as possible. Follow these strict guidelines:\n\n"
        "1. DO NOT summarize, rephrase, or create new categories. Extract the information as-is. At maximum, make grammatical improvements.\n"
        "2. Preserve the main context and meaning of the original text, correcting obvious spelling and grammatical mistakes, and improving clarity if needed.\n"
        "3. Preserve the original formatting and structure of the CV as much as possible.\n"
        "4. Do not create summaries or mini-categories (e.g., don't summarize skills).\n"
        "5. Extract ALL information from the CV, including full sentences and bullet points.\n"
        "6. Use the exact words and phrases from the original CV whenever possible.\n"
        "7. Do not add any information that is not present in the original CV.\n"
        "8. Preserve the original order of information as it appears in the CV.\n"
        "9. If there's any mention of preferred position, desired role, career objective, or similar concepts, "
        "include it under a section called 'Summary'.\n"
        "10. Use the following format for structuring the extracted information:\n"
        "[NAME]Full Name\n"
        "[SECTION]Section Heading\n"
        "[COMPANY]Company Name[TAB]Location\n"
        "[JOBTITLE]Job Title[TAB]Date Range\n"
        "[EDUCATION]Degree or Qualification[TAB]Date\n"
        "[INSTITUTION]Institution Name[TAB]Location\n"
        "[BULLET]Bullet point\n"
        "[NORMAL]Normal text\n\n"
        "11. Ensure that dates are consistently formatted and placed at the end of the line.\n"
        "12. Include countries or cities where the person has worked or studied, ensuring they are properly formatted with correct capitalization (e.g., 'Dubai, United Arab Emirates'). Do not include any asterisks or special characters.\n"
        "13. Remove all contact-based information if possible, also, parent names, passport number, marital status, religion or similar except\n"
        "14. Combine multiple profile descriptions into a single coherent paragraph under the 'Summary' section.\n"
        "15. Organize the content in the following order (if available):\n"
        "    - Summary/Profile information (Name it as 'Summary')\n"
        "    - Work Experience and etc (Name as 'Experience')\n"
        "    - Courses\n"
        "    - Education\n"
        "    - Languages (only if explicitly mentioned in the CV)\n"
        "    - Hobbies/Interests (only if explicitly mentioned in the CV)\n"
        "    - Others\n"
        "16. If there is any additional information not fitting into the above categories, include it at the end under a section called 'Additional Information' or 'Others'.\n"
        "17. When listing locations (cities and countries), write them with proper capitalization, and do not include any asterisks or special characters.\n\n"
        f"CV Text:\n{cv_text}\n\n"
        "Please provide the formatted CV content, ready to be inserted into a Word document. "
        "Remember to maintain the original content as much as possible except information not relevant in a CV."
        "Remove any generic prompts such as 'Here's your formatted CV' and etc. Just provide the information requested."
    )

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in AI processing: {str(e)}")
        raise

def extract_text_from_pdf(pdf_path):
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise

def extract_image_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            image_list = page.get_images(full=True)
            if image_list:
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_stream = io.BytesIO(image_bytes)
                    image = Image.open(image_stream)
                    image = fix_image_orientation(image)
                    return image  # Return the first image found
    except Exception as e:
        logger.error(f"Error extracting image from PDF: {str(e)}")
        return None

def extract_text_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        full_text = []

        for para in doc.paragraphs:
            full_text.append(para.text)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text.append(cell.text)

        return '\n'.join(full_text)
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {str(e)}")
        raise

def extract_image_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        for rel in doc.part.rels:
            if "image" in doc.part.rels[rel].target_ref:
                image = doc.part.rels[rel].target_part.blob
                image_stream = io.BytesIO(image)
                img = Image.open(image_stream)
                img = fix_image_orientation(img)
                return img
    except Exception as e:
        logger.error(f"Error extracting image from DOCX: {str(e)}")
        return None

def clean_and_normalize_text(text):
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Replace multiple newlines with a single newline
    text = re.sub(r'\n+', '\n', text)
    # Remove any remaining special characters or non-printable characters
    text = re.sub(r'[^\x20-\x7E\n]', '', text)
    return text

def clean_text(text):
    # Remove all unwanted placeholders from the text
    text = text.replace("[JOBTITLE]", "").replace("[NORMAL]", "").replace("[TAB]", "\t")
    # Remove any asterisks
    text = text.replace("*", "")
    return text

def is_date(text):
    # Simple date pattern matching
    date_patterns = [
        r'\d{4}',  # Year
        r'\d{4}-\d{4}',  # Year range
        r'\d{4} to \d{4}',  # Year range with "to"
        r'\d{4} - present',  # Year to present
        r'\d{4} to present',  # Year to present with "to"
        r'\w+ \d{4}',  # Month Year
        r'\w+ \d{4} - \w+ \d{4}',  # Month Year range
        r'\w+ \d{4} to \w+ \d{4}',  # Month Year range with "to"
    ]
    return any(re.match(pattern, text.strip().lower()) for pattern in date_patterns)

def create_word_doc(output_path, formatted_cv, cv_image=None):
    try:
        # Load the template document
        doc = docx.Document('templates/naas_template.docx')

        # Assume that the styles are already defined in the template
        styles = doc.styles

        # Update styles to ensure all text is black
        for style in styles:
            if hasattr(style, 'font'):
                style.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Set to black

        # Set up the right tab stop (adjust according to your template's page setup)
        right_tab_stop = Inches(6)  # Adjust as needed

        # Clean and process the text upfront
        cleaned_cv = clean_text(formatted_cv)

        lines = cleaned_cv.split('\n')
        applicant_name = ""
        current_section = ""
        last_job_title = False

        # Insert the photo at the top
        if cv_image:
            image_stream = io.BytesIO()
            cv_image.save(image_stream, format="PNG")
            image_stream.seek(0)
            # Insert image at the beginning of the document
            doc.add_picture(image_stream, width=Inches(1.5))
            last_paragraph = doc.paragraphs[-1]
            last_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        for line in lines:
            line = line.strip()
            logger.debug(f"Processing line: {line}")

            if line.startswith('[NAME]'):
                p = doc.add_paragraph(line[len('[NAME]'):].strip(), style='Name')
                p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                p.runs[0].font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure name is black
                applicant_name = line[len('[NAME]'):].strip()
            elif line.startswith('[SECTION]'):
                current_section = line[len('[SECTION]'):].strip().lower()
                if current_section not in ['languages', 'hobbies', 'interests']:
                    doc.add_paragraph("")  # Blank line before the section
                    p = doc.add_paragraph(line[len('[SECTION]'):].strip().upper(), style='Section')
                    p.runs[0].font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure section header is black
            elif line.startswith('[COMPANY]'):
                if last_job_title:
                    doc.add_paragraph("")  # Add space after each job
                p = doc.add_paragraph(style='Company')
                parts = line[len('[COMPANY]'):].split('\t')
                company_name = parts[0].strip()
                company_run = p.add_run(company_name)
                company_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure company name is black
                if len(parts) > 1:
                    location = parts[1].strip()
                    location = location.replace("*", "")  # Remove asterisks if any
                    location_run = p.add_run('\t' + location)
                    location_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)
                    location_run.italic = True  # Make location italic
                p.paragraph_format.tab_stops.add_tab_stop(right_tab_stop, WD_TAB_ALIGNMENT.RIGHT)
                last_job_title = False
            elif line.startswith('[JOBTITLE]'):
                p = doc.add_paragraph(style='JobTitle')
                parts = line[len('[JOBTITLE]'):].split('\t')
                job_title = parts[0].strip()
                run = p.add_run(job_title)
                run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure job title is black
                run.italic = True  # Make job title italic
                if len(parts) > 1:
                    date_range = parts[1].strip()
                    date_run = p.add_run('\t' + date_range)
                    date_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)
                    p.paragraph_format.tab_stops.add_tab_stop(right_tab_stop, WD_TAB_ALIGNMENT.RIGHT)
                last_job_title = True
            elif line.startswith('[EDUCATION]'):
                # In education section, degree or qualification
                p = doc.add_paragraph(style='Normal')
                parts = line[len('[EDUCATION]'):].split('\t')
                degree = parts[0].strip()
                run = p.add_run(degree)
                run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure degree is black
                if len(parts) > 1:
                    date = parts[1].strip()
                    date_run = p.add_run('\t' + date)
                    date_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)
                    p.paragraph_format.tab_stops.add_tab_stop(right_tab_stop, WD_TAB_ALIGNMENT.RIGHT)
            elif line.startswith('[INSTITUTION]'):
                # Institution name and location
                p = doc.add_paragraph(style='Normal')
                parts = line[len('[INSTITUTION]'):].split('\t')
                institution = parts[0].strip()
                run = p.add_run(institution)
                run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure institution name is black
                run.italic = True  # Make institution name italic
                if len(parts) > 1:
                    location = parts[1].strip()
                    location = location.replace("*", "")  # Remove asterisks if any
                    location_run = p.add_run(', ' + location)
                    location_run.font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure location is black
                    location_run.italic = True  # Make location italic
                doc.add_paragraph("")  # Add space after each education entry
            elif line.startswith('[BULLET]'):
                p = doc.add_paragraph(style='List Bullet')
                p.text = line[len('[BULLET]'):].strip()
                p.runs[0].font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure bullet point is black
            elif line:
                p = doc.add_paragraph(line, style='Normal')
                p.runs[0].font.color.rgb = docx.shared.RGBColor(0, 0, 0)  # Ensure normal text is black
            
            # Add spacing after each company experience
            if last_job_title and not line.startswith('[COMPANY]') and not line.startswith('[JOBTITLE]') and not line.startswith('[BULLET]'):
                doc.add_paragraph("")  # Add an empty paragraph for spacing
                last_job_title = False

        # If there is any remaining content that was not included in the main sections, add it at the end
        # This can be implemented as needed based on how the content is structured

        doc.save(output_path)
        return applicant_name
    except Exception as e:
        logger.error(f"Error creating Word document: {str(e)}")
        logger.error(f"Problematic CV content: {formatted_cv}")
        raise

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}")
    # Return a generic error message
    return "An unexpected error occurred. Please try again later.", 500

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']

    if file.filename == '':
        return "No selected file", 400

    if file and (file.filename.endswith('.pdf') or file.filename.endswith('.docx')):
        upload_folder = 'uploads'
        output_folder = 'outputs'

        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

        file_path = os.path.join(upload_folder, file.filename)
        file.save(file_path)

        try:
            if file.filename.endswith('.pdf'):
                cv_text = extract_text_from_pdf(file_path)
                cv_image = extract_image_from_pdf(file_path)
            elif file.filename.endswith('.docx'):
                cv_text = extract_text_from_docx(file_path)
                cv_image = extract_image_from_docx(file_path)

            cv_text = clean_and_normalize_text(cv_text)
            formatted_cv = extract_cv_information(cv_text)
            logger.debug(f"Formatted CV content: {formatted_cv}")

            temp_output_path = os.path.join(output_folder, 'temp_CV.docx')
            applicant_name = create_word_doc(temp_output_path, formatted_cv, cv_image)

            if not applicant_name:
                applicant_name = "Unknown"

            base_filename = f'{applicant_name.replace(" ", "_")}_CV.docx'
            final_output_path = os.path.join(output_folder, base_filename)

            counter = 1
            while os.path.exists(final_output_path):
                base_filename = f'{applicant_name.replace(" ", "_")}_CV({counter}).docx'
                final_output_path = os.path.join(output_folder, base_filename)
                counter += 1

            os.rename(temp_output_path, final_output_path)

            return send_file(final_output_path, as_attachment=True)

        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return f"Error processing file: {str(e)}", 500

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    return "Unsupported file format. Please upload a PDF or DOCX.", 400

if __name__ == '__main__':
    app.run(debug=True)
