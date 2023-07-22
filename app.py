# IMPORTED MODULES
from cs50 import SQL
from flask import Flask, redirect, render_template, request, render_template_string
from re import findall
from sympy import symbols, Eq, sympify, solve
from math import log10, floor
from json import dumps
import random
from pint import UnitRegistry


# CONFIGURE APPLICATION
app = Flask(__name__)


# CONFIGURE DATABASE
db = SQL("sqlite:///phasla.db")


# CREATE A PINT UNITREGISTRY
ureg = UnitRegistry()


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


# HOMEPAGE
@app.route("/")
def index():
    return render_template("pages/index.html")


# TOPICS PAGE
@app.route("/topics")
def topics():
    # Retrieve information from the database and create a list of tuples
    TOPICS = [(row["topic"], row["category"]) for row in db.execute("SELECT topic, category FROM topics")]
    return render_template("pages/topics.html", topic=TOPICS)


# ABOUT PAGE
@app.route("/about")
def about():
    # Retrieve information from the database and create a list of tuples
    ADMINS = [(row["name"], row["email"], row["imageURL"]) for row in db.execute("SELECT name, email, imageURL FROM admin;")]
    return render_template("pages/about.html", admins=ADMINS)


# ERROR PAGE FOR ALL EXCEPTIONS
# @app.errorhandler(Exception)
# def handle_error(error):
#     # Get the status code from the error object (default to 500)
#     STATUS_CODE = getattr(error, 'code', 500)
#     # Get the description of the status code (default to ISE)
#     DESCRIPTION = getattr(error, 'description', 'Internal Server Error')
#     return render_template("pages/error.html", statusCode=STATUS_CODE, description=DESCRIPTION)


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
# TODO PRIORITIES:
    # *    SHOW SOLUTION: FIX PROCESS THEN SHOW CONVERSIONN
    # • DO SUBSTITUTIONS INSTEAD
    # *    DIFFICULTY BUTTONS: CHANGING OPTIONS

    # *    OPTIMIZATION AND COMMENTS
    # *    FIX COMMENTS SO THAT THERE'S A COMMENT BEFORE EVERY FUNCTION

    # *    FUNCTION: CREATION OF VALUES
    # *    OTHER TODOs

@app.route("/worksheet", methods=["GET", "POST"])
def worksheet():
    global TOPIC, CATEGORY, DIFFICULTY, FORMULA, VARIABLES, QUANTITIES, QUESTION_ID, RENDERED_QUESTION, UNITS_QUESTION, SCORE, SOLVED_STATUS

    # Guard clause for GET method
    if request.method == "GET" or request.args.get("next"):

        DIFFICULTY = request.args.get("options")
        if request.args.get("next"):
            DIFFICULTY = request.args.get("next")

        all_solved = bool(QUESTION_ID["all"]) and all(index in SOLVED_STATUS["Yes"] for index in QUESTION_ID["all"])

        if DIFFICULTY in SOLVED_STATUS["Difficulty"]:
            SOLVED_STATUS["Difficulty"].append(DIFFICULTY)
            DIFFICULTY = None
            return render_basic_worksheet(TOPIC, CATEGORY)

        if DIFFICULTY and not all_solved:
            FORMULA, VARIABLES, QUESTION_ID, RENDERED_QUESTION, QUANTITIES, UNITS_QUESTION = generate_question()
            return render_template(
                "pages/worksheet.html",
                topic=TOPIC.capitalize(),
                category=CATEGORY,
                difficulty=DIFFICULTY,
                question=RENDERED_QUESTION,
                unit=QUANTITIES["units"],
                score=f"{SCORE['correct']}/{SCORE['total']}"
            )

        SOLVED_STATUS["Difficulty"].append(DIFFICULTY)
        DIFFICULTY = None
        return render_basic_worksheet(TOPIC, CATEGORY)

    # Guard clause for POST method
    if request.method == "POST" and request.form.get("topic"):
        TOPIC = request.form.get("topic")
        CATEGORY = request.form.get("category")
        return render_basic_worksheet(TOPIC, CATEGORY)

    elif request.method == "POST" and request.form.get("number"):
        SUBMITTED_ANSWER = [
            float(request.form.get("number")),
            request.form.get("unit"),
        ]

        MISSING_VAR, SOLUTION, ANSWER = get_answer()
        CORRECT_STATUS, SOLVED_STATUS, SCORE = check_answer(SUBMITTED_ANSWER, ANSWER)
        SOLUTION_TEXT = render_solution(MISSING_VAR, SOLUTION, ANSWER)

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
            score=f"{SCORE['correct']}/{SCORE['total']}"
        )
    
    elif request.method == "POST" and request.form.get('end'):
        TOPIC, CATEGORY, DIFFICULTY, FORMULA, VARIABLES, RENDERED_QUESTION, UNITS_QUESTION, SOLVED_STATUS, QUESTION_ID, QUANTITIES, SCORE = reset()

        if request.form.get("end") == "nav-btn":
            # Redirect to the selected page when triggered by the navigation link
            return redirect(request.form.get("exitLink"))

        # Always redirect to "/topics" when triggered by the finish button
        return redirect("/topics")
    return redirect('/error')


