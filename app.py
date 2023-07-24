# IMPORTED MODULES
from cs50 import SQL
from flask import Flask, redirect, render_template, request, render_template_string
from re import findall
from sympy import symbols, Eq, sympify, solve
from math import log10, floor
from json import dumps
import random
from pint import UnitRegistry, UndefinedUnitError
import inflect


# CONFIGURE APPLICATION
app = Flask(__name__)


# CONFIGURE DATABASE
db = SQL("sqlite:///phasla.db")


# CREATE A PINT UNITREGISTRY AND INFLECT ENGINE
ureg = UnitRegistry()
p = inflect.engine()


# ENSURE RESPONSES ARE NOT CACHED
@app.after_request
def after_request(response):
    # Set headers to prevent caching of the response
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    # Return the modified response object
    return response


# GLOBAL VARIABLES
# Initialize empty variables
TOPIC = CATEGORY = DIFFICULTY = FORMULA = VARIABLES = RENDERED_QUESTION = UNITS_QUESTION = None
# Initialize dictionaries with indexes
SOLVED_STATUS = {"Yes": [], "No": [], "Difficulty": []}
QUESTION_ID = {"all": [], "selected": None}
QUANTITIES = {"symbols": {}, "units": {}}
SCORE = {"total": 0, "correct": 0}
ALL_SOLVED = {"easy": False, "standard": False, "hard": False}


# HOMEPAGE
@app.route("/")
def index():
    return render_template("pages/index.html")


# TOPICS PAGE
@app.route("/topics")
def topics():
    # Retrieve information from the database and create a list of tuples
    TOPICS = [
        (row["topic"], row["category"])
        for row in db.execute("SELECT topic, category FROM topics")
    ]
    return render_template("pages/topics.html", topic=TOPICS)


# ABOUT PAGE
@app.route("/about")
def about():
    # Retrieve information from the database and create a list of tuples
    ADMINS = [
        (row["name"], row["email"], row["imageURL"])
        for row in db.execute("SELECT name, email, imageURL FROM admin;")
    ]
    return render_template("pages/about.html", admins=ADMINS)


# ERROR PAGE FOR ALL EXCEPTIONS
@app.errorhandler(Exception)
def handle_error(error):
    # Get the status code from the error object (default to 500)
    STATUS_CODE = getattr(error, 'code', 500)
    # Get the description of the status code (default to ISE)
    DESCRIPTION = getattr(error, 'description', 'Internal Server Error')
    return render_template("pages/error.html", statusCode=STATUS_CODE, description=DESCRIPTION)


# ADMIN PAGE
# TODO REMOVE ONCE DONE
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        db.execute(
            "INSERT INTO questions (text, formula, difficulty, topicID) VALUES (?, ?, ?, ?)",
            request.form.get("text"),
            request.form.get("formula"),
            request.form.get("difficulty"),
            request.form.get("topicID"),
        )
    return render_template("pages/admin.html")


