from flask import Flask, render_template, request, send_file
import os
from dotenv import load_dotenv
import docx
from docx.shared import Pt, RGBColor, Inches
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
        "Given the following CV text, please extract and format ALL relevant information  "
        "into a well-structured, professional-looking resume. Scan word documents with text in tables better, scan as much as possible. Follow these strict guidelines:\n\n"
        "1. DO NOT summarize, rephrase, or create new categories. Extract the information as-is. At maximum, make grammatical improvements.\n"
        "2. Maintain 95-98% of the original text, correcting only obvious spelling mistakes.\n"
        "3. Preserve the original formatting and structure of the CV as much as possible.\n"
        "4. Do not create summaries or mini-categories (e.g., don't summarize skills).\n"
        "5. Extract ALL information from the CV, including full sentences and bullet points.\n"
        "6. Use the exact words and phrases from the original CV whenever possible.\n"
        "7. Do not add any information that is not present in the original CV.\n"
        "8. Preserve the original order of information as it appears in the CV.\n"
        "9. If there's any mention of preferred position, desired role, career objective, or similar concepts, "
        "include it under a section called 'Career Objective' or 'Preferred Position'.\n"
        "10. Use the following format for structuring the extracted information:\n"
        "[NAME]Full Name\n"
        "[SECTION]Section Heading\n"
        "[COMPANY]Company Name[TAB]Location\n"
        "[JOBTITLE]Job Title[TAB]Date Range\n"
        "[BULLET]Bullet point\n"
        "[NORMAL]Normal text\n\n"
        "11. Ensure that dates are consistently formatted and placed at the end of the line.\n"
        "12. Include countries or cities where the person has worked or studied.\n"
        "13. Remove all contact-based information if possible, also, parent names, passport number, marital status, religion or similar except\n\n"
        f"CV Text:\n{cv_text}\n\n"
        "Please provide the formatted CV content, ready to be inserted into a Word document. "
        "Remember to maintain the original content as much as possible except information not relevant in a CV."
        "Remove any generic prompts such as 'Here's you formatted cv'and etc just provide the information requested" 
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
    return text.replace("[JOBTITLE]", "").replace("[NORMAL]", "").replace("[BULLET]", "•")

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
        doc = docx.Document()

        if cv_image:
            image_stream = io.BytesIO()
            cv_image.save(image_stream, format="PNG")
            image_stream.seek(0)
            doc.add_picture(image_stream, width=Inches(1.5))
            last_paragraph = doc.paragraphs[-1]
            last_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        styles = doc.styles

        # Style for applicant name
        name_style = styles.add_style('Name', WD_STYLE_TYPE.PARAGRAPH)
        name_style.font.size = Pt(18)
        name_style.font.bold = True
        name_style.font.name = modern_font
        name_style.font.color.rgb = RGBColor(0, 0, 139)
        name_style.paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        # Style for sections
        section_style = styles.add_style('Section', WD_STYLE_TYPE.PARAGRAPH)
        section_style.font.size = Pt(14)
        section_style.font.bold = True
        section_style.font.name = modern_font
        section_style.font.color.rgb = RGBColor(0, 0, 139)
        section_style.paragraph_format.space_after = Pt(6)

        # Style for companies
        company_style = styles.add_style('Company', WD_STYLE_TYPE.PARAGRAPH)
        company_style.font.size = Pt(12)
        company_style.font.bold = True
        company_style.font.name = modern_font

        # Style for job titles (italicized)
        job_title_style = styles.add_style('JobTitle', WD_STYLE_TYPE.PARAGRAPH)
        job_title_style.font.size = Pt(11)
        job_title_style.font.italic = True
        job_title_style.font.name = modern_font

        # Normal style for normal text
        normal_style = styles['Normal']
        normal_style.font.size = Pt(11)
        normal_style.font.name = modern_font

        # Set consistent line spacing
        for style in [normal_style, section_style, company_style, job_title_style]:
            style.paragraph_format.space_after = Pt(0)  # Set uniform space after paragraphs
            style.paragraph_format.line_spacing = 1.0  # Uniform line spacing

        right_tab_stop = Inches(6.5)  # Set up right-aligned tab stop for dates and locations

        # Clean and process the text upfront
        cleaned_cv = clean_text(formatted_cv)

        lines = cleaned_cv.split('\n')
        applicant_name = ""

        for line in lines:
            line = line.strip()
            logger.debug(f"Processing line: {line}")

            if line.startswith('[NAME]'):
                doc.add_paragraph(line[6:], style='Name')
                applicant_name = line[6:].strip()
            elif line.startswith('[SECTION]'):
                doc.add_paragraph("")  # Blank line before the section
                doc.add_paragraph(line[9:], style='Section')
            elif line.startswith('[COMPANY]'):
                p = doc.add_paragraph(style='Company')
                parts = line[9:].split('[TAB]')
                p.add_run(parts[0].strip())
                if len(parts) > 1:
                    p.add_run('\t' + parts[1].strip())
                    p.paragraph_format.tab_stops.add_tab_stop(right_tab_stop, WD_TAB_ALIGNMENT.RIGHT)
            elif '[TAB]' in line:
                p = doc.add_paragraph(style='JobTitle')
                parts = line.split('[TAB]')
                p.add_run(parts[0].strip())
                if len(parts) > 1:
                    p.add_run('\t' + parts[1].strip())
                    p.paragraph_format.tab_stops.add_tab_stop(right_tab_stop, WD_TAB_ALIGNMENT.RIGHT)
            elif line.startswith('•'):
                p = doc.add_paragraph(style='List Bullet')
                p.text = line[1:].strip()  # Remove the bullet character
            elif line:
                doc.add_paragraph(line, style='Normal')

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