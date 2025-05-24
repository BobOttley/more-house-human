#!/usr/bin/env python3
import os
import pickle
import traceback
import sqlite3
import smtplib
import logging
from datetime import date, datetime
import pytz
import numpy as np
import openai
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from email.mime.text import MIMEText
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Initialise ──────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    logger.error("OPENAI_API_KEY not set in .env")
    raise RuntimeError("OPENAI_API_KEY not set in .env")

# SMTP configuration for alerts
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
MODERATOR_EMAIL = os.getenv("MODERATOR_EMAIL", "registrar@morehousemail.org.uk")

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app, resources={r"/ask": {"origins": "*"}, r"/status": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# ─── SQLite Database Setup ───────────────────────────────────────────────────
def init_db():
    db_path = '/tmp/db/flag.db'
    db_dir = os.path.dirname(db_path)
    
    try:
        # Create subdirectory if it doesn't exist
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            os.chmod(db_dir, 0o775)
            logger.info(f"Created directory {db_dir} with permissions 775")
        else:
            logger.info(f"Directory {db_dir} already exists")
        
        # Connect to database and create table
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                bot_response TEXT,
                human_response TEXT,
                status TEXT NOT NULL DEFAULT 'bot',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        
        # Set file permissions
        os.chmod(db_path, 0o664)
        logger.info(f"Set permissions for {db_path} to 664")
        conn.close()
        logger.info(f"Successfully initialized database at {db_path}")
    except Exception as e:
        logger.error(f"Error initializing database at {db_path}: {str(e)}")
        raise

try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    raise

# ─── URL lookup ───────────────────────────────────────────────────────────────
PAGE_LINKS = {
    "home": "https://www.morehouse.org.uk/",
    "homepage": "https://www.morehouse.org.uk/",
    "main page": "https://www.morehouse.org.uk/",
    "open events": "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open morning": "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open day": "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open evening": "https://www.morehouse.org.uk/admissions/our-open-events/",
    "admissions": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "enquiry": "https://www.morehouse.org.uk/admissions/enquiry/",
    "enquire": "https://www.morehouse.org.uk/admissions/enquiry/",
    "inquire": "https://www.morehouse.org.uk/admissions/enquiry/",
    "prospectus": "https://www.morehouse.org.uk/admissions/enquiry/",
    "fees": "https://www.morehouse.org.uk/admissions/fees/",
    "cost": "https://www.morehouse.org.uk/admissions/fees/",
    "costs": "https://www.morehouse.org.uk/admissions/fees/",
    "price": "https://www.morehouse.org.uk/admissions/fees/",
    "tuition": "https://www.morehouse.org.uk/admissions/fees/",
    "charges": "https://www.morehouse.org.uk/admissions/fees/",
    "scholarships": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "scholarship": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "scholarships and bursaries": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursaries": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursary": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursary scholarships": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "registration deadline": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "registration": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "register": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "registering": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "deadline": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "term dates": "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "terms": "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "calendar": "https://www.morehouse.org.uk/news-and-calendar/calendar/",
    "school calendar": "https://www.morehouse.org.uk/news-and-calendar/calendar/",
    "half term": "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "holiday dates": "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "uniform": "https://www.morehouse.org.uk/information/school-uniform/",
    "dress code": "https://www.morehouse.org.uk/information/school-uniform/",
    "contact": "https://www.morehouse.org.uk/contact/",
    "contact us": "https://www.morehouse.org.uk/contact/",
    "email": "https://www.morehouse.org.uk/contact/",
    "phone": "https://www.morehouse.org.uk/contact/",
    "telephone": "https://www.morehouse.org.uk/contact/",
    "our ethos": "https://www.morehouse.org.uk/our-school/our-ethos/",
    "ethos": "https://www.morehouse.org.uk/our-school/our-ethos/",
    "history": "https://www.morehouse.org.uk/our-school/history/",
    "our story": "https://www.morehouse.org.uk/our-school/more-house-stories/",
    "staff": "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "governors": "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "staff and governors": "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "head of school": "https://www.morehouse.org.uk/our-school/meet-the-head/",
    "meet the head": "https://www.morehouse.org.uk/our-school/meet-the-head/",
    "lettings": "https://www.morehouse.org.uk/information/lettings/",
    "venues": "https://www.morehouse.org.uk/information/lettings/",
    "school lunches": "https://www.morehouse.org.uk/information/school-lunches/",
    "lunch": "https://www.morehouse.org.uk/information/school-lunches/",
    "lunches": "https://www.morehouse.org.uk/information/school-lunches/",
    "meals": "https://www.morehouse.org.uk/information/school-lunches/",
    "pastoral care": "https://www.morehouse.org.uk/our-school/pastoral-care/",
    "safeguarding": "https://www.morehouse.org.uk/information/safeguarding/",
    "safety": "https://www.morehouse.org.uk/information/safeguarding/",
    "inspection reports": "https://www.morehouse.org.uk/information/inspection-reports/",
    "inspection": "https://www.morehouse.org.uk/information/inspection-reports/",
    "reports": "https://www.morehouse.org.uk/information/inspection-reports/",
    "school policies": "https://www.morehouse.org.uk/information/school-policies/",
    "policy": "https://www.morehouse.org.uk/information/school-policies/",
    "policies": "https://www.morehouse.org.uk/information/school-policies/",
    "pre-senior": "https://www.morehouse.org.uk/pre-senior/",
    "academic life": "https://www.morehouse.org.uk/learning/academic-life/",
    "academics": "https://www.morehouse.org.uk/learning/academic-life/",
    "subjects": "https://www.morehouse.org.uk/learning/subjects/",
    "sixth form": "https://www.morehouse.org.uk/learning/sixth-form/",
    "creative suite": "https://www.morehouse.org.uk/learning/our-creative-suite/",
    "creative": "https://www.morehouse.org.uk/learning/our-creative-suite/",
    "learning support": "https://www.morehouse.org.uk/learning/learning-support/",
    "support": "https://www.morehouse.org.uk/learning/learning-support/",
    "results and destinations": "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "destinations": "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "results": "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "be more": "https://www.morehouse.org.uk/learning/be-more/",
    "houses": "https://www.morehouse.org.uk/our-school/houses/",
    "co-curricular": "https://www.morehouse.org.uk/beyond-the-classroom/co-curricular-programme/",
    "sport": "https://www.morehouse.org.uk/beyond-the-classroom/sport/",
    "faith life": "https://www.morehouse.org.uk/beyond-the-classroom/faith-life/",
}

# ─── Human labels for fallback links ────────────────────────────────────────
URL_LABELS = {
    PAGE_LINKS["enquiry"]: "More about Enquiries",
    PAGE_LINKS["fees"]: "More about Fees",
    PAGE_LINKS["registration deadline"]: "More about Deadlines",
    PAGE_LINKS["term dates"]: "More about Term Dates",
    PAGE_LINKS["open events"]: "More about Open Events",
    PAGE_LINKS["uniform"]: "More about Uniform",
    PAGE_LINKS["school lunches"]: "More about Lunch Menu",
    PAGE_LINKS["academic life"]: "More about Academic Life",
    PAGE_LINKS["subjects"]: "More about Subjects",
    PAGE_LINKS["pre-senior"]: "More about Pre-Senior",
    PAGE_LINKS["houses"]: "More about Houses",
    PAGE_LINKS["co-curricular"]: "More about Co-curricular",
    PAGE_LINKS["sport"]: "More about Sport",
    PAGE_LINKS["faith life"]: "More about Faith Life",
    PAGE_LINKS["results and destinations"]: "More about Results",
    PAGE_LINKS["inspection reports"]: "More about Inspection Reports",
    PAGE_LINKS["school policies"]: "More about Policies",
    PAGE_LINKS["scholarships"]: "More about Scholarships",
    PAGE_LINKS["contact"]: "More about Contact",
    PAGE_LINKS["sixth form"]: "More about Sixth Form",
    PAGE_LINKS["pastoral care"]: "More about Pastoral Care",
    PAGE_LINKS["safeguarding"]: "More about Safeguarding",
    PAGE_LINKS["head of school"]: "Meet the Head",
    PAGE_LINKS["lettings"]: "More about Facilities",
    PAGE_LINKS["learning support"]: "More about Learning Support",
    PAGE_LINKS["ethos"]: "More about Our Ethos",
    PAGE_LINKS["admissions"]: "More about Admissions",
    PAGE_LINKS["prospectus"]: "More about Prospectus",
    PAGE_LINKS["staff"]: "Meet Our Staff",
    "https://www.morehouse.org.uk/information/school-policies/": "More about Policies",
}

# ─── Static QAs ──────────────────────────────────────────────────────────────
STATIC_QAS = {
    "enquiry": (
        "Please complete our enquiry form and we will tailor a prospectus exactly for you and your child.",
        PAGE_LINKS["enquiry"],
        "More about Enquiries"
    ),
    "ask about enquiry": (
        "Please complete our enquiry form and we will tailor a prospectus exactly for you and your child.",
        PAGE_LINKS["enquiry"],
        "More about Enquiries"
    ),
    "prospectus": (
        "Please complete our enquiry form and we will tailor a prospectus exactly for you and your child.",
        PAGE_LINKS["prospectus"],
        "More about Prospectus"
    ),
    "what are the school fees": (
        "Our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "fees": (
        "Our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "price": (
        "Are you referring to school fees? If so, our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "charges": (
        "Are you referring to school fees? If so, our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "cost": (
        "Are you referring to school fees? If so, our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "costs": (
        "Are you referring to school fees? If so, our current tuition fees for 2024–25 are £10,530 per term, inclusive of VAT.",
        PAGE_LINKS["fees"],
        "More about Fees"
    ),
    "what is the school uniform": (
        "The uniform comprises a navy More House blazer, navy v-neck jumper, gingham blouse, navy skirt or trousers and sensible black leather shoes. For full details, see below.",
        PAGE_LINKS["uniform"],
        "More about Uniform"
    ),
    "uniform": (
        "The uniform comprises a navy More House blazer, navy v-neck jumper, gingham blouse, navy skirt or trousers and sensible black leather shoes. For full details, see below.",
        PAGE_LINKS["uniform"],
        "More about Uniform"
    ),
    "how do you cater for dietary requirements": (
        "Our Connect Catering team provides vegetarian options, a salad bar, daily desserts, and a tuck shop. Download the Summer Term menu via the link below.",
        PAGE_LINKS["school lunches"],
        "View School Menus"
    ),
    "dietary requirements": (
        "Our Connect Catering team provides vegetarian options, a salad bar, daily desserts, and a tuck shop. Download the Summer Term menu via the link below.",
        PAGE_LINKS["school lunches"],
        "View School Menus"
    ),
    "lunch menu": (
        "You can download our current school lunch menus (including dietary options) here:",
        PAGE_LINKS["school lunches"],
        "View School Menus"
    ),
    "lunch": (
        "You can download our current school lunch menus (including dietary options) here:",
        PAGE_LINKS["school lunches"],
        "View School Menus"
    ),
    "what are the term dates": (
        "Our published term dates, half-terms and holiday dates can be found here:",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "term dates": (
        "Our published term dates, half-terms and holiday dates can be found here:",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "half term": (
        "Our published term dates, half-terms and holiday dates can be found here:",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "holiday dates": (
        "Our published term dates, half-terms and holiday dates can be found here:",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "what are the registration deadlines": (
        "11+ Entrance: noon, 7 November 2025; Sixth Form: 14 November 2025; Pre-Senior: year-round applications.",
        PAGE_LINKS["registration deadline"],
        "More about Registration"
    ),
    "registration deadlines": (
        "11+ Entrance: noon, 7 November 2025; Sixth Form: 14 November 2025; Pre-Senior: year-round applications.",
        PAGE_LINKS["registration deadline"],
        "More about Registration"
    ),
    "register": (
        "11+ Entrance: noon, 7 November 2025; Sixth Form: 14 November 2025; Pre-Senior: year-round applications.",
        PAGE_LINKS["registration deadline"],
        "More about Registration"
    ),
    "what are the open events": (
        "Summer Term 2025: Open Morning on 18 June; Autumn Term 2025: Open Evening on 17 September, Open Mornings on 10 October & 5 November; Spring Term 2026: Open Morning on 23 January & Open Evening on 5 March; Summer Term 2026: Open Morning on 13 May & Open Evening on 17 June.",
        PAGE_LINKS["open events"],
        "View Open Events"
    ),
    "open events": (
        "Summer Term 2025: Open Morning on 18 June; Autumn Term 2025: Open Evening on 17 September, Open Mornings on 10 October & 5 November; Spring Term 2026: Open Morning on 23 January & Open Evening on 5 March; Summer Term 2026: Open Morning on 13 May & Open Evening on 17 June.",
        PAGE_LINKS["open events"],
        "View Open Events"
    ),
    "tell me about scholarships and bursaries": (
        "We offer a range of bursaries and scholarships to support families in need. For eligibility criteria and application details, please visit our Scholarships & Bursaries page.",
        PAGE_LINKS["scholarships"],
        "More about Scholarships"
    ),
    "bursaries": (
        "We offer a range of bursaries and scholarships to support families in need. For eligibility criteria and application details, please visit our Scholarships & Bursaries page.",
        PAGE_LINKS["scholarships"],
        "More about Scholarships"
    ),
    "scholarships": (
        "We offer a range of bursaries and scholarships to support families in need. For eligibility criteria and application details, please visit our Scholarships & Bursaries page.",
        PAGE_LINKS["scholarships"],
        "More about Scholarships"
    ),
    "tell me about the sixth form": (
        "Thank you for your question! For full details of our Sixth Form—including courses, results and admissions—please visit our Sixth Form page.",
        PAGE_LINKS["sixth form"],
        "More about Sixth Form"
    ),
    "sixth form": (
        "Thank you for your question! For full details of our Sixth Form—including courses, results and admissions—please visit our Sixth Form page.",
        PAGE_LINKS["sixth form"],
        "More about Sixth Form"
    ),
    "how can i contact the school": (
        "You can contact our Admissions team by email at registrar@morehousemail.org.uk or by phone on 020 1234 5678. For full details, visit our Contact page.",
        PAGE_LINKS["contact"],
        "Contact Us"
    ),
    "contact": (
        "You can contact our Admissions team by email at registrar@morehousemail.org.uk or by phone on 020 1234 5678. For full details, visit our Contact page.",
        PAGE_LINKS["contact"],
        "Contact Us"
    ),
    "who is the head of school": (
        "The Head of School is Ms Claire Phelps. For more about her vision and background, please visit our Meet the Head page.",
        PAGE_LINKS["head of school"],
        "Meet the Head"
    ),
    "head of school": (
        "The Head of School is Ms Claire Phelps. For more about her vision and background, please visit our Meet the Head page.",
        PAGE_LINKS["head of school"],
        "Meet the Head"
    ),
    "how do you support students pastoral care": (
        "We offer dedicated pastoral teams, regular check-ins and specialised programmes to support every student's wellbeing. See our Pastoral Care page for details.",
        PAGE_LINKS["pastoral care"],
        "More about Pastoral Care"
    ),
    "what are your safeguarding policies": (
        "Our safeguarding policies ensure every pupil's safety both on and off campus. For full policy documents, visit our Safeguarding page.",
        PAGE_LINKS["safeguarding"],
        "View Safeguarding Policies"
    ),
    "what is academic life like": (
        "Academic Life at More House blends rigorous coursework with personalised support. Explore our approach on the Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "which subjects do you offer": (
        "We offer a wide range of subjects from STEM to humanities and creative arts. See the full list on our Subjects page.",
        PAGE_LINKS["subjects"],
        "View Subjects Offered"
    ),
    "tell me about pre-senior": (
        "Pre-Senior (Years 5–6) prepares pupils with a broad curriculum and pastoral support. Learn more on our Pre-Senior page.",
        PAGE_LINKS["pre-senior"],
        "More about Pre-Senior"
    ),
    "how does your house system work": (
        "Our house system fosters camaraderie and healthy competition across four houses. Find details on our Houses page.",
        PAGE_LINKS["houses"],
        "More about Houses"
    ),
    "what extracurricular activities do you offer": (
        "We run sport, music, drama, Duke of Edinburgh and more. Discover all options on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "what sports do you offer": (
        "We offer netball, hockey, football, rowing, athletics and more. Details are on our Sport page.",
        PAGE_LINKS["sport"],
        "View Sports Offered"
    ),
    "tell me about faith life": (
        "Faith Life includes regular reflection sessions and chaplaincy support. Visit our Faith Life page to learn more.",
        PAGE_LINKS["faith life"],
        "More about Faith Life"
    ),
    "what are your exam results": (
        "50% A*–A and 82% A*–B at A-Level; 95% progress to first-choice university or apprenticeship. See more on our Results & Destinations page.",
        PAGE_LINKS["results and destinations"],
        "View Results & Destinations"
    ),
    "results": (
        "50% A*–A and 82% A*–B at A-Level; 95% progress to first-choice university or apprenticeship. See more on our Results & Destinations page.",
        PAGE_LINKS["results and destinations"],
        "View Results & Destinations"
    ),
    "destinations": (
        "50% A*–A and 82% A*–B at A-Level; 95% progress to first-choice university or apprenticeship. See more on our Results & Destinations page.",
        PAGE_LINKS["results and destinations"],
        "View Results & Destinations"
    ),
    "where can i find inspection reports": (
        "All our latest inspection reports are published here:",
        PAGE_LINKS["inspection reports"],
        "View Inspection Reports"
    ),
    "inspection reports": (
        "All our latest inspection reports are published here:",
        PAGE_LINKS["inspection reports"],
        "View Inspection Reports"
    ),
    "inspection": (
        "All our latest inspection reports are published here:",
        PAGE_LINKS["inspection reports"],
        "View Inspection Reports"
    ),
    "exams": (
        "At More House School, our Public Exams Policy covers assessment methods, regulations and the support we offer students. You can read the full policy in our School Policies section.",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "exam policy": (
        "At More House School, our Public Exams Policy covers assessment methods, regulations and the support we offer students. You can read the full policy in our School Policies section.",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "teachers": (
        "Our dedicated teaching staff at More House School are experts in their subjects and committed to each pupil’s growth, both academically and personally. For full profiles, please visit our Staff & Governors page.",
        PAGE_LINKS["staff"],
        "Meet Our Staff"
    ),
    "teaching staff": (
        "Our dedicated teaching staff at More House School are experts in their subjects and committed to each pupil’s growth, both academically and personally. For full profiles, please visit our Staff & Governors page.",
        PAGE_LINKS["staff"],
        "Meet Our Staff"
    ),
    "universities": (
        "In our Sixth Form, students receive tailored university guidance—including Oxbridge support, mock interviews and visits to leading institutions. For full details, please visit our Results & Destinations page.",
        PAGE_LINKS["results and destinations"],
        "View Results & Destinations"
    ),
    "university guidance": (
        "In our Sixth Form, students receive tailored university guidance—including Oxbridge support, mock interviews and visits to leading institutions. For full details, please visit our Results & Destinations page.",
        PAGE_LINKS["results and destinations"],
        "View Results & Destinations"
    ),
    "transport": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,
        "View Bus Routes"
    ),
    "bus service": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,
        "View Bus Routes"
    ),
    "bus routes": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,
        "View Bus Routes"
    ),
    "after school clubs": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,
        "View After-School Clubs"
    ),
    "clubs": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,
        "View After-School Clubs"
    ),
    "after school": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,
        "View After-School Clubs"
    ),
    "parents evening": (
        "Our termly Parents’ Evenings let you meet teachers and review progress. Dates and booking info here:",
        None,
        "Book Parents’ Evening"
    ),
    "parent evenings": (
        "Our termly Parents’ Evenings let you meet teachers and review progress. Dates and booking info here:",
        None,
        "Book Parents’ Evening"
    ),
    "pta": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,
        "More about PTA"
    ),
    "friends of school": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,
        "More about PTA"
    ),
    "parents association": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,
        "More about PTA"
    ),
    "mental health": (
        "We have an on-site counsellor and weekly wellbeing workshops. Details here:",
        None,
        "More about Wellbeing"
    ),
    "wellbeing support": (
        "We have an on-site counsellor and weekly wellbeing workshops. Details here:",
        None,
        "More about Wellbeing"
    ),
    "sen": (
        "Our Learning Support team provides one-to-one and group SEN support. Read more here:",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "special educational needs": (
        "Our Learning Support team provides one-to-one and group SEN support. Read more here:",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "learning support": (
        "Our Learning Support team provides one-to-one and group SEN support. Read more here:",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "e-safety": (
        "We teach digital citizenship and monitor online use. See our e-Safety policy here:",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "online safety": (
        "We teach digital citizenship and monitor online use. See our e-Safety policy here:",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "alumni": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,
        "Join Our Alumnae"
    ),
    "old girls": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,
        "Join Our Alumnae"
    ),
    "past pupils": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,
        "Join Our Alumnae"
    ),
    "faith": (
        "At More House School, our Catholic faith is an integral part of our ethos and daily life. We foster a community where values of tolerance, justice and integrity are upheld. Daily prayers and weekly Chapel services help build our community spirit, and we celebrate special occasions such as St Thomas More’s Day and Days of Obligation.\n\n"
        "Our Faith in Action programme empowers pupils to initiate change locally and globally, partnering with CAFOD, The Cardinal Hume Centre and The WE Foundation. These experiences instil a sense of global citizenship as students campaign on issues like climate change and homelessness.",
        PAGE_LINKS["faith life"],
        "More about Faith Life"
    ),
    "religion": (
        "At More House School, our Catholic faith is an integral part of our ethos and daily life. We foster a community where values of tolerance, justice and integrity are upheld. Daily prayers and weekly Chapel services help build our community spirit, and we celebrate special occasions such as St Thomas More’s Day and Days of Obligation.\n\n"
        "Our Faith in Action programme empowers pupils to initiate change locally and globally, partnering with CAFOD, The Cardinal Hume Centre and The WE Foundation. These experiences instil a sense of global citizenship as students campaign on issues like climate change and homelessness.",
        PAGE_LINKS["faith life"],
        "More about Faith Life"
    ),
    "education": (
        "Education at More House School combines a rigorous academic curriculum with personalised support and enrichment from Years 5 through 13. For a full overview of our teaching approach, curriculum structure and support systems, please visit our Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "learning": (
        "Education at More House School combines a rigorous academic curriculum with personalised support and enrichment from Years 5 through 13. For a full overview of our teaching approach, curriculum structure and support systems, please visit our Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "apply": (
        "You can begin your application online via our Admissions page. For step-by-step guidance on entry requirements and key dates, please visit our Admissions page.",
        PAGE_LINKS["admissions"],
        "Apply Now"
    ),
    "application": (
        "You can begin your application online via our Admissions page. For step-by-step guidance on entry requirements and key dates, please visit our Admissions page.",
        PAGE_LINKS["admissions"],
        "Apply Now"
    ),
    "application form": (
        "You can begin your application online via our Admissions page. For step-by-step guidance on entry requirements and key dates, please visit our Admissions page.",
        PAGE_LINKS["admissions"],
        "Apply Now"
    ),
    "apply online": (
        "You can begin your application online via our Admissions page. For step-by-step guidance on entry requirements and key dates, please visit our Admissions page.",
        PAGE_LINKS["admissions"],
        "Apply Now"
    ),
    "entry requirements": (
        "Our entry requirements vary by year group; please see our Admissions page for detailed academic and age criteria for each entry point.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "admissions criteria": (
        "Our entry requirements vary by year group; please see our Admissions page for detailed academic and age criteria for each entry point.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "requirements": (
        "Our entry requirements vary by year group; please see our Admissions page for detailed academic and age criteria for each entry point.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "virtual tour": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,
        "Take Virtual Tour"
    ),
    "tour": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,
        "Take Virtual Tour"
    ),
    "visit us online": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,
        "Take Virtual Tour"
    ),
    "facilities": (
        "Our campus features science labs, a sports hall, arts studios and more. For full details on all our facilities and how to hire them, please visit our Lettings page.",
        PAGE_LINKS["lettings"],
        "More about Facilities"
    ),
    "labs": (
        "Our campus features science labs, a sports hall, arts studios and more. For full details on all our facilities and how to hire them, please visit our Lettings page.",
        PAGE_LINKS["lettings"],
        "More about Facilities"
    ),
    "sports hall": (
        "Our campus features science labs, a sports hall, arts studios and more. For full details on all our facilities and how to hire them, please visit our Lettings page.",
        PAGE_LINKS["lettings"],
        "More about Facilities"
    ),
    "drama": (
        "Our Drama & Theatre programme runs regular productions, workshops and classes. Discover our Performing Arts offerings on the Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "theatre": (
        "Our Drama & Theatre programme runs regular productions, workshops and classes. Discover our Performing Arts offerings on the Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "performing arts": (
        "Our Drama & Theatre programme runs regular productions, workshops and classes. Discover our Performing Arts offerings on the Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "robotics": (
        "Our Robotics & Coding clubs inspire future engineers through hands-on projects. Learn more about STEM enrichment on the Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "coding": (
        "Our Robotics & Coding clubs inspire future engineers through hands-on projects. Learn more about STEM enrichment on the Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "computer club": (
        "Our Robotics & Coding clubs inspire future engineers through hands-on projects. Learn more about STEM enrichment on the Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),
    "motto": (
        "Our school motto is ‘Ad Altiora’—aiming always for higher standards in character, learning and service. For more on our values, visit the Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "mission statement": (
        "Our school motto is ‘Ad Altiora’—aiming always for higher standards in character, learning and service. For more on our values, visit the Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "inset days": (
        "Our INSET days (staff training) are scheduled throughout the year. For full term-by-term dates including INSET and holiday breaks, please visit the Term Dates page.",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "staff training": (
        "Our INSET days (staff training) are scheduled throughout the year. For full term-by-term dates including INSET and holiday breaks, please visit the Term Dates page.",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "training day": (
        "Our INSET days (staff training) are scheduled throughout the year. For full term-by-term dates including INSET and holiday breaks, please visit the Term Dates page.",
        PAGE_LINKS["term dates"],
        "View Term Dates"
    ),
    "health and safety": (
        "Our Health & Safety policies safeguard every pupil on campus. For full details, please visit our Safeguarding page.",
        PAGE_LINKS["safeguarding"],
        "View Safeguarding Policies"
    ),
    "h&s": (
        "Our Health & Safety policies safeguard every pupil on campus. For full details, please visit our Safeguarding page.",
        PAGE_LINKS["safeguarding"],
        "View Safeguarding Policies"
    ),
    "accessibility": (
        "More House is committed to full accessibility across campus. For details on facilities and support, please visit our School Policies page.",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "disabled access": (
        "More House is committed to full accessibility across campus. For details on facilities and support, please visit our School Policies page.",
        PAGE_LINKS["school policies"],
        "View School Policies"
    ),
    "senco": (
        "Our SENCO leads specialist support for pupils with special educational needs. Learn more about our SEN provision on the Learning Support page.",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "send": (
        "Our SENCO leads specialist support for pupils with special educational needs. Learn more about our SEN provision on the Learning Support page.",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "special needs coordinator": (
        "Our SENCO leads specialist support for pupils with special educational needs. Learn more about our SEN provision on the Learning Support page.",
        PAGE_LINKS["learning support"],
        "More about Learning Support"
    ),
    "deadlines": (
        "Key application deadlines (11+, Sixth Form, Pre-Senior) are listed on our Admissions page. Please check the Admissions page for exact dates.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "entry deadlines": (
        "Key application deadlines (11+, Sixth Form, Pre-Senior) are listed on our Admissions page. Please check the Admissions page for exact dates.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "apply by": (
        "Key application deadlines (11+, Sixth Form, Pre-Senior) are listed on our Admissions page. Please check the Admissions page for exact dates.",
        PAGE_LINKS["admissions"],
        "More about Admissions"
    ),
    "values": (
        "Our core values—confidence, character, community and compassion—drive everything we do. To learn more, please visit our Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "our values": (
        "Our core values—confidence, character, community and compassion—drive everything we do. To learn more, please visit our Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "what are the values of the school": (
        "Our core values—confidence, character, community and compassion—drive everything we do. To learn more, please visit our Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "tell me about your values": (
        "Our core values—confidence, character, community and compassion—drive everything we do. To learn more, please visit our Ethos page.",
        PAGE_LINKS["ethos"],
        "More about Our Ethos"
    ),
    "alumni events": (
        "Our Alumnae network hosts reunions, mentorship programmes and regional events. For details and to register, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Join Our Alumnae"
    ),
    "reunion": (
        "Our Alumnae network hosts reunions, mentorship programmes and regional events. For details and to register, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Join Our Alumnae"
    ),
    "old girls": (
        "Our Alumnae network hosts reunions, mentorship programmes and regional events. For details and to register, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Join Our Alumnae"
    ),
    "parent portal": (
        "Our Parent Portal (ParentPay) lets you view invoices, pay fees and track attendance. For login details or support, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Access Parent Portal"
    ),
    "parentpay": (
        "Our Parent Portal (ParentPay) lets you view invoices, pay fees and track attendance. For login details or support, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Access Parent Portal"
    ),
    "portal": (
        "Our Parent Portal (ParentPay) lets you view invoices, pay fees and track attendance. For login details or support, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Access Parent Portal"
    ),
    "jobs": (
        "All current staff vacancies and application details are listed on our Vacancies page. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Vacancies"
    ),
    "vacancies": (
        "All current staff vacancies and application details are listed on our Vacancies page. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Vacancies"
    ),
    "careers at school": (
        "All current staff vacancies and application details are listed on our Vacancies page. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Vacancies"
    ),
    "behaviour policy": (
        "Our Behaviour Policy sets out expectations, support systems and procedures for student conduct. For any questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Behaviour Policy"
    ),
    "discipline": (
        "Our Behaviour Policy sets out expectations, support systems and procedures for student conduct. For any questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Behaviour Policy"
    ),
    "student conduct": (
        "Our Behaviour Policy sets out expectations, support systems and procedures for student conduct. For any questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Behaviour Policy"
    ),
    "uniform supplier": (
        "Our official uniform supplier is XYZ Outfitters. You can order via their website or contact the Director of Admissions at registrar@morehousemail.org.uk for assistance.",
        None,
        "Order Uniform"
    ),
    "where to buy uniform": (
        "Our official uniform supplier is XYZ Outfitters. You can order via their website or contact the Director of Admissions at registrar@morehousemail.org.uk for assistance.",
        None,
        "Order Uniform"
    ),
    "kit supplier": (
        "Our official uniform supplier is XYZ Outfitters. You can order via their website or contact the Director of Admissions at registrar@morehousemail.org.uk for assistance.",
        None,
        "Order Uniform"
    ),
    "lost property": (
        "Please check our Lost Property Office in reception during school hours. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Contact Lost Property"
    ),
    "found items": (
        "Please check our Lost Property Office in reception during school hours. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Contact Lost Property"
    ),
    "misplaced items": (
        "Please check our Lost Property Office in reception during school hours. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Contact Lost Property"
    ),
    "breakfast club": (
        "We run Breakfast Club from 7.30 am and After-School care until 6 pm. For bookings, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Book Wraparound Care"
    ),
    "after school care": (
        "We run Breakfast Club from 7.30 am and After-School care until 6 pm. For bookings, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Book Wraparound Care"
    ),
    "wraparound": (
        "We run Breakfast Club from 7.30 am and After-School care until 6 pm. For bookings, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "Book Wraparound Care"
    ),
    "exclusions": (
        "Details of our exclusions and disciplinary procedures are in the School Policies section. For more information, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View School Policies"
    ),
    "suspension": (
        "Details of our exclusions and disciplinary procedures are in the School Policies section. For more information, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View School Policies"
    ),
    "sanctions": (
        "Details of our exclusions and disciplinary procedures are in the School Policies section. For more information, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View School Policies"
    ),
    "ehcp": (
        "We support EHCP pupils through our Learning Support team. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Learning Support"
    ),
    "education health and care plan": (
        "We support EHCP pupils through our Learning Support team. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Learning Support"
    ),
    "sen support": (
        "We support EHCP pupils through our Learning Support team. For enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Learning Support"
    ),
    "counsellor": (
        "We have an on-site counsellor and weekly wellbeing workshops. For referrals or enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Wellbeing"
    ),
    "mental health support": (
        "We have an on-site counsellor and weekly wellbeing workshops. For referrals or enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Wellbeing"
    ),
    "wellbeing": (
        "We have an on-site counsellor and weekly wellbeing workshops. For referrals or enquiries, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "More about Wellbeing"
    ),
    "wi-fi": (
        "Students connect to our secure campus Wi-Fi; please refer to the IT Acceptable Use Policy. For technical issues, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View IT Policies"
    ),
    "internet access": (
        "Students connect to our secure campus Wi-Fi; please refer to the IT Acceptable Use Policy. For technical issues, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View IT Policies"
    ),
    "edtech": (
        "Students connect to our secure campus Wi-Fi; please refer to the IT Acceptable Use Policy. For technical issues, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View IT Policies"
    ),
    "covid policy": (
        "Our Health & Safety page covers illness protocols, immunisations and Covid measures. For further questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Health Policies"
    ),
    "health policy": (
        "Our Health & Safety page covers illness protocols, immunisations and Covid measures. For further questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Health Policies"
    ),
    "illness": (
        "Our Health & Safety page covers illness protocols, immunisations and Covid measures. For further questions, please contact the Director of Admissions at registrar@morehousemail.org.uk.",
        None,
        "View Health Policies"
    ),
    "policy": (
        "You can find all of More House School’s official policies—including safeguarding, health & safety, SEND, exams and more—on our Policies page.",
        "https://www.morehouse.org.uk/information/school-policies/",
        "View School Policies"
    ),
    "policies": (
        "You can find all of More House School’s official policies—including safeguarding, health & safety, SEND, exams and more—on our Policies page.",
        "https://www.morehouse.org.uk/information/school-policies/",
        "View School Policies"
    ),
    "music": (
        "Our Music Department offers individual lessons, ensembles, choir and orchestra. See timetables and performance opportunities on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "choir": (
        "Our Music Department offers individual lessons, ensembles, choir and orchestra. See timetables and performance opportunities on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "orchestra": (
        "Our Music Department offers individual lessons, ensembles, choir and orchestra. See timetables and performance opportunities on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
    "music lessons": (
        "Our Music Department offers individual lessons, ensembles, choir and orchestra. See timetables and performance opportunities on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),
}

# ─── Load embeddings & metadata ───────────────────────────────────────────────
try:
    with open("/app/embeddings.pkl", "rb") as f:
        embeddings = np.stack(pickle.load(f), axis=0)
    logger.info("Loaded embeddings.pkl")
except Exception as e:
    logger.error(f"Failed to load embeddings.pkl: {str(e)}")
    raise

try:
    with open("/app/metadata.pkl", "rb") as f:
        metadata = pickle.load(f)
    logger.info("Loaded metadata.pkl")
except Exception as e:
    logger.error(f"Failed to load metadata.pkl: {str(e)}")
    raise

EMB_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-3.5-turbo"

# ─── System prompt ────────────────────────────────────────────────────────────
today = date.today().isoformat()
system_prompt = (
    f"You are a friendly, professional assistant for More House School.\n"
    f"Today's date is {today}.\n"
    "Begin with 'Thank you for your question!' and end with 'Anything else I can help you with today?'.\n"
    "If you do not know the answer, say 'I'm sorry, I don't have that information.'\n"
    "Use British spelling."
)

# ─── Human takeover triggers ──────────────────────────────────────────────────
SENSITIVE_KEYWORDS = ["bullying", "emergency", "harassment", "safeguarding issue", "complaint"]
def needs_human_takeover(question, sim_score=None):
    now = datetime.now(pytz.timezone("Europe/London"))
    hour = now.hour
    scheduled = 9 <= hour < 17
    keyword_trigger = any(keyword in question.lower() for keyword in SENSITIVE_KEYWORDS)
    low_confidence = sim_score is not None and sim_score < 0.7
    return scheduled or keyword_trigger or low_confidence

# ─── Send email alert ─────────────────────────────────────────────────────────
def send_alert_email(question, session_id):
    if not all([SMTP_SERVER, SMTP_USER, SMTP_PASS, MODERATOR_EMAIL]):
        logger.warning("SMTP configuration missing; skipping email alert")
        return
    msg = MIMEText(
        f"A new query requires human review.\n\nQuestion: {question}\nSession ID: {session_id}\n"
        f"Please review at https://more-house-human.onrender.com/review"
    )
    msg["Subject"] = "More House Chatbot: Human Review Required"
    msg["From"] = SMTP_USER
    msg["To"] = MODERATOR_EMAIL
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info(f"Sent email alert for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to send email alert: {str(e)}")

def cosine_similarities(matrix, vector):
    dot = matrix @ vector
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)
    return dot / (norms + 1e-8)

def remove_bullets(text):
    return " ".join(
        line[2:].strip() if line.startswith("- ") else line.strip()
        for line in text.split("\n")
    )

def format_response(ans, is_human=False):
    footer = "Anything else I can help you with today?"
    ans = ans.replace(footer, "").strip()
    sents, paras, curr = ans.split(". "), [], []
    for s in sents:
        s = s.strip()
        if not s:
            continue
        curr.append(s.rstrip("."))
        if len(curr) >= 3 or s.endswith("?"):
            paras.append(". ".join(curr) + ".")
            curr = []
    if curr:
        paras.append(". ".join(curr) + ".")
    if not is_human and (not paras or not paras[0].startswith("Thank you for your question")):
        paras.insert(0, "Thank you for your question!")
    paras.append(footer)
    return "\n\n".join(paras)

@app.route("/", methods=["GET"])
def home():
    try:
        logger.info("Serving index.html")
        return render_template("index.html")
    except Exception as e:
        logger.error(f"Error serving index.html: {str(e)}")
        return jsonify(error="Failed to load homepage"), 500

@app.route("/ask", methods=["POST"])
@cross_origin()
def ask():
    try:
        data = request.get_json(force=True)
        question = data.get("question", "").strip()
        session_id = data.get("session_id", str(uuid.uuid4()))
        if not question:
            logger.warning("No question provided in /ask")
            return jsonify(error="No question provided"), 400

        key = question.lower().rstrip("?")

        # Check existing session
        conn = sqlite3.connect('/tmp/db/flag.db')
        c = conn.cursor()
        c.execute("SELECT status, human_response, bot_response FROM chat_sessions WHERE session_id = ?", (session_id,))
        session = c.fetchone()
        if session and session[0] == "human" and session[1]:
            conn.close()
            socketio.emit("human_response", {
                "session_id": session_id,
                "answer": format_response(session[1], is_human=True),
                "url": None,
                "link_label": None,
                "source": "human"
            }, room=session_id)
            logger.info(f"Returning human response for session {session_id}")
            return jsonify(
                answer=format_response(session[1], is_human=True),
                url=None,
                link_label=None,
                source="human",
                session_id=session_id
            ), 200
        elif session and session[0] == "pending":
            conn.close()
            socketio.emit("system_alert", {
                "session_id": session_id,
                "answer": "Your question has been flagged for human review. A member of our team will respond soon.",
                "url": None,
                "link_label": None,
                "source": "system"
            }, room=session_id)
            logger.info(f"Session {session_id} is pending human review")
            return jsonify(
                answer="Your question has been flagged for human review. A member of our team will respond soon.",
                url=None,
                link_label=None,
                source="system",
                session_id=session_id
            ), 200

        # 1) Exact static
        if key in STATIC_QAS:
            raw, url, label = STATIC_QAS[key]
            c.execute(
                "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
                (session_id, question, raw, "bot")
            )
            conn.commit()
            conn.close()
            socketio.emit("bot_response", {
                "session_id": session_id,
                "answer": format_response(remove_bullets(raw)),
                "url": url,
                "link_label": label,
                "source": "bot"
            }, room=session_id)
            logger.info(f"Answered with exact static QA for session {session_id}")
            return jsonify(
                answer=format_response(remove_bullets(raw)),
                url=url,
                link_label=label,
                source="bot",
                session_id=session_id
            ), 200

        # 2) Fuzzy static
        for sk, (raw, url, label) in STATIC_QAS.items():
            if fuzz.partial_ratio(sk, key) > 80:
                c.execute(
                    "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
                    (session_id, question, raw, "bot")
                )
                conn.commit()
                conn.close()
                socketio.emit("bot_response", {
                    "session_id": session_id,
                    "answer": format_response(remove_bullets(raw)),
                    "url": url,
                    "link_label": label,
                    "source": "bot"
                }, room=session_id)
                logger.info(f"Answered with fuzzy static QA for session {session_id}")
                return jsonify(
                    answer=format_response(remove_bullets(raw)),
                    url=url,
                    link_label=label,
                    source="bot",
                    session_id=session_id
                ), 200

        # 3) Welcome (custom — no “Thank you for your question!”)
        if question == "__welcome__":
            raw = (
                "Hi there! Ask me anything about More House School.\n\n"
                "We tailor our prospectus to your enquiry. For more details, visit below.\n\n"
                "Anything else I can help you with today?"
            )
            c.execute(
                "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
                (session_id, question, raw, "bot")
            )
            conn.commit()
            conn.close()
            socketio.emit("bot_response", {
                "session_id": session_id,
                "answer": remove_bullets(raw),
                "url": PAGE_LINKS["enquiry"],
                "link_label": "Enquire now",
                "source": "bot"
            }, room=session_id)
            logger.info(f"Sent welcome message for session {session_id}")
            return jsonify(
                answer=remove_bullets(raw),
                url=PAGE_LINKS["enquiry"],
                link_label="Enquire now",
                source="bot",
                session_id=session_id
            ), 200

        # 4) Guard “how many…”
        if key.startswith("how many"):
            raw = "I'm sorry, I don't have that information."
            c.execute(
                "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
                (session_id, question, raw, "bot")
            )
            conn.commit()
            conn.close()
            socketio.emit("bot_response", {
                "session_id": session_id,
                "answer": format_response(raw),
                "url": None,
                "link_label": None,
                "source": "bot"
            }, room=session_id)
            logger.info(f"Guarded 'how many' question for session {session_id}")
            return jsonify(
                answer=format_response(raw),
                url=None,
                link_label=None,
                source="bot",
                session_id=session_id
            ), 200

        # 5) Keyword → URL
        relevant_url = None
        for k, u in PAGE_LINKS.items():
            if k in key or any(
                fuzz.partial_ratio(k, w) > 80 for w in key.split() if len(w) > 3
            ):
                relevant_url = u
                break

        # 6) RAG fallback
        emb = openai.embeddings.create(model=EMB_MODEL, input=question)
        q_vec = np.array(emb.data[0].embedding, dtype="float32")
        sims = cosine_similarities(embeddings, q_vec)
        top_idx = sims.argmax()
        top_sim = sims[top_idx]
        contexts = [metadata[i]["text"] for i in sims.argsort()[-20:][::-1]]
        prompt = "Use these passages:\n\n" + "\n---\n".join(contexts)
        prompt += f"\n\nQuestion: {question}\nAnswer:"
        chat = openai.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        raw = chat.choices[0].message.content

        # Check for human takeover
        if needs_human_takeover(question, top_sim):
            c.execute(
                "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
                (session_id, question, raw, "pending")
            )
            conn.commit()
            conn.close()
            send_alert_email(question, session_id)
            socketio.emit("system_alert", {
                "session_id": session_id,
                "answer": "Your question has been flagged for human review. A member of our team will respond soon.",
                "url": None,
                "link_label": None,
                "source": "system"
            }, room=session_id)
            logger.info(f"Flagged for human review: session {session_id}")
            return jsonify(
                answer="Your question has been flagged for human review. A member of our team will respond soon.",
                url=None,
                link_label=None,
                source="system",
                session_id=session_id
            ), 200

        # Store bot response
        c.execute(
            "INSERT OR REPLACE INTO chat_sessions (session_id, question, bot_response, status) VALUES (?, ?, ?, ?)",
            (session_id, question, raw, "bot")
        )
        conn.commit()
        conn.close()

        answer = format_response(remove_bullets(raw))
        if not relevant_url and top_idx:
            relevant_url = metadata[top_idx].get("url")
        link_label = URL_LABELS.get(relevant_url)

        socketio.emit("bot_response", {
            "session_id": session_id,
            "answer": answer,
            "url": relevant_url,
            "link_label": link_label,
            "source": "bot"
        }, room=session_id)
        logger.info(f"Answered with RAG for session {session_id}")
        return jsonify(
            answer=answer,
            url=relevant_url,
            link_label=link_label,
            source="bot",
            session_id=session_id
        ), 200

    except Exception as e:
        logger.error(f"Error in /ask: {str(e)}")
        traceback.print_exc()
        return jsonify(error=str(e)), 500

@app.route("/status", methods=["POST"])
@cross_origin()
def status():
    try:
        data = request.get_json(force=True)
        session_id = data.get("session_id")
        if not session_id:
            logger.warning("No session_id provided in /status")
            return jsonify(error="No session_id provided"), 400
        conn = sqlite3.connect('/tmp/db/flag.db')
        c = conn.cursor()
        c.execute("SELECT status, human_response, bot_response FROM chat_sessions WHERE session_id = ?", (session_id,))
        session = c.fetchone()
        conn.close()
        if not session:
            logger.warning(f"Session {session_id} not found")
            return jsonify(error="Session not found"), 404
        status, human_response, bot_response = session
        if status == "human" and human_response:
            socketio.emit("human_response", {
                "session_id": session_id,
                "answer": format_response(human_response, is_human=True),
                "url": None,
                "link_label": None,
                "source": "human"
            }, room=session_id)
            logger.info(f"Returned human response for session {session_id}")
            return jsonify(
                answer=format_response(human_response, is_human=True),
                url=None,
                link_label=None,
                source="human",
                session_id=session_id
            ), 200
        elif status == "pending":
            socketio.emit("system_alert", {
                "session_id": session_id,
                "answer": "Your question is still under human review. Please check back soon.",
                "url": None,
                "link_label": None,
                "source": "system"
            }, room=session_id)
            logger.info(f"Session {session_id} is pending review")
            return jsonify(
                answer="Your question is still under human review. Please check back soon.",
                url=None,
                link_label=None,
                source="system",
                session_id=session_id
            ), 200
        else:
            logger.info(f"Returned bot response for session {session_id}")
            return jsonify(
                answer=format_response(bot_response),
                url=None,
                link_label=None,
                source="bot",
                session_id=session_id
            ), 200
    except Exception as e:
        logger.error(f"Error in /status: {str(e)}")
        traceback.print_exc()
        return jsonify(error=str(e)), 500

@app.route("/review", methods=["GET", "POST"])
def review():
    try:
        conn = sqlite3.connect('/tmp/db/flag.db')
        c = conn.cursor()
        if request.method == "GET":
            c.execute("SELECT session_id, question, status, human_response FROM chat_sessions WHERE status = 'pending'")
            sessions = c.fetchall()
            conn.close()
            logger.info("Served review.html with pending sessions")
            return render_template("review.html", sessions=sessions)
        else:
            data = request.form
            session_id = data.get("session_id")
            human_response = data.get("human_response")
            if not session_id or not human_response:
                conn.close()
                logger.warning("Missing session_id or human_response in /review POST")
                return jsonify(error="Missing session_id or human_response"), 400
            c.execute(
                "UPDATE chat_sessions SET human_response = ?, status = ? WHERE session_id = ?",
                (human_response, "human", session_id)
            )
            conn.commit()
            conn.close()
            socketio.emit("human_response", {
                "session_id": session_id,
                "answer": format_response(human_response, is_human=True),
                "url": None,
                "link_label": None,
                "source": "human"
            }, room=session_id)
            logger.info(f"Submitted human response for session {session_id}")
            return jsonify(success="Response submitted"), 200
    except Exception as e:
        logger.error(f"Error in /review: {str(e)}")
        traceback.print_exc()
        return jsonify(error=str(e)), 500

@socketio.on("connect")
def handle_connect():
    logger.info("Client connected")

@socketio.on("join")
def handle_join(data):
    session_id = data.get("session_id")
    if session_id:
        logger.info(f"Client joined room: {session_id}")
        emit("joined", {"session_id": session_id}, room=session_id)

if __name__ == "__main__":
    logger.info("Starting Flask-SocketIO server")
    socketio.run(app, host="0.0.0.0", port=5000)