# WORKSHEET PAGE
# *    OTHER TODOs: BRING BACK ERROR PAGE
@app.route("/worksheet", methods=["GET", "POST"])
def worksheet():
    global TOPIC, CATEGORY, DIFFICULTY, FORMULA, VARIABLES, QUANTITIES, QUESTION_ID, RENDERED_QUESTION, UNITS_QUESTION, SCORE, SOLVED_STATUS, ALL_SOLVED

    # Guard clause for GET method
    if request.method == "GET" or request.args.get("next"):
        # Get the topic and category from the URL
        DIFFICULTY = request.args.get("options")
        if request.args.get("next"):
            DIFFICULTY = request.args.get("next")
        # Update the ALL_SOLVED dictionary based on the selected DIFFICULTY
        ALL_SOLVED[DIFFICULTY] = bool(QUESTION_ID["all"]) and all(
            index in SOLVED_STATUS["Yes"] for index in QUESTION_ID["all"]
        )  # Prompt user to select new difficulty when all questions for the selected difficulty level are solved
        if DIFFICULTY and ALL_SOLVED[DIFFICULTY]:
            SOLVED_STATUS["Difficulty"].append(DIFFICULTY)
            QUESTION_ID = {"all": [], "selected": None}
            solvedDifficulty = DIFFICULTY
            allSolved = dumps(
                {key: str(value).lower() for key, value in ALL_SOLVED.items()}
            )
            DIFFICULTY = None
            return render_template(
                "pages/worksheet.html",
                topic=TOPIC.capitalize(),
                difficulty=solvedDifficulty,
                category=CATEGORY,
                allSolved=allSolved,
                score=f"{SCORE['correct']}/{SCORE['total']}",
            )  # Generate a new question when the user selects a new difficulty level
        if DIFFICULTY and not ALL_SOLVED[DIFFICULTY]:
            (
                FORMULA,
                VARIABLES,
                QUESTION_ID,
                RENDERED_QUESTION,
                QUANTITIES,
                UNITS_QUESTION,
            ) = generate_question()
            return render_template(
                "pages/worksheet.html",
                topic=TOPIC.capitalize(),
                category=CATEGORY,
                difficulty=DIFFICULTY,
                question=RENDERED_QUESTION,
                unit=QUANTITIES["units"],
                score=f"{SCORE['correct']}/{SCORE['total']}",
            )  # If no conditions are met, set DIFFICULTY to None and render the basic worksheet
        DIFFICULTY = None
        return render_basic_worksheet(TOPIC, CATEGORY)
    # Guard clause for POST method
    if request.method == "POST" and request.form.get("topic"):
        # Get the topic and category from form
        TOPIC = request.form.get("topic")
        CATEGORY = request.form.get("category")
        return render_basic_worksheet(TOPIC, CATEGORY)
    elif request.method == "POST" and request.form.get("number"):
        # Get the submitted answer from form
        SUBMITTED_ANSWER = [
            float(request.form.get("number")),
            request.form.get("unit"),
        ]  # Get correct answer
        (
            MISSING_VAR,
            SOLUTION,
            ANSWER,
            VARIABLES_ORIGINAL,
            UNITS_VARIABLES,
        ) = get_answer()
        # Check if submitted answer is correct
        CORRECT_STATUS, SOLVED_STATUS, SCORE = check_answer(SUBMITTED_ANSWER, ANSWER)
        # Render solution
        SOLUTION_TEXT = render_solution(
            MISSING_VAR, SOLUTION, ANSWER, VARIABLES_ORIGINAL, UNITS_VARIABLES
        )
        return render_template(
            "pages/worksheet.html",
            topic=TOPIC.capitalize(),
            category=CATEGORY,
            difficulty=DIFFICULTY,
            question=RENDERED_QUESTION,
            unit=QUANTITIES["units"],
            correctAnswer=dumps(CORRECT_STATUS),
            submittedNumber=SUBMITTED_ANSWER[0],
            submittedUnit=SUBMITTED_ANSWER[1],
            solution=SOLUTION_TEXT,
            score=f"{SCORE['correct']}/{SCORE['total']}",
        )
    elif request.method == "POST" and request.form.get("end"):
        # Reset all the global variables to their initial values
        (
            TOPIC,
            CATEGORY,
            DIFFICULTY,
            FORMULA,
            VARIABLES,
            RENDERED_QUESTION,
            UNITS_QUESTION,
            SOLVED_STATUS,
            QUESTION_ID,
            QUANTITIES,
            SCORE,
        ) = reset()
        if request.form.get("end") == "nav-btn":
            # Redirect to the selected page when triggered by the navigation link
            return redirect(request.form.get("exitLink"))
        # Always redirect to "/topics" when triggered by the finish button
        return redirect("/topics")
    # Redirect to error page if none of the conditions are met
    return redirect("/error")


# RESET VARIABLES USED IN WORKSHEET
def reset():
    # Reinitialize empty variables
    TOPIC = (
        CATEGORY
    ) = DIFFICULTY = FORMULA = VARIABLES = RENDERED_QUESTION = UNITS_QUESTION = None
    # Reinitialize dictionaries with indexes
    SOLVED_STATUS = {"Yes": [], "No": [], "Difficulty": []}
    QUESTION_ID = {"all": [], "selected": None}
    QUANTITIES = {"symbols": {}, "units": {}}
    SCORE = {"total": 0, "correct": 0}
    # Return variables and dictionaries
    return (
        TOPIC,
        CATEGORY,
        DIFFICULTY,
        FORMULA,
        VARIABLES,
        RENDERED_QUESTION,
        UNITS_QUESTION,
        SOLVED_STATUS,
        QUESTION_ID,
        QUANTITIES,
        SCORE,
    )