def reset():
    # Reinitialize empty variables
    TOPIC = CATEGORY = DIFFICULTY = FORMULA = VARIABLES = RENDERED_QUESTION = UNITS_QUESTION = None
    # Reinitialize dictionaries with indexes
    SOLVED_STATUS = {"Yes": [], "No": [], "Difficulty": []}
    QUESTION_ID = {"all": [], "selected": None}
    QUANTITIES = {"symbols": {}, "units": {}}
    SCORE = {"total": 0, "correct": 0}
    # Return variables and dictionaries
    return TOPIC, CATEGORY, DIFFICULTY, FORMULA, VARIABLES, RENDERED_QUESTION, UNITS_QUESTION, SOLVED_STATUS, QUESTION_ID, QUANTITIES, SCORE


def render_basic_worksheet(TOPIC, CATEGORY):
    # Render worksheet page without showing questions
    return render_template(
        "pages/worksheet.html",
        topic=TOPIC.capitalize(),
        category=CATEGORY,
    )


def render_solution(MISSING_VAR, SOLUTION, ANSWER):
    # TODO: ADD FOR CONVERSIONS (IF STATEMENT)
    return render_template_string(
        "To solve the problem, use the formula: {{ formula }}.<br><br>"
        "{{ missingVariable }} = {{ solution }} = {{ answer }}",
        formula=FORMULA,
        missingVariable=MISSING_VAR,
        solution=SOLUTION.subs(VARIABLES),
        answer=f"{ANSWER['number']} {ANSWER['unit']}",
    )


def check_answer(SUBMITTED_ANSWER, ANSWER):
    """Check answer if it is correct"""
    # Check if the number in SUBMITTED_ANSWER is within the tolerance of the number in ANSWER
    number_correct = abs(SUBMITTED_ANSWER[0] - ANSWER['number']) < 0.001
    # Check if the unit in SUBMITTED_ANSWER matches the unit in ANSWER
    unit_correct = SUBMITTED_ANSWER[1] == ANSWER['unit']
    # Update the SOLVED_STATUS dictionary based on the correctness of the submitted answer
    SOLVED_STATUS[("No", "Yes")[number_correct and unit_correct]].append(QUESTION_ID["selected"])
    # Update the SCORE dictionary based on the correctness of the submitted answer
    SCORE["correct"] += number_correct and unit_correct
    SCORE["total"] += 1
    return {'number': number_correct, 'unit': unit_correct}, SOLVED_STATUS, SCORE


def get_answer():
    """Get the correct answer"""
    # Find the missing variable
    formula_symbols = extract_formula_symbols()
    missing_variable = next(symbol for symbol in formula_symbols if symbol not in VARIABLES)
    # Split the equation into LHS and RHS
    lhs_str, rhs_str = FORMULA.split("=")
    # Convert the LHS and RHS to SymPy expressions
    lhs_expr, rhs_expr = sympify(lhs_str.strip()), sympify(rhs_str.strip())
    # Solve for the missing variable
    MISSING_VAR = symbols(missing_variable)
    SOLUTION = solve(Eq(lhs_expr, rhs_expr), MISSING_VAR)[0]
    # Get the units for each variable in VARIABLES from the database
    data = db.execute("SELECT name, unit FROM units WHERE name IN ({})".format(", ".join(f"'{variable}'" for variable in VARIABLES.keys())))
    # Create a dictionary to store the variable units
    unitsVariables = {index["name"]: str(ureg(index["unit"]).units) for index in data}
    # Check if the units in UNITS_QUESTION match with unitsVariables for each index
    for index in VARIABLES.keys():
        if UNITS_QUESTION.get(index) != unitsVariables.get(index):
            # Perform conversion only for indexes with non-matching units
            conversion_expr = ureg.Quantity(VARIABLES[index], UNITS_QUESTION[index]).to(unitsVariables[index])
            VARIABLES[index] = round(conversion_expr.magnitude, 4)
    # Round number to two significant digits
    numAnswer = eval(str(SOLUTION.subs(VARIABLES)))
    numAnswer = round(numAnswer, -int(floor(log10(abs(numAnswer)))) + 1)
    # Store correct number and unit into ANSWER
    ANSWER = {
        "number": numAnswer,
        "unit": QUANTITIES["symbols"].get(str(MISSING_VAR))
    }
    return MISSING_VAR, SOLUTION, ANSWER

    
