"""
One-time script to populate all Google Classroom assignments into the database.
Parses the structured classroom export data and inserts into the assignments table.
"""
import sqlite3
import uuid
import json
import re
from datetime import datetime

DB_PATH = "sais.db"
# Auto-detect user ID from the database (first active user, or fallback)
_DEFAULT_USER_ID = "c28d0ecadab74b12b7f32b95652d27a7"

def _get_user_id():
    """Get the demo user's ID from the database, or fall back to default."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = 'demo@sais.edu'")
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return _DEFAULT_USER_ID

USER_ID = _get_user_id()

# ── Raw classroom data split by section ──────────────────────────────

ASSIGNED_DUE = [
    ("Practical 4: Min_Max Algorithm", "SE_CE_C_January_May_2026", "2/23/2026", "2026-02-28"),
]

ASSIGNED_NO_DUE = [
    ("lab5", "DBMS SE C 2025-26", "2/23/2026", None),
    ("Lab4", "DBMS SE C 2025-26", "2/23/2026", None),
    ("Experiment No 3", "FSD SECE-C A & B Batch", "2/20/2026", None),
    ("Assignment 1: Affectuation principle case study", "CE C", "2/18/2026", None),
    ("Experiment 2", "OS-SE-B and C -EVEN-2025-2026", "2/18/2026", None),
    ("Experiment 1", "OS-SE-B and C -EVEN-2025-2026", "2/10/2026", None),
    ("Activity 2", "SE_CE_C_January_May_2026", "1/26/2026", None),
    ("Index", "SE Comps C", "11/21/2025", None),
    ("COA TH ISE2 Quiz 2025-26", "COA", "11/20/2025", None),
    ("Sensors and Actuators Course Exit Survey", "Sensors and Actuators IoT Double Minors 25-26", "11/12/2025", None),
    ("Tutorial 7", "Sensors and Actuators IoT Double Minors 25-26", "10/15/2025", None),
    ("Tutorial 6", "Sensors and Actuators IoT Double Minors 25-26", "10/15/2025", None),
    ("Tutorial 2", "SE Comps C", "9/28/2025", None),
    ("Tutorial 1", "SE Comps C", "9/28/2025", None),
    ("Tutorial 3 Quiz", "Sensors and Actuators IoT Double Minors 25-26", "8/6/2025", None),
    ("Tutorial 2 Quiz", "Sensors and Actuators IoT Double Minors 25-26", "7/23/2025", None),
    ("Tutorial 1 Quiz", "Sensors and Actuators IoT Double Minors 25-26", "7/16/2025", None),
    ("Panel discussion", "FE CE C AOC", "4/24/2025", None),
    ("Letter writing", "FE CE C AOC", "4/1/2025", None),
    ("Writeups Tutorial 5 Beta and Gamma function", "FE COMP C 2024-2025", "3/21/2025", None),
    ("Aptitude test", "FE CE C AOC", "3/17/2025", None),
    ("ecse quiz fe c flexbox", "ECSE computer FE C", "2/21/2025", None),
    ("css quiz", "ECSE computer FE C", "2/20/2025", None),
    ("Module 2: Section 2.1", "CE_C_IET2025", "2/17/2025", None),
    ("Role play report", "FE CE C AOC", "2/17/2025", None),
    ("ecse c html quiz", "ECSE computer FE C", "2/13/2025", None),
    ("ecse c html quiz (2)", "ECSE computer FE C", "2/13/2025", None),
    ("ISE 1 Listening skills-2", "FE CE C AOC", "2/10/2025", None),
    ("ISE 1 Listening skills 1", "FE CE C AOC", "2/10/2025", None),
    ("Communication quiz ISE 1", "FE CE C AOC", "2/3/2025", None),
    ("ISE1_2", "FEComp_DIVC", "11/8/2024", None),
    ("Writing Skill - Sanskrit", "9th A", "4/12/2021", None),
    ("Writing Skill - Entire Hindi", "9th A", "4/12/2021", None),
    ("Second Term Evaluation - Sanskrit", "9th A", "4/12/2021", None),
    ("Second Term Evaluation - Entire Hindi", "9th A", "4/12/2021", None),
    ("9th Geography Ch.12 Tourism", "9th A", "3/16/2021", None),
    ("PPT on Python", "9th A", "3/5/2021", None),
    ("Microsoft Word Assessment", "9th A", "2/9/2021", None),
    ("Std - 9th - Sanskrit - 2 UT", "9th A", "2/1/2021", None),
    ("\u092e\u0930\u093e\u0920\u0940 Activity 22.1.2021 \u092e\u0930\u093e\u0920\u0940 \u0928\u093f\u092c\u0902\u0927 \u0932\u093f\u0939\u093e", "9th A", "1/22/2021", None),
    ("Basic Excel Assignment", "9th A", "1/21/2021", None),
    ("To Upload Project file", "9th A", "1/6/2021", None),
    ("Sanskrit - Std - 9th -1st Term Evaluation", "9th A", "10/30/2020", None),
    ("Moral Science evaluation paper - 8.20 am to 8.35 am", "9th A", "10/27/2020", None),
    ("Hindi Revision", "9th A", "10/23/2020", None),
    ("Hindi Entire 1st Semester Assignment Writing Skill 3/10/2020", "9th A", "10/2/2020", None),
    ("Learning assignment - Essay & Agenda writing", "9th A", "10/1/2020", None),
    ("Sanskrit Competitions", "9th A", "9/12/2020", None),
    ("1st Online Unit Test Hindi Entire", "9th A", "9/2/2020", None),
    ("9th std -Sanskrit - Unit Test", "9th A", "9/2/2020", None),
    ("\u0915\u0915\u094d\u0937\u093e: \u096f\u0935\u0940\u0902 \u0935\u093f\u0937\u092f: \u0939\u093f\u0902\u0926\u0940 (\u0938\u0902\u092f\u0941\u0915\u094d\u0924) \u092a\u094d\u0930\u0925\u092e \u0918\u091f\u0915 \u092a\u0930\u0940\u0915\u094d\u0937\u093e 2020-21", "9th A", "9/2/2020", None),
    ("Scout whistle and flag signal", "9th A", "8/8/2020", None),
]

SUBMITTED = [
    ("Experiment No 2", "FSD SECE-C A & B Batch", "2/11/2026", None),
    ("EXPT2", "DBMS SE C 2025-26", "2/4/2026", None),
    ("EXP1", "DBMS SE C 2025-26", "2/4/2026", None),
    ("Experiment No 1", "FSD SECE-C A & B Batch", "2/2/2026", None),
    ("Activity 3 - Home Assignment", "SE_CE_C_January_May_2026", "1/30/2026", "2026-02-01"),
    ("Experiment 4", "OS-SE-B and C -EVEN-2025-2026", "1/29/2026", "2027-01-08"),
    ("Activity 1", "SE_CE_C_January_May_2026", "1/18/2026", None),
    ("COA Theory ISE2 Presentations", "COA", "11/18/2025", None),
    ("Miniproject", "Data Structure", "11/13/2025", None),
    ("Experiment 10", "OOPJava_SECE_C_25_26", "11/12/2025", "2025-11-15"),
    ("EXP-10-DFS & BFS", "Data Structure", "11/12/2025", "2025-11-21"),
    ("Tutorial 6", "SE Comps C", "11/11/2025", "2025-11-18"),
    ("Tutorial 5", "SE Comps C", "11/11/2025", "2025-11-18"),
    ("Experiment 9", "OOPJava_SECE_C_25_26", "11/7/2025", "2025-11-14"),
    ("Competitive DS Coding (2-Linear & 2-Non linear Problems)", "Data Structure", "11/6/2025", None),
    ("COA Practical ISE2", "COA", "11/6/2025", None),
    ("ISE-2_Assignment- From Lesson 7 and 8", "Kannada MIL-(2025-26)", "11/3/2025", None),
    ("Experiment 8: JavaFX", "OOPJava_SECE_C_25_26", "10/31/2025", "2025-11-14"),
    ("PRACTICAL ISE", "Data Structure", "10/29/2025", None),
    ("Expt 11: Blinking display", "COA", "10/29/2025", None),
    ("Exp-9-Binary Search Trees", "Data Structure", "10/17/2025", "2025-10-31"),
    ("ISE-2_Assignment No-3 (From Lesson 4)", "Kannada MIL-(2025-26)", "10/6/2025", None),
    ("ISE-2_Assignment -2 (from Lesson-3)", "Kannada MIL-(2025-26)", "10/6/2025", None),
    ("Expt 10: Restoring and Non-restoring Division Algorithm", "COA", "10/2/2025", None),
    ("Expt 9: Booth's Multiplication Algorithm", "COA", "10/2/2025", None),
    ("ISE 2- Certificate", "HVPE_CE_C_AB_25", "9/26/2025", "2025-10-10"),
    ("Experiment 7- Multithreading", "OOPJava_SECE_C_25_26", "9/26/2025", "2025-10-03"),
    ("EXP-8-Polynomial Add/Sub", "Data Structure", "9/24/2025", "2025-10-01"),
    ("EXP-7-Doubly Link List", "Data Structure", "9/24/2025", "2025-10-01"),
    ("Circular Link List -EXP-6", "Data Structure", "9/24/2025", "2025-10-01"),
    ("Experiment 6_Exception Handling", "OOPJava_SECE_C_25_26", "9/19/2025", "2025-09-27"),
    ("Assignment 1", "FPTI_2025", "9/18/2025", "2025-09-25"),
    ("COA Theory ISE1 Video links", "COA", "9/16/2025", None),
    ("Expt 8: Password verification", "COA", "9/4/2025", None),
    ("ISE-1 Assignments", "Kannada MIL-(2025-26)", "9/1/2025", None),
    ("EXP-5-Singly Linked List", "Data Structure", "8/28/2025", "2025-09-12"),
    ("EXP-4-Circular Queue", "Data Structure", "8/28/2025", "2025-09-05"),
    ("COA Practical ISE1", "COA", "8/21/2025", None),
    ("Expt 7: 3x3 matrix addition", "COA", "8/20/2025", None),
    ("Link List-Reverse & Display", "Data Structure", "8/19/2025", None),
    ("SPLIT LINK LIST", "Data Structure", "8/19/2025", None),
    ("COPY LINK LIST", "Data Structure", "8/19/2025", None),
    ("ISE 1-Certificate", "HVPE_CE_C_AB_25", "8/17/2025", "2025-08-20"),
    ("Experiment 5-Strings", "OOPJava_SECE_C_25_26", "8/14/2025", "2025-09-02"),
    ("Exp-3-Linear Queue", "Data Structure", "8/13/2025", "2025-08-22"),
    ("Expt 6: Block transfer of data", "COA", "8/11/2025", "2025-08-20"),
    ("Expt 5: Odd and Even numbers", "COA", "8/11/2025", "2025-08-18"),
    ("Experiment No - 4", "OOPJava_SECE_C_25_26", "8/7/2025", "2025-08-15"),
    ("Expt 4: Ascending and Descending order", "COA", "8/6/2025", None),
    ("Practical-2-Infix to Postfix Conversion", "Data Structure", "8/1/2025", "2025-08-08"),
    ("Expt 3: Minimum and Maximum numbers", "COA", "7/31/2025", "2025-08-07"),
    ("Experiment No. 3- Inheritance, Interface, Abstract, Super and Final keyword", "OOPJava_SECE_C_25_26", "7/31/2025", "2025-08-05"),
    ("Expt 2: Multiplication of two 8-bit and 16-bit numbers", "COA", "7/24/2025", "2025-07-31"),
    ("Practical-1A-Balanced Paranthesis", "Data Structure", "7/23/2025", "2025-07-25"),
    ("Practical-1", "Data Structure", "7/19/2025", "2025-07-25"),
    ("Experiment 2- Fundamental concepts of OOP", "OOPJava_SECE_C_25_26", "7/19/2025", "2025-07-02"),
    ("COA Expt1: Addition of two numbers", "COA", "7/11/2025", "2025-07-16"),
    ("Experiment 1: Java Fundamentals", "OOPJava_SECE_C_25_26", "7/9/2025", "2025-07-26"),
    ("Book/ Movie review", "FE CE C AOC", "4/29/2025", None),
    ("Perform these commands", "ECSE computer FE C", "4/25/2025", None),
    ("Presentation report", "FE CE C AOC", "4/24/2025", None),
    ("MIS summary writing", "FE CE C AOC", "4/21/2025", None),
    ("PCC11CE03: DE EXPERIMENT 8", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "4/18/2025", "2025-04-22"),
    ("PCC11CE03: DE EXPERIMENT 7", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "4/18/2025", "2025-04-22"),
    ("PCC11CE03: DE EXPERIMENT 2", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "4/18/2025", "2025-04-22"),
    ("Assignment on DBMS for Batch 1", "ECSE computer FE C", "4/17/2025", "2025-04-30"),
    ("Writeups Tutorial 6: Double Integration", "FE COMP C 2024-2025", "4/4/2025", "2025-04-10"),
    ("Assignment 2_6", "ECSE computer FE C", "4/2/2025", "2025-04-20"),
    ("Hand written Assignment on HHS Module 4&5", "Human Health Systems", "3/28/2025", "2025-04-16"),
    ("MITT: ELX: Submission of the Write-up", "FE C-A,B,C", "3/26/2025", "2025-04-16"),
    ("Lab performance", "ECSE computer FE C", "3/13/2025", None),
    ("PCC11CE03: DE EXPERIMENT 6", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "3/11/2025", None),
    ("PCC11CE03: DE EXPERIMENT 5", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "3/11/2025", "2025-03-31"),
    ("CREATIVE VISUAL TRIP", "FOCUS FOREVER", "3/9/2025", "2025-03-30"),
    ("HTML, CSS and Javascript.", "ECSE computer FE C", "2/21/2025", "2025-04-01"),
    ("PCC11CE03: DE EXPERIMENT 4", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "2/20/2025", "2025-03-25"),
    ("PCC11CE03: DE EXPERIMENT 3", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "2/18/2025", "2025-03-25"),
    ("PPT Creation", "ECSE computer FE C", "2/10/2025", "2025-03-27"),
    ("Test Latex Example", "ECSE computer FE C", "2/10/2025", None),
    ("Assignment on Basic Linux Commands", "ECSE computer FE C", "2/6/2025", "2025-04-17"),
    ("PCC11CE03: DE EXPERIMENT 1", "PCC11CE03: DIGITAL ELECTRONICS THEORY AND PRACTICALS", "2/5/2025", "2025-03-25"),
    ("2. HHS-Human Organ System Activity", "Human Health Systems", "2/4/2025", "2025-02-28"),
    ("Public speaking draft", "FE CE C AOC", "2/3/2025", None),
    ("Evolution of communication in Indian History", "FE CE C AOC", "2/3/2025", None),
    ("Assignment No 1", "ECSE computer FE C", "1/30/2025", None),
    ("Module 2 Assignment", "ECSE computer FE C", "1/28/2025", "2025-04-01"),
    ("HHS- Personality Trait Activity", "Human Health Systems", "1/21/2025", "2025-01-30"),
    ("LAB_ISE", "FEComp_DIVC", "12/19/2024", "2024-12-19"),
    ("ISE_2", "FEComp_DIVC", "12/12/2024", "2024-12-13"),
    ("Experiment 7: Mini Project", "Python_24(C-B1)", "12/8/2024", "2024-12-20"),
    ("Experiment 6: Classes", "Python_24(C-B1)", "12/2/2024", "2024-12-11"),
    ("Lab Quiz", "FEComp_DIVC", "11/29/2024", None),
    ("Resubmission of Poster", "Python_24(C-B1)", "11/29/2024", "2024-11-30"),
    ("Experiment 5: Functions", "Python_24(C-B1)", "11/22/2024", "2024-11-29"),
    ("Experiment 4", "Python_24(C-B1)", "10/30/2024", "2024-11-20"),
    ("exp2", "EPSE_FE", "10/16/2024", "2024-10-21"),
    ("Experiment 3: Decision Flow Control Statements", "Python_24(C-B1)", "10/15/2024", "2024-10-31"),
    ("exp1", "EPSE_FE", "10/15/2024", None),
    ("Experiment 2 : List and dictionaries", "Python_24(C-B1)", "10/10/2024", "2024-10-18"),
    ("Experiment 1: study of datatypes", "Python_24(C-B1)", "10/3/2024", "2024-10-11"),
    ("Second Term Evaluation", "9th A", "4/16/2021", None),
    ("Second Term Evaluation - History & Political Science", "9th A", "4/15/2021", None),
    ("Second Term Evaluation - Marathi", "9th A", "4/14/2021", None),
    ("Writing Skill - Marathi", "9th A", "4/14/2021", None),
    ("Writing Skill - French", "9th A", "4/12/2021", None),
    ("Second Term Evaluation - French Composite", "9th A", "4/12/2021", None),
    ("Second Term Evaluation - Hindi Composite", "9th A", "4/9/2021", None),
    ("Hindi Composite - Writing Skill", "9th A", "4/9/2021", None),
    ("Second Term Evaluation - English", "9th A", "4/9/2021", None),
    ("English - Writing Skill", "9th A", "4/8/2021", None),
    ("Second Term Evaluation - Science II", "9th A", "4/8/2021", None),
    ("Second Term Evaluation - Science I", "9th A", "4/7/2021", None),
    ("Second Term Evaluation - Math II", "9th A", "4/6/2021", None),
    ("Second Term Evaluation - Math I", "9th A", "4/5/2021", None),
    ("Religion Evaluation Second Term", "9th A", "3/30/2021", None),
    ("9th History MCQ II Term", "9th A", "3/18/2021", "2021-03-21"),
    ("9th Geography MCQ (II Term)", "9th A", "3/18/2021", None),
    ("Submission of Scout Online Exam paper -17/3/21", "9th A", "3/17/2021", "2021-03-17"),
    ("Quadrilaterals", "9th A", "3/12/2021", "2021-03-20"),
    ("9th PS. Ch.6: International problems", "9th A", "3/12/2021", "2021-03-15"),
    ("Chapter 15- Life Processes in Living Organisms", "9th A", "3/10/2021", "2021-03-15"),
    ("Submission of Exam- Online paper marks- 6/3/2021", "9th A", "3/6/2021", "2021-03-06"),
    ("9th History. Ch.Changing Life -1", "9th A", "3/5/2021", "2021-03-08"),
    ("Std. 9 - Geography - Chpt. 11 - Transport and Communication (Assignment)", "9th A", "3/2/2021", "2021-03-06"),
    ("French C - Second Unit Test", "9th A", "2/26/2021", "2021-02-02"),
    ("Revision of possessif adjectives.", "9th A", "2/25/2021", "2021-02-27"),
    ("Revision of Trouvez l'intrus ( odd one out)", "9th A", "2/24/2021", "2021-02-26"),
    ("5. India and other Countries", "9th A", "2/22/2021", "2021-02-25"),
    ("Chp-17 Introduction to Biotechnology(Assignment)", "9th A", "2/16/2021", "2021-02-25"),
    ("9th Geography Ch.10: Urbanisation.", "9th A", "2/16/2021", "2021-02-18"),
    ("Activity- social Leadership", "9th A", "2/13/2021", "2021-02-13"),
    ("Social Leadership", "9th A", "2/12/2021", "2021-02-13"),
    ("Please Listen", "9th A", "2/11/2021", "2021-02-14"),
    ("Science - I Second UT", "9th A", "2/5/2021", None),
    ("Math II Second Unit Test", "9th A", "2/4/2021", "2021-02-04"),
    ("History & Political Science-2nd Unit Test- Evaluation", "9th A", "2/3/2021", None),
    ("Std.9- Science-2: Second Unit Test Evaluation:03/02/2021", "9th A", "2/2/2021", "2021-02-03"),
    ("MATHEMATICS PART 1 EVALUATION 02/02/2021", "9th A", "2/2/2021", None),
    ("\u0926\u094d\u0935\u093f\u0924\u0940\u092f \u0918\u091f\u0915 \u092a\u0930\u0940\u0915\u094d\u0937\u093e (\u0938\u0902\u092f\u0941\u0915\u094d\u0924 \u0939\u093f\u0902\u0926\u0940)", "9th A", "2/2/2021", None),
    ("The Story Teller", "9th A", "2/2/2021", "2021-02-28"),
    ("Std. 9 - Geography - 2nd Unit Test - 1st February'2021", "9th A", "2/1/2021", "2021-02-01"),
    ("Marathi Evalution 1.02.2021", "9th A", "1/31/2021", "2021-02-01"),
    ("Unit Test- English", "9th A", "1/31/2021", "2021-02-03"),
    ("DON BOSCO QUIZ (LIFE OF DON BOSCO)", "9th A", "1/29/2021", "2021-01-30"),
    ("8. Industry and Trade", "9th A", "1/18/2021", "2021-01-22"),
    ("Std. 9 - Economics - Chpt.9 - Trade (Assignment)", "9th A", "1/12/2021", "2021-01-15"),
    ("Growth mindset Activity", "9th A", "1/12/2021", "2021-01-12"),
    ("Chapter 16- Heredity & Variation", "9th A", "1/8/2021", "2021-01-11"),
    ("Revision of Direct and Indirect Pronouns", "9th A", "1/7/2021", "2021-01-11"),
    ("How the first letter was written ?", "9th A", "1/7/2021", "2021-01-10"),
    ("9th PS- Ch.4 UNited Nations", "9th A", "1/5/2021", "2021-01-07"),
    ("CHAPTER 04 : RATIO AND PROPORTION ASSIGNMENT", "9th A", "1/3/2021", "2021-01-07"),
    ("Computer- Word Processor", "9th A", "12/17/2020", None),
    ("Computer: Chapter_Word Processor", "9th A", "12/17/2020", None),
    ("Circle Assignment 2", "9th A", "12/15/2020", "2020-12-23"),
    ("7. Science and Technology", "9th A", "12/15/2020", "2020-12-19"),
    ("The Road not Taken", "9th A", "12/14/2020", "2020-12-20"),
    ("Revision of Adjectives", "9th A", "12/10/2020", "2020-12-14"),
    ("std 9 Sci-2 Ch 18 Assignment (Observing Space: Telescopes)", "9th A", "12/9/2020", "2020-12-13"),
    ("Geog: Ch. 8 Introduction to Economics", "9th A", "12/8/2020", "2020-12-10"),
    ("Scout Registration Details", "9th A", "12/8/2020", "2020-12-15"),
    ("History Ch.6: Empowerment of women", "9th A", "12/1/2020", "2020-12-03"),
    ("Circle", "9th A", "11/30/2020", "2020-12-09"),
    ("Assignment 1 - II Term", "9th A", "11/27/2020", "2020-11-30"),
    ("Reading works of art", "9th A", "11/26/2020", "2020-11-29"),
    ("Std. 9 - Chpt. 7 - International Date Line (Assignment)", "9th A", "11/24/2020", "2020-11-27"),
    ("Swavikas-Art Appreciation Activity is a must. (15mks) Reference of Poster Design", "9th A", "11/9/2020", "2020-11-12"),
    ("History paper (First term evaluation 2020-21)", "9th A", "11/8/2020", "2020-11-09"),
    ("FIRST TERM EVALUATION: MATHEMATICS PART 1", "9th A", "11/6/2020", "2020-11-07"),
    ("Std 9 Science-2 First Term Evaluation", "9th A", "11/6/2020", None),
    ("\u0939\u093f\u0902\u0926\u0940 (\u0938\u0902\u092f\u0941\u0915\u094d\u0924)- \u092a\u094d\u0930\u0925\u092e \u0938\u0924\u094d\u0930\u093e\u0902\u0924 \u092e\u0942\u0932\u094d\u092f\u093e\u0902\u0915\u0928", "9th A", "11/4/2020", None),
    ("First Term English Evaluation", "9th A", "11/2/2020", None),
    ("1st Term Evaluation", "9th A", "11/1/2020", "2020-11-02"),
    ("First Term Evaluation", "9th A", "10/30/2020", None),
    ("Std. 9 - Geography - Evaluation - 29th October 2020", "9th A", "10/29/2020", "2020-10-29"),
    ("Religion Evaluation ( Term)", "9th A", "10/27/2020", "2020-10-28"),
    ("Scout test", "9th A", "10/10/2020", "2020-10-10"),
    ("SCOUT - Test 25marks", "9th A", "10/9/2020", "2020-10-10"),
    ("Marathi 1st sem. assignment writing skill 5.10.2020", "9th A", "10/4/2020", None),
    ("Writing Skills - Assignment 2", "9th A", "10/3/2020", "2020-10-06"),
    ("Writing Skills - Assignment", "9th A", "10/3/2020", "2020-10-05"),
    ("Assignment Test", "9th A", "10/2/2020", "2020-10-03"),
    ("Marathi 1st Semester Assignment Writing Skill 3/10/2020", "9th A", "10/2/2020", None),
    ("Writing Skill", "9th A", "10/2/2020", None),
    ("Assignment of Art. 1st term Activity (25 mks).", "9th A", "9/28/2020", "2020-09-30"),
    ("Ch.6 : Properties of Sea water", "9th A", "9/21/2020", "2020-09-24"),
    ("Swavikas chp -5", "9th A", "9/18/2020", "2020-09-30"),
    ("L 2.3 & L 2.5", "9th A", "9/17/2020", "2020-09-20"),
    ("Ch.4 : Economic Development", "9th A", "9/15/2020", "2020-09-17"),
    ("\u0939\u093f\u0902\u0926\u0940 \u0926\u093f\u0935\u0938", "9th A", "9/14/2020", "2020-09-21"),
    ("Std 9 - Sci 2: Chpt 10 - ICT Assignment - Surbhi Crasto", "9th A", "9/11/2020", "2020-09-15"),
    ("A True story of the sea turtles", "9th A", "9/10/2020", "2020-09-13"),
    ("Std. 9 - Geography - Chpt. 5 - Precipitation (Assignment)", "9th A", "9/8/2020", "2020-09-11"),
    ("CHAPTER 05: LINEAR EQUATIONS IN TWO VARIABLES: ASSIGNMENT 1", "9th A", "9/6/2020", "2020-09-10"),
    ("Science -I Unit Test", "9th A", "9/5/2020", None),
    ("First Unit Test (2020-21)", "9th A", "9/4/2020", None),
    ("First Unit Test Math 2- 4th September, 2020", "9th A", "9/4/2020", "2020-09-04"),
    ("Std 9 UT-1 Science 2", "9th A", "9/3/2020", None),
    ("English : 1st Unit Test", "9th A", "9/3/2020", None),
    ("FIRST UNIT TEST: MATHS 1", "9th A", "9/2/2020", "2020-09-02"),
    ("1st Unit Test French Composite. Time-15 minutes.", "9th A", "9/2/2020", None),
    ("Std. 9 - Geography - First Unit Test - 1st September, 2020", "9th A", "9/1/2020", "2020-09-01"),
    ("Marathi 1st Online Unit Test", "9th A", "9/1/2020", None),
    ("Revision of Lesson 1", "9th A", "8/19/2020", "2020-08-24"),
    ("Revision of Lesson 1 (2)", "9th A", "8/19/2020", "2020-08-24"),
    ("Ch.4. Exogenetic Processes - Part 2", "9th A", "8/18/2020", "2020-08-20"),
    ("Write an essay on Clean Town, Green Town in about 200 - 250 words.", "9th A", "8/14/2020", "2020-08-15"),
    ("Parts of speech ( New )", "9th A", "8/13/2020", "2020-08-15"),
    ("Parts of speech", "9th A", "8/12/2020", "2020-08-15"),
    ("Self Report : chp no 1", "9th A", "8/11/2020", "2020-09-30"),
    ("India's Internal Challenges", "9th A", "8/10/2020", None),
    ("\u0935\u093e\u0915\u094d\u092f\u093e\u091a\u0947 \u092a\u094d\u0930\u0915\u093e\u0930 assignment", "9th A", "8/6/2020", "2020-08-10"),
    ("Chapter 9 - Environmental Management", "9th A", "8/6/2020", "2020-08-09"),
    ("CHAPTER 03: POLYNOMIALS", "9th A", "8/4/2020", "2020-08-07"),
    ("Std. 9 - Geography -Chpt.3 - Exogenetic Processes - Part 1 (Assignment)", "9th A", "8/4/2020", "2020-08-07"),
    ("Triangles", "9th A", "8/4/2020", "2020-08-12"),
    ("Invictus", "9th A", "8/3/2020", "2020-08-09"),
    ("Text Exercises", "9th A", "7/29/2020", "2020-08-03"),
    ("PS-CH-1: Post World War Political Movements", "9th A", "7/28/2020", "2020-07-30"),
    ("Figures of Speech", "9th A", "7/27/2020", "2020-08-02"),
    ("Swavikas chp no 1 Activity 1", "9th A", "7/24/2020", "2020-08-15"),
    ("Chp- 8 Useful and Harmful Microbes(Assignment)", "9th A", "7/23/2020", "2020-07-29"),
    ("Ch2. Endogenetic Movements", "9th A", "7/21/2020", "2020-07-24"),
    ("Measurement of mass Assign", "9th A", "7/20/2020", "2020-07-25"),
    ("Parallel lines", "9th A", "7/14/2020", "2020-07-22"),
    ("CHAPTER 02 : REAL NUMBERS ASSIGNMENT", "9th A", "7/13/2020", "2020-07-16"),
    ("The Necklace", "9th A", "7/12/2020", "2020-07-19"),
    ("Marathi Assignment 1", "9th A", "7/10/2020", "2020-07-17"),
    ("Assignment 3", "9th A", "6/30/2020", "2020-07-07"),
    ("CHAPTER 02: REAL NUMBERS : ASSIGNMENT 01", "9th A", "6/29/2020", "2020-07-02"),
    ("2. India Events after 1960", "9th A", "6/29/2020", "2020-07-02"),
    ("Have You Ever Seen", "9th A", "6/28/2020", "2020-07-05"),
    ("A Synopsis- The Swiss Family Robinson (Assignment)", "9th A", "6/25/2020", None),
    ("Chapter 1 Assignment 2", "9th A", "6/23/2020", "2020-06-30"),
    ("Sci 1 Laws of Motion (Assign 2)", "9th A", "6/22/2020", "2020-06-27"),
    ("Chapter 1 Sets: Assignment 02", "9th A", "6/22/2020", "2020-06-25"),
    ("Assignment 1", "9th A", "6/19/2020", "2020-06-23"),
    ("Sci 2 Classification of Plants Assign 1", "9th A", "6/18/2020", "2020-06-24"),
]


def parse_posted(posted_str):
    """Parse M/D/YYYY posted date string into ISO datetime."""
    try:
        dt = datetime.strptime(posted_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def build_rows():
    """Build all assignment rows for insertion."""
    rows = []
    seq = 0

    # 1) Assigned with due date
    for title, course, posted, due in ASSIGNED_DUE:
        seq += 1
        rows.append(build_row(seq, title, course, posted, due, "pending", "assigned"))

    # 2) Assigned without due date
    for title, course, posted, due in ASSIGNED_NO_DUE:
        seq += 1
        rows.append(build_row(seq, title, course, posted, due, "pending", "no due date"))

    # 3) Submitted
    for title, course, posted, due in SUBMITTED:
        seq += 1
        rows.append(build_row(seq, title, course, posted, due, "completed", "submitted"))

    return rows


def build_row(seq, title, course, posted, due, status, classroom_label):
    """Build a single assignment row tuple."""
    aid = uuid.uuid4().hex
    classroom_id = f"manual_{seq:04d}"
    created_at = parse_posted(posted)
    updated_at = created_at

    metadata = json.dumps({
        "classroom": {
            "source": "google_classroom",
            "course": course,
            "submission_status": "submitted" if classroom_label == "submitted" else "assigned",
            "workflow_status": classroom_label,
            "classroom_label": classroom_label,
            "has_due_date": due is not None,
            "posted_at": posted,
        }
    })

    return (
        aid,           # id
        USER_ID,       # user_id
        title,         # title
        course,        # subject
        "assignment",  # task_type
        None,          # description
        due,           # deadline
        "medium",      # priority
        status,        # status
        classroom_id,  # classroom_id
        metadata,      # ai_metadata
        created_at,    # created_at
        updated_at,    # updated_at
    )


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Remove any previously inserted manual assignments (idempotent re-run)
    cursor.execute("DELETE FROM assignments WHERE classroom_id LIKE 'manual_%'")
    deleted = cursor.rowcount
    if deleted:
        print(f"Cleaned up {deleted} previously inserted manual assignments")

    rows = build_rows()
    print(f"Inserting {len(rows)} assignments...")

    cursor.executemany(
        """INSERT INTO assignments
           (id, user_id, title, subject, task_type, description, deadline,
            priority, status, classroom_id, ai_metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()

    # Verify
    total = cursor.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    manual = cursor.execute(
        "SELECT COUNT(*) FROM assignments WHERE classroom_id LIKE 'manual_%'"
    ).fetchone()[0]

    print(f"\nDone! Inserted {manual} classroom assignments.")
    print(f"Total assignments in DB: {total}")

    # Show breakdown
    for label in ["assigned", "no due date", "submitted"]:
        cnt = cursor.execute(
            "SELECT COUNT(*) FROM assignments WHERE classroom_id LIKE 'manual_%' AND ai_metadata LIKE ?",
            (f'%"classroom_label": "{label}"%',),
        ).fetchone()[0]
        print(f"  {label}: {cnt}")

    conn.close()


if __name__ == "__main__":
    main()