# RENDER BLANK WORKSHEET PAGE
def render_basic_worksheet(TOPIC, CATEGORY):
    # Render worksheet page without showing questions
    return render_template(
        "pages/worksheet.html",
        topic=TOPIC.capitalize(),
        category=CATEGORY,
        clear="true",
    )


# RENDER SOLUTION
def render_solution(MISSING_VAR, SOLUTION, ANSWER, VARIABLES_ORIGINAL, UNITS_VARIABLES):
    # Replace '/' in unit strings with 'per'
    for var, unit_str in UNITS_QUESTION.items():
        unit_str = unit_str.replace("/", "per")
    # Update UNITS_QUESTION to contain unit abbreviations
    for var, unit_str in UNITS_QUESTION.items():
        # Check if the unit exists in the Unit Registry using get_dimensionality or parse_expression
        if ureg.get_dimensionality(unit_str):
            # Use the unit directly if it's a valid unit in the registry
            unit_abbreviation = unit_str
        else:
            # Otherwise, try to parse the unit string and get the abbreviation
            try:
                parsed_unit = ureg.parse_expression(unit_str)
                unit_abbreviation = ureg.get_symbol(parsed_unit)
            except UndefinedUnitError:
                # If the unit is still not found, use an empty string
                unit_abbreviation = ""
        UNITS_QUESTION[var] = unit_abbreviation
    # Convert the variables in SOLUTION to strings and update with units from UNITS_QUESTION
    SOLUTION = str(SOLUTION)
    # Check if units in UNITS_QUESTION are the same as UNITS_VARIABLES
    conversion_text = ""
    for index in VARIABLES.keys():
        if UNITS_QUESTION.get(index) != UNITS_VARIABLES.get(index):
            # Perform conversion only for indexes with non-matching units
            VARIABLES_ORIGINAL[index] = (
                str(VARIABLES_ORIGINAL[index]) + " " + UNITS_QUESTION[index]
            )
            VARIABLES[index] = str(VARIABLES[index]) + " " + UNITS_VARIABLES[index]
            # Add conversion details to conversion_text
            conversion_text += f"{index.capitalize()}: {VARIABLES_ORIGINAL[index]} -> {VARIABLES[index]}<br>"
    # Check if any conversions were made and add appropriate text
    if conversion_text:
        conversion_text = (
            "Convert the necessary variables:<br>" + conversion_text + "<br>"
        )
    else:
        # Update VARIABLES with UNITS_VARIABLES
        for index in VARIABLES.keys():
            VARIABLES[index] = str(VARIABLES[index]) + " " + UNITS_VARIABLES[index]
    for var, value in VARIABLES.items():
        # Replace the variable with its value and add the corresponding unit from UNITS_QUESTION
        SOLUTION = SOLUTION.replace(var, f"{value}")
    # Return rendered solution text
    return render_template_string(
        f"{conversion_text}"
        "To solve the problem, use the formula: {{ formula }}.<br>"
        "{{ missingVariable }} = {{ solution }} = {{ answer }}",
        formula=FORMULA,
        missingVariable=str(MISSING_VAR).capitalize(),
        solution=SOLUTION,
        answer=f"{ANSWER['number']} {ANSWER['unit']}",
    )


# CHECK IF SUBMITTED ANSWER IS CORRECT
def check_answer(SUBMITTED_ANSWER, ANSWER):
    # Check if the number in SUBMITTED_ANSWER is within the tolerance of the number in ANSWER
    number_correct = abs(SUBMITTED_ANSWER[0] - ANSWER["number"]) < 0.001
    # Check if the unit in SUBMITTED_ANSWER matches the unit in ANSWER
    unit_correct = SUBMITTED_ANSWER[1] == ANSWER["unit"]
    # Update the SOLVED_STATUS dictionary based on the correctness of the submitted answer
    SOLVED_STATUS[("No", "Yes")[number_correct and unit_correct]].append(
        QUESTION_ID["selected"]
    )
    # Update the SCORE dictionary based on the correctness of the submitted answer
    SCORE["correct"] += number_correct and unit_correct
    SCORE["total"] += 1
    return {"number": number_correct, "unit": unit_correct}, SOLVED_STATUS, SCORE


