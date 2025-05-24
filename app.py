#!/usr/bin/env python3
import os
import pickle
import traceback
from datetime import date

import numpy as np
import openai
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, join_room, emit
from dotenv import load_dotenv
from fuzzywuzzy import fuzz

# ─── Initialise ──────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

# ─── Flask & SocketIO setup ───────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "CHANGE_ME")
CORS(app, resources={r"/ask": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# track which sessions are in human-override
override_states = {}  # session_id → bool

# ─── Paste your existing dictionaries here UNCHANGED ──────────────────────────
PAGE_LINKS = {
    # Home
    "home":               "https://www.morehouse.org.uk/",
    "homepage":           "https://www.morehouse.org.uk/",
    "main page":          "https://www.morehouse.org.uk/",

    # Admissions & enquiry / prospectus
    "open events":        "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open morning":       "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open day":           "https://www.morehouse.org.uk/admissions/our-open-events/",
    "open evening":       "https://www.morehouse.org.uk/admissions/our-open-events/",
    "admissions":         "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "enquiry":            "https://www.morehouse.org.uk/admissions/enquiry/",
    "enquire":            "https://www.morehouse.org.uk/admissions/enquiry/",
    "inquire":            "https://www.morehouse.org.uk/admissions/enquiry/",
    "prospectus":         "https://www.morehouse.org.uk/admissions/enquiry/",

    # Fees & costs
    "fees":               "https://www.morehouse.org.uk/admissions/fees/",
    "cost":               "https://www.morehouse.org.uk/admissions/fees/",
    "costs":              "https://www.morehouse.org.uk/admissions/fees/",
    "price":              "https://www.morehouse.org.uk/admissions/fees/",
    "tuition":            "https://www.morehouse.org.uk/admissions/fees/",
    "charges":            "https://www.morehouse.org.uk/admissions/fees/",

    # Scholarships & bursaries
    "scholarships":       "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "scholarship":        "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "scholarships and bursaries": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursaries":          "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursary":            "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",
    "bursary scholarships": "https://www.morehouse.org.uk/admissions/scholarships-and-bursaries/",

    # Registration & deadlines
    "registration deadline": "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "registration":        "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "register":            "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "registering":         "https://www.morehouse.org.uk/admissions/joining-more-house/",
    "deadline":            "https://www.morehouse.org.uk/admissions/joining-more-house/",

    # Term dates & calendar
    "term dates":         "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "terms":              "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "calendar":           "https://www.morehouse.org.uk/news-and-calendar/calendar/",
    "school calendar":    "https://www.morehouse.org.uk/news-and-calendar/calendar/",
    "half term":          "https://www.morehouse.org.uk/news-and-calendar/term-dates/",
    "holiday dates":      "https://www.morehouse.org.uk/news-and-calendar/term-dates/",

    # Uniform
    "uniform":            "https://www.morehouse.org.uk/information/school-uniform/",
    "dress code":         "https://www.morehouse.org.uk/information/school-uniform/",

    # Contact
    "contact":            "https://www.morehouse.org.uk/contact/",
    "contact us":         "https://www.morehouse.org.uk/contact/",
    "email":              "https://www.morehouse.org.uk/contact/",
    "phone":              "https://www.morehouse.org.uk/contact/",
    "telephone":          "https://www.morehouse.org.uk/contact/",

    # Ethos & history
    "our ethos":          "https://www.morehouse.org.uk/our-school/our-ethos/",
    "ethos":              "https://www.morehouse.org.uk/our-school/our-ethos/",
    "history":            "https://www.morehouse.org.uk/our-school/history/",
    "our story":          "https://www.morehouse.org.uk/our-school/more-house-stories/",

    # Staff & governors
    "staff":              "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "governors":          "https://www.morehouse.org.uk/information/our-staff-and-governors/",
    "staff and governors": "https://www.morehouse.org.uk/information/our-staff-and-governors/",

    # Head of School
    "head of school":     "https://www.morehouse.org.uk/our-school/meet-the-head/",
    "meet the head":      "https://www.morehouse.org.uk/our-school/meet-the-head/",

    # Facilities & info
    "lettings":           "https://www.morehouse.org.uk/information/lettings/",
    "venues":             "https://www.morehouse.org.uk/information/lettings/",
    "school lunches":     "https://www.morehouse.org.uk/information/school-lunches/",
    "lunch":              "https://www.morehouse.org.uk/information/school-lunches/",
    "lunches":            "https://www.morehouse.org.uk/information/school-lunches/",
    "meals":              "https://www.morehouse.org.uk/information/school-lunches/",

    # Pastoral Care
    "pastoral care":      "https://www.morehouse.org.uk/our-school/pastoral-care/",

    # Safeguarding & policies
    "safeguarding":       "https://www.morehouse.org.uk/information/safeguarding/",
    "safety":             "https://www.morehouse.org.uk/information/safeguarding/",
    "inspection reports": "https://www.morehouse.org.uk/information/inspection-reports/",
    "inspection":         "https://www.morehouse.org.uk/information/inspection-reports/",
    "reports":            "https://www.morehouse.org.uk/information/inspection-reports/",
    "school policies":    "https://www.morehouse.org.uk/information/school-policies/",
    "policy":             "https://www.morehouse.org.uk/information/school-policies/",
    "policies":           "https://www.morehouse.org.uk/information/school-policies/",

    # Learning & curriculum
    "pre-senior":         "https://www.morehouse.org.uk/pre-senior/",
    "academic life":      "https://www.morehouse.org.uk/learning/academic-life/",
    "academics":          "https://www.morehouse.org.uk/learning/academic-life/",
    "subjects":           "https://www.morehouse.org.uk/learning/subjects/",
    "sixth form":         "https://www.morehouse.org.uk/learning/sixth-form/",
    "creative suite":     "https://www.morehouse.org.uk/learning/our-creative-suite/",
    "creative":           "https://www.morehouse.org.uk/learning/our-creative-suite/",
    "learning support":   "https://www.morehouse.org.uk/learning/learning-support/",
    "support":            "https://www.morehouse.org.uk/learning/learning-support/",
    "results and destinations": "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "destinations":       "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "results":            "https://www.morehouse.org.uk/learning/results-and-destinations/",
    "be more":            "https://www.morehouse.org.uk/learning/be-more/",

    # Houses
    "houses":             "https://www.morehouse.org.uk/our-school/houses/",
    
    # Beyond the classroom
    "co-curricular":             "https://www.morehouse.org.uk/beyond-the-classroom/co-curricular-programme/",
    "sport":                     "https://www.morehouse.org.uk/beyond-the-classroom/sport/",
    "faith life":                "https://www.morehouse.org.uk/beyond-the-classroom/faith-life/",

    # Academic results
    "results and destinations":  "https://www.morehouse.org.uk/learning/results-and-destinations/",

    # Inspection & policies
    "inspection reports":        "https://www.morehouse.org.uk/information/inspection-reports/",
    "school policies":           "https://www.morehouse.org.uk/information/school-policies/",
        
}

# ─── Human labels for fallback links ────────────────────────────────────────
URL_LABELS = {
    # PAGE_LINKS entries
    PAGE_LINKS["enquiry"]            : "More about Enquiries",
    PAGE_LINKS["fees"]               : "More about Fees",
    PAGE_LINKS["registration deadline"]: "More about Deadlines",
    PAGE_LINKS["term dates"]         : "More about Term Dates",
    PAGE_LINKS["open events"]        : "More about Open Events",
    PAGE_LINKS["uniform"]            : "More about Uniform",
    PAGE_LINKS["school lunches"]     : "More about Lunch Menu",
    PAGE_LINKS["academic life"]      : "More about Academic Life",
    PAGE_LINKS["subjects"]           : "More about Subjects",
    PAGE_LINKS["pre-senior"]         : "More about Pre-Senior",
    PAGE_LINKS["houses"]             : "More about Houses",
    PAGE_LINKS["co-curricular"]      : "More about Co-curricular",
    PAGE_LINKS["sport"]              : "More about Sport",
    PAGE_LINKS["faith life"]         : "More about Faith Life",
    PAGE_LINKS["results and destinations"]: "More about Results",
    PAGE_LINKS["inspection reports"] : "More about Inspection Reports",
    PAGE_LINKS["school policies"]    : "More about Policies",
    PAGE_LINKS["scholarships"]       : "More about Scholarships",
    PAGE_LINKS["contact"]            : "More about Contact",
    PAGE_LINKS["sixth form"]         : "More about Sixth Form",
    PAGE_LINKS["pastoral care"]      : "More about Pastoral Care",
    PAGE_LINKS["safeguarding"]       : "More about Safeguarding",
    PAGE_LINKS["head of school"]     : "Meet the Head",
    PAGE_LINKS["lettings"]           : "More about Facilities",
    PAGE_LINKS["learning support"]   : "More about Learning Support",
    PAGE_LINKS["ethos"]              : "More about Our Ethos",
    PAGE_LINKS["admissions"]         : "More about Admissions",
    PAGE_LINKS["prospectus"]         : "More about Prospectus",
    PAGE_LINKS["staff"]              : "Meet Our Staff",

    # Explicit URL
    "https://www.morehouse.org.uk/information/school-policies/": "More about Policies",

}


STATIC_QAS = {
    # 1) Enquiry / Prospectus
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

    # 2) School fees
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

    # 3) Uniform
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

    # 4) Dietary requirements / lunch menu
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

    # 5) Term dates
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

    # 6) Registration deadlines
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

    # 7) Open events
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

    # 8) Bursaries & scholarships
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

    # 9) Sixth Form
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

    # 10) Contact
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

    # 11) Head of School
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

    # 12) Pastoral Care
    "how do you support students pastoral care": (
        "We offer dedicated pastoral teams, regular check-ins and specialised programmes to support every student's wellbeing. See our Pastoral Care page for details.",
        PAGE_LINKS["pastoral care"],
        "More about Pastoral Care"
    ),

    # 13) Safeguarding
    "what are your safeguarding policies": (
        "Our safeguarding policies ensure every pupil's safety both on and off campus. For full policy documents, visit our Safeguarding page.",
        PAGE_LINKS["safeguarding"],
        "View Safeguarding Policies"
    ),

    # 14) Academic Life
    "what is academic life like": (
        "Academic Life at More House blends rigorous coursework with personalised support. Explore our approach on the Academic Life page.",
        PAGE_LINKS["academic life"],
        "More about Academic Life"
    ),

    # 15) Subjects
    "which subjects do you offer": (
        "We offer a wide range of subjects from STEM to humanities and creative arts. See the full list on our Subjects page.",
        PAGE_LINKS["subjects"],
        "View Subjects Offered"
    ),

    # 16) Pre-Senior
    "tell me about pre-senior": (
        "Pre-Senior (Years 5–6) prepares pupils with a broad curriculum and pastoral support. Learn more on our Pre-Senior page.",
        PAGE_LINKS["pre-senior"],
        "More about Pre-Senior"
    ),

    # 17) Houses
    "how does your house system work": (
        "Our house system fosters camaraderie and healthy competition across four houses. Find details on our Houses page.",
        PAGE_LINKS["houses"],
        "More about Houses"
    ),

    # 18) Co-curricular
    "what extracurricular activities do you offer": (
        "We run sport, music, drama, Duke of Edinburgh and more. Discover all options on our Co-curricular Programme page.",
        PAGE_LINKS["co-curricular"],
        "View Co-curricular Activities"
    ),

    # 19) Sport
    "what sports do you offer": (
        "We offer netball, hockey, football, rowing, athletics and more. Details are on our Sport page.",
        PAGE_LINKS["sport"],
        "View Sports Offered"
    ),

    # 20) Faith Life
    "tell me about faith life": (
        "Faith Life includes regular reflection sessions and chaplaincy support. Visit our Faith Life page to learn more.",
        PAGE_LINKS["faith life"],
        "More about Faith Life"
    ),

    # 21) Results & Destinations
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

    # 22) Inspection Reports
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

    # 23) Exams / exam policy
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

    # 24) Teaching staff
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

    # 25) University guidance
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

    # 26) Transport & Bus
    "transport": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,  # no live URL yet
        "View Bus Routes"  # label, in case you add a URL later
    ),
    "bus service": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,  # no live URL yet
        "View Bus Routes"  # label, in case you add a URL later
    ),
    "bus routes": (
        "We run dedicated school buses from X, Y and Z. See timetables and pick-up points here:",
        None,  # no live URL yet
        "View Bus Routes"  # label, in case you add a URL later
    ),

    # 27) After-school Clubs
    "after school clubs": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,  # no live URL yet
        "View After-School Clubs"  # label, in case you add a URL later
    ),
    "clubs": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,  # no live URL yet
        "View After-School Clubs"  # label, in case you add a URL later
    ),
    "after school": (
        "We offer chess, coding, drama, netball and more in our After-School Clubs. Full schedule here:",
        None,  # no live URL yet
        "View After-School Clubs"  # label, in case you add a URL later
    ),

    # 28) Parents’ Evenings
    "parents evening": (
        "Our termly Parents’ Evenings let you meet teachers and review progress. Dates and booking info here:",
        None,  # no live URL yet
        "Book Parents’ Evening"  # label, in case you add a URL later
    ),
    "parent evenings": (
        "Our termly Parents’ Evenings let you meet teachers and review progress. Dates and booking info here:",
        None,  # no live URL yet
        "Book Parents’ Evening"  # label, in case you add a URL later
    ),

    # 29) PTA / Friends of School
    "pta": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,  # no live URL yet
        "More about PTA"  # label, in case you add a URL later
    ),
    "friends of school": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,  # no live URL yet
        "More about PTA"  # label, in case you add a URL later
    ),
    "parents association": (
        "Our PTA organises events and fundraising—everyone’s welcome. Learn more here:",
        None,  # no live URL yet
        "More about PTA"  # label, in case you add a URL later
    ),

    # 30) Mental Health & Wellbeing
    "mental health": (
        "We have an on-site counsellor and weekly wellbeing workshops. Details here:",
        None,  # no live URL yet
        "More about Wellbeing"  # label, in case you add a URL later
    ),
    "wellbeing support": (
        "We have an on-site counsellor and weekly wellbeing workshops. Details here:",
        None,  # no live URL yet
        "More about Wellbeing"  # label, in case you add a URL later
    ),

    # 31) SEN / Learning support
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

    # 32) e-Safety / Online safety
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

    # 33) Alumni / Old Girls
    "alumni": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,  # no live URL yet
        "Join Our Alumnae"  # label, in case you add a URL later
    ),
    "old girls": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,  # no live URL yet
        "Join Our Alumnae"  # label, in case you add a URL later
    ),
    "past pupils": (
        "Our Alumnae network offers mentorship and events. Join here:",
        None,  # no live URL yet
        "Join Our Alumnae"  # label, in case you add a URL later
    ),

    # 34) Faith & Religion
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

    # 35) Education
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

    # 36) Admissions process
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

    # 37) Entry requirements
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

    # 38) Virtual tour
    "virtual tour": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,  # no live URL yet
        "Take Virtual Tour"  # label, in case you add a URL later
    ),
    "tour": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,  # no live URL yet
        "Take Virtual Tour"  # label, in case you add a URL later
    ),
    "visit us online": (
        "Take our online Virtual Tour to explore More House’s facilities and campus from anywhere in the world. Access the 360° walkthrough on our website.",
        None,  # no live URL yet
        "Take Virtual Tour"  # label, in case you add a URL later
    ),

    # 39) Facilities
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

    # 40) Drama & theatre
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

    # 41) Robotics & coding
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

    # 42) School motto / mission
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

    # 43) INSET days / staff training
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

    # 44) Health & safety
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

    # 45) Accessibility
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

    # 46) SENCO / SEND
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

    # 47) Application deadlines
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

    # 48) Values
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

    # 49) Alumni events
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

    # 50) Parent portal / ParentPay
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

    # 51) Jobs & Vacancies
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

    # 52) Behaviour & Discipline
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

    # 53) Uniform Supplier
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

    # 54) Lost Property
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

    # 55) Wraparound Care
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

    # 56) Exclusions & Sanctions
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

    # 57) SEND & EHCP
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

    # 58) Health & Wellbeing
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

    # 59) IT & Wi-Fi
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

    # 60) Health & Covid policies
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

    # 61) School policies
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

    # 62) Music department
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
with open("embeddings.pkl", "rb") as f:
    embeddings = np.stack(pickle.load(f), axis=0)