def extract_formula_symbols():
    """Extract the symbols (variables) from the formula."""
    # Regular expression pattern for word-like sequences
    pattern = r"\b[A-Za-z]+\b"
    # Find all the formula symbols
    return findall(pattern, FORMULA)


def extract_units_from_text(text, variables):
    # Extract numbers and units using regular expressions
    pattern = r"(\d+(\.\d+)?)\s+([a-zA-Z/]+)"
    matches = findall(pattern, text)
    # Create a list to keep track of the variable order in the matches
    variable_order = [variable for number, _, unit in matches for variable in variables if unit in text]
    # Use a dictionary comprehension to group units by variables
    return {variable_order[i]: str(ureg(unit).units) for i, (_, _, unit) in enumerate(matches)}


def get_variables(QUESTION):
    """" Extract then provide values to variables from question"""
    # Initialize empty dictionary
    VARIABLES = {}
    # Start from the beginning of the question
    start = 0
    while True:
        # Find the start of a Jinja template
        start = QUESTION.find("{{", start)
        if start == -1:
            break # If no more Jinja templates are found, exit the loop
        # Find the end of the Jinja template
        end = QUESTION.find("}}", start + 2) 
        if end == -1:
            break # If the end of the template is not found, exit the loop
        # Extract the variable name from the template
        TEMPLATE = QUESTION[start + 2 : end].strip()
        # Generate values for the variable and add it to VARIABLES
        VARIABLES[TEMPLATE.lower()] = generate_values()
        # Move to the next Jinja template in the question
        start = end + 2
    return VARIABLES


def generate_question():
    topicID = db.execute("SELECT topicID FROM topics WHERE topic = ?", TOPIC)[0]["topicID"]

    if DIFFICULTY is None:
        FORMULA = VARIABLES = RENDERED_QUESTION = QUANTITIES["units"] = " "
        return FORMULA, VARIABLES, RENDERED_QUESTION, QUANTITIES["units"]

    QUESTION_ID["all"] = [
        row["questionID"]
        for row in db.execute(
            "SELECT questionID FROM questions WHERE topicID = ? AND difficulty = ?;",
            topicID,
            DIFFICULTY,
        )
    ]

    QUESTION_ID["selected"] = random.choice([q_id for q_id in QUESTION_ID["all"] if q_id not in SOLVED_STATUS["Yes"]])


    data = db.execute(
        "SELECT q.text, q.formula FROM questions q JOIN topics t ON q.topicID = t.topicID WHERE q.topicID = ? AND q.difficulty = ? AND q.questionID = ?;", topicID, DIFFICULTY, QUESTION_ID["selected"])

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
    QUANTITIES["units"] = {variable_name: unit_values[i] for i, variable_name in enumerate(QUANTITIES["units"])}
    QUANTITIES["units"] = QUANTITIES["units"].values()

    return FORMULA, VARIABLES, QUESTION_ID, RENDERED_QUESTION, QUANTITIES, UNITS_QUESTION


def get_measurements(all_variables):
    """Retrieve symbols and units for a given list of variables"""
    # Initialize empty dictionaries
    symbols = units = {}
    # Loop through each variable in the list
    for index in all_variables:
        # Retrieve symbol and unit for the variables from database
        data = db.execute("SELECT symbol, unit FROM units WHERE name = ?", index)
        # Store the symbol and unit in the dictionaries if data is found, otherwise leave empty
        symbols[index], units[index] = data[0]["symbol"], data[0]["unit"] if data else ("", "")
    return symbols, units


# TODO HOW TO ADJUST VALUE CREATION DEPENDING OF DIFFICULTY AND VARIABLES TO BE CREATED
# GENERATE RANDOM VALUES BASED ON QUESTION
def generate_values():
    return random.randint(3, 11)


# RUN FLASK APPLICATION
if __name__ == "__main__":
    app.run()