# GET CORRECT ANSWER
def get_answer():
    # Find the missing variable
    formula_symbols = extract_formula_symbols()
    missing_variable = next(
        symbol for symbol in formula_symbols if symbol not in VARIABLES
    )
    # Split the equation into LHS and RHS
    lhs_str, rhs_str = FORMULA.split("=")
    # Convert the LHS and RHS to SymPy expressions
    lhs_expr, rhs_expr = sympify(lhs_str.strip()), sympify(rhs_str.strip())
    # Solve for the missing variable
    MISSING_VAR = symbols(missing_variable)
    SOLUTION = solve(Eq(lhs_expr, rhs_expr), MISSING_VAR)[0]
    # Copy the original VARIABLES dictionary before conversion
    VARIABLES_ORIGINAL = VARIABLES.copy()
    # Get the units for each variable in VARIABLES from the database
    data = db.execute(
        "SELECT name, unit FROM units WHERE name IN ({})".format(
            ", ".join(f"'{variable}'" for variable in VARIABLES.keys())
        )
    )
    # Create a dictionary to store the variable units
    UNITS_VARIABLES = {index["name"]: str(ureg(index["unit"]).units) for index in data}
    # Loop through both UNITS_VARIABLES and UNITS_QUESTION
    for units_dict in (UNITS_VARIABLES, UNITS_QUESTION):
        for key, value in units_dict.items():
            # Convert "/" to "per"
            value = value.replace("/", "per")
            # Get plural form of unit
            units_dict[key] = p.plural(value)
            # Convert "per" back to "/"
            units_dict[key] = units_dict[key].replace("per", "/")
    for index in VARIABLES.keys():
        if UNITS_QUESTION.get(index) != UNITS_VARIABLES.get(index):
            # Perform conversion only for indexes with non-matching units
            conversion_expr = ureg.Quantity(VARIABLES[index], UNITS_QUESTION[index]).to(
                UNITS_VARIABLES[index]
            )
            VARIABLES[index] = round(conversion_expr.magnitude, 4)
    # Round number to two significant digits
    numAnswer = eval(str(SOLUTION.subs(VARIABLES)))
    numAnswer = round(numAnswer, -int(floor(log10(abs(numAnswer)))) + 1)
    # Store correct number and unit into ANSWER
    ANSWER = {"number": numAnswer, "unit": QUANTITIES["symbols"].get(str(MISSING_VAR))}
    return MISSING_VAR, SOLUTION, ANSWER, VARIABLES_ORIGINAL, UNITS_VARIABLES


# EXTRACT SYMVOLS FROM FORMULA
def extract_formula_symbols():
    # Regular expression pattern for word-like sequences
    pattern = r"\b[A-Za-z]+\b"
    # Find all the formula symbols
    return findall(pattern, FORMULA)


# EXTRACT NUMBERS AND UNITS FROM QUESTION USING REGULAR EXPRESSIONS
def extract_units_from_text(text, variables):
    pattern = r"(\d+(\.\d+)?)\s+([a-zA-Z/]+)"
    matches = findall(pattern, text)
    # Create a list to keep track of the variable order in the matches
    variable_order = [
        variable
        for number, _, unit in matches
        for variable in variables
        if unit in text
    ]
    # Use a dictionary comprehension to group units by variables
    return {
        variable_order[i]: str(ureg(unit).units)
        for i, (_, _, unit) in enumerate(matches)
    }


# EXTRACT THEN PROVIDE VALUES TO VARIABLES FROM QUESTION
def get_variables(QUESTION):
    # Initialize empty dictionary
    VARIABLES = {}
    # Start from the beginning of the question
    start = 0
    while True:
        # Find the start of a Jinja template
        start = QUESTION.find("{{", start)
        if start == -1:
            break  # If no more Jinja templates are found, exit the loop
        # Find the end of the Jinja template
        end = QUESTION.find("}}", start + 2)
        if end == -1:
            break  # If the end of the template is not found, exit the loop
        # Extract the variable name from the template
        TEMPLATE = QUESTION[start + 2 : end].strip()
        # Generate values for the variable and add it to VARIABLES
        VARIABLES[TEMPLATE.lower()] = generate_values(TEMPLATE)
        # Move to the next Jinja template in the question
        start = end + 2
    return VARIABLES