with open("metadata.pkl", "rb") as f:
    metadata = pickle.load(f)

EMB_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-3.5-turbo"

today = date.today().isoformat()
system_prompt = (
    f"You are a friendly, professional assistant for More House School.\n"
    f"Today's date is {today}.\n"
    "Begin with 'Thank you for your question!' and end with "
    "'Anything else I can help you with today?'.\n"
    "If you do not know the answer, say 'I'm sorry, I don't have that information.'\n"
    "Use British spelling."
)

# ─── Utility functions ──────────────────────────────────────────────────────
def cosine_similarities(matrix, vector):
    dot = matrix @ vector
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)
    return dot / (norms + 1e-8)

def remove_bullets(text):
    return " ".join(
        line[2:].strip() if line.startswith("- ") else line.strip()
        for line in text.split("\n")
    )

def format_response(ans):
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
    if not paras or not paras[0].startswith("Thank you for your question"):
        paras.insert(0, "Thank you for your question!")
    paras.append(footer)
    return "\n\n".join(paras)

# ─── HTTP endpoint for automated “ask” ──────────────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "PEN.ai is running."

@app.route("/ask", methods=["POST"])
@cross_origin()
def ask():
    try:
        data = request.get_json(force=True)
        question = data.get("question", "").strip()
        if not question:
            return jsonify(error="No question provided"), 400

        key = question.lower().rstrip("?")

        # 1) Exact static
        if key in STATIC_QAS:
            raw, url, label = STATIC_QAS[key]
            return jsonify(
                answer=format_response(remove_bullets(raw)),
                url=url,
                link_label=label
            ), 200

        # 2) Fuzzy static
        for sk, (raw, url, label) in STATIC_QAS.items():
            if fuzz.partial_ratio(sk, key) > 80:
                return jsonify(
                    answer=format_response(remove_bullets(raw)),
                    url=url,
                    link_label=label
                ), 200

        # 3) Welcome
        if question == "__welcome__":
            raw = (
                "Hi there! Ask me anything about More House School.\n\n"
                "We tailor our prospectus to your enquiry. For more details, visit below.\n\n"
                "Anything else I can help you with today?"
            )
            return jsonify(
                answer=remove_bullets(raw),
                url=PAGE_LINKS["enquiry"],
                link_label="Enquire now"
            ), 200

        # 4) Guard “how many…”
        if key.startswith("how many"):
            return jsonify(
                answer=format_response("I'm sorry, I don't have that information."),
                url=None
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
        top_idxs = sims.argsort()[-20:][::-1]
        contexts = [metadata[i]["text"] for i in top_idxs]
        prompt = "Use these passages:\n\n" + "\n---\n".join(contexts)
        prompt += f"\n\nQuestion: {question}\nAnswer:"
        chat = openai.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = chat.choices[0].message.content
        answer = format_response(remove_bullets(raw))

        # 7) Fallback URL + human label
        if not relevant_url and top_idxs.size:
            relevant_url = metadata[top_idxs[0]].get("url")
        link_label = URL_LABELS.get(relevant_url)

        return jsonify(
            answer=answer,
            url=relevant_url,
            link_label=link_label
        ), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify(error=str(e)), 500

# ─── SocketIO events for live chat & human takeover ─────────────────────────
@socketio.on("join")
def on_join(data):
    sid  = data["sessionId"]
    role = data.get("role", "user")
    join_room(f"{role}_{sid}")

@socketio.on("client_message")
def handle_client_message(data):
    sid     = data["sessionId"]
    message = data["message"]
    if override_states.get(sid):
        # send user text to agent instead of bot
        emit("incoming_message", {"message": message}, room=f"agent_{sid}")
    else:
        # bot handles it
        resp = ask_via_function(message)
        emit("bot_response", {"message": resp["answer"]}, room=f"user_{sid}")

@socketio.on("takeover")
def handle_takeover(data):
    sid = data["sessionId"]
    override_states[sid] = True
    emit("system_message",
         {"message": "⚠️ Human agent has taken over."},
         room=f"user_{sid}")
    emit("system_message",
         {"message": "You are now in control of this chat."},
         room=f"agent_{sid}")

@socketio.on("agent_message")
def handle_agent_message(data):
    sid  = data["sessionId"]
    text = data["message"]
    emit("bot_response", {"message": text}, room=f"user_{sid}")

@socketio.on("release")
def handle_release(data):
    sid = data["sessionId"]
    override_states[sid] = False
    emit("system_message",
         {"message": "🤖 Chatbot has resumed control."},
         room=f"user_{sid}")
    emit("system_message",
         {"message": "You have released this chat."},
         room=f"agent_{sid}")

# ─── Helper to invoke ask() internally ───────────────────────────────────────
def ask_via_function(question):
    with app.test_request_context(json={"question": question}):
        resp = ask()
        return resp.get_json()

# ─── Serve the agent dashboard ────────────────────────────────────────────────
@app.route("/agent")
def agent_dashboard():
    # assumes you put agent.html in your app’s /static folder
    return app.send_static_file("agent.html")


# ─── Run the app ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # In production, you may switch to `eventlet` or `gevent` for better concurrency
    socketio.run(app, host="0.0.0.0", port=5000)