# RETRIEVE SYMBOLS AND UNITS FOR A GIVEN LIST OF VARIABLES
def get_measurements(all_variables):
    # Initialize empty dictionaries
    symbols = units = {}
    # Loop through each variable in the list
    for index in all_variables:
        # Retrieve symbol and unit for the variables from database
        data = db.execute("SELECT symbol, unit FROM units WHERE name = ?", index)
        # Store the symbol and unit in the dictionaries if data is found, otherwise leave empty
        symbols[index], units[index] = data[0]["symbol"], data[0]["unit"] if data else ("", "",)
    return symbols, units


# GENERATE RANDOM VALUES BASED ON QUESTION
def generate_values(TEMPLATE):
     # Dictionary to store generated values for each variable (TEMPLATE)
    generatedValues = {}
    # Difficulty settings for each template
    difficulty = {"easy": (2, 30), "standard": (10, 250), "hard": (30, 1000)}
    # Determine the minimum and maximum values based on the difficulty and variable
    min_value, max_value = difficulty.get(DIFFICULTY, None) or (5, 36) if TEMPLATE == "time" else (2, 50)
    while True:
        # Generate the random value based on the difficulty and variable
        generatedValue = round(random.uniform(min_value, max_value), 2) if DIFFICULTY in ["standard", "hard"] and TEMPLATE != "time" else random.randint(min_value, max_value)
        # If the variable is not yet in the generatedValues, add the value and return it
        if TEMPLATE not in generatedValues:
            generatedValues[TEMPLATE] = [generatedValue]
            return generatedValue
        # If the generated value is not yet present in the variable's history, add it and return it
        if generatedValue not in generatedValues[TEMPLATE]:
            generatedValues[TEMPLATE].append(generatedValue)
            return generatedValue


# GENERATE QUESTION
def generate_question():
    # Retrieve the topicID from the database based on the given TOPIC
    topicID = db.execute("SELECT topicID FROM topics WHERE topic = ?", TOPIC)[0][
        "topicID"
    ] # Check if DIFFICULTY is None, if so, return default values
    if DIFFICULTY is None:
        return " ", " ", " ", " "
    # Retrieve a list of all questionIDs for the given topicID and difficulty
    QUESTION_ID["all"] = [
        row["questionID"]
        for row in db.execute(
            "SELECT questionID FROM questions WHERE topicID = ? AND difficulty = ?;",
            topicID,
            DIFFICULTY,
        )
    ] # Select a random questionID from the list of all questionIDs that have not been marked as solved
    QUESTION_ID["selected"] = random.choice([q_id for q_id in QUESTION_ID["all"] if q_id not in SOLVED_STATUS["Yes"]]) 
    # Retrieve the text and formula of the selected question from the database
    data = db.execute(
        "SELECT q.text, q.formula FROM questions q JOIN topics t ON q.topicID = t.topicID WHERE q.topicID = ? AND q.difficulty = ? AND q.questionID = ?;",
        topicID,
        DIFFICULTY,
        QUESTION_ID["selected"],
    ) 
    QUESTION, FORMULA = (data[0]["text"], data[0]["formula"])
    # Identify Jinja templates (variables) in the question and assign unique values to them
    VARIABLES = get_variables(QUESTION)
    # Generate question with variables subtituted with variables
    RENDERED_QUESTION = render_template_string(QUESTION, **VARIABLES)
    # Identify units used in text
    UNITS_QUESTION = extract_units_from_text(RENDERED_QUESTION, VARIABLES)
    # Extract variables used in the formula
    FORMULA_VARIABLES = findall(r"\b\w+\b", FORMULA)
    # Combine the variables into a set without duplicates
    all_variables = set(VARIABLES.keys()) | set(FORMULA_VARIABLES)
    # Retrieve the symbol and unit for each variable
    QUANTITIES["symbols"], QUANTITIES["units"] = get_measurements(all_variables)
    # Shuffle the values in UNITS
    unit_values = list(QUANTITIES["units"].values())
    random.shuffle(unit_values)
    # Create a new shuffled_units dictionary
    QUANTITIES["units"] = {
        variable_name: unit_values[i]
        for i, variable_name in enumerate(QUANTITIES["units"])
    } # Convert the shuffled_units dictionary to a list and store it in QUANTITIES["units"]
    QUANTITIES["units"] = QUANTITIES["units"].values()
    # Return all the generated components
    return (
        FORMULA,
        VARIABLES,
        QUESTION_ID,
        RENDERED_QUESTION,
        QUANTITIES,
        UNITS_QUESTION,
    )


# RUN FLASK APPLICATION
if __name__ == "__main__":
    app.run(debug=True)
