import os
import sqlite3
import json
from datetime import datetime
import mysql.connector
from datetime import datetime, timedelta

from flask import Flask, render_template_string, redirect, url_for, request
from openai import OpenAI

# Load configuration (ensure config.json exists with the required keys)
with open('config.json', 'r') as file:
    data = json.load(file)

# --- Global Configuration & Globals ---
DB_FILE = 'telegram_bot.db'
client = OpenAI(api_key=data['openai_api_key'])

# --- Database Helper Functions ---

def init_db():
    """Initialize the SQLite database with required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Chats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            chat_name TEXT,
            created_at TEXT
        )
    ''')
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY (chat_id) REFERENCES Chats(chat_id)
        )
    ''')
    # Analyses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            analysis_result TEXT,
            updated_at TEXT
        )
    ''')
    # MessageStats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS MessageStats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,  
            message_count INTEGER,
            UNIQUE(user_id, date)
        )
    ''')
    # Authorizations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Authorizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            age TEXT,
            gender TEXT,
            country TEXT,
            created_at TEXT
        )
    ''')
    # UserMentalHealth table for storing mental health risk data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS UserMentalHealth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            mental_percent REAL,
            risk_category TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_all_authorizations():
    """Return all authorization records from the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, age, gender, country, created_at FROM Authorizations")
    users = cursor.fetchall()
    conn.close()
    return users

def get_authorization_by_user(user_id: int):
    """Return the authorization record for a given user_id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, age, gender, country, created_at FROM Authorizations WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_messages(user_id: int):
    """Retrieve all messages sent by the user, ordered by timestamp."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT content, timestamp FROM Messages WHERE user_id = ? ORDER BY timestamp", (user_id,))
    messages = cursor.fetchall()
    conn.close()
    return messages

def get_user_history(user_id: int) -> str:
    """Combine all messages of a given user into a single string."""
    messages = get_user_messages(user_id)
    history_lines = [f"[{ts}] {content}" for content, ts in messages]
    return "\n".join(history_lines)

def update_user_analysis(user_id: int, analysis_result: str):
    """Insert or update the analysis result for a given user in the Analyses table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT OR REPLACE INTO Analyses (id, user_id, analysis_result, updated_at)
        VALUES (
            (SELECT id FROM Analyses WHERE user_id = ?),
            ?, ?, ?
        )
    ''', (user_id, user_id, analysis_result, now))
    conn.commit()
    conn.close()

def get_user_analysis(user_id: int):
    """Retrieve the latest analysis result for a given user from the Analyses table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT analysis_result, updated_at FROM Analyses WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row if row else ("No analysis available.", "")

def insert_authorization(user_id: int, age: str, gender: str, country: str):
    """Insert or update authorization data for a given user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT OR REPLACE INTO Authorizations (user_id, age, gender, country, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, age, gender, country, now))
    conn.commit()
    conn.close()

def get_message_stats(user_id: int) -> list:
    """Retrieve daily message statistics for a given user (date, message_count)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, message_count FROM MessageStats
        WHERE user_id = ?
        ORDER BY date ASC
    ''', (user_id,))
    stats = cursor.fetchall()
    conn.close()
    return stats

def get_distribution(column: str):
    """Return labels and counts for a given column in Authorizations."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"SELECT {column}, COUNT(*) FROM Authorizations GROUP BY {column}")
    rows = cursor.fetchall()
    conn.close()
    labels = [row[0] for row in rows]
    counts = [row[1] for row in rows]
    return labels, counts

def update_user_mental_health(user_id: int, mental_percent: float, risk_category: str):
    """Insert or update the mental health risk percentage for a given user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT OR REPLACE INTO UserMentalHealth (user_id, mental_percent, risk_category, updated_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, mental_percent, risk_category, now))
    conn.commit()
    conn.close()

def get_user_mental_health(user_id: int):
    """Retrieve mental health risk data for a given user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT mental_percent, risk_category, updated_at FROM UserMentalHealth WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None, None)

# --- OpenAI Analysis Function ---

def analyze_user_messages(user_history: str, window_size: int = 10) -> (bool, str):
    messages_list = [msg.strip() for msg in user_history.split("\n") if msg.strip()]
    if len(" ".join(messages_list).split()) < 50:
        return (False, "Not enough data for analysis.")
    
    recent_history = "\n".join(messages_list[-window_size:])
    prompt = (
        "Analyze the following user's conversation history for signs of psychological distress or indicators that "
        "the user might benefit from psychological analysis. Give extra weight to the most recent messages. If the most recent "
        "messages indicate improvement or resolution of previous issues, reflect that in your analysis. Respond with either:\n"
        "'yes: <brief explanation>' if concern is detected, or\n"
        "'no: <brief explanation>' if no concern is detected.\n\n"
        "Recent conversation history:\n" + recent_history
    )
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Analyzing user conversation history."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100
    )
    result = response.choices[0].message.content.strip().lower()
    if result.startswith("yes:"):
        explanation = result[4:].strip()
        return (True, explanation)
    return (False, result[3:].strip() if result.startswith("no:") else result)

# --- OpenAI GPT Agent Functions for Conversational Replies ---

def get_ai_response(user_message: str) -> str:
    """Generate a conversational reply using GPT-3.5-turbo."""
    with open("promt.txt", "r") as f:
        system_prompt = f.read()
    messages = [
       {"role": "system", "content": system_prompt},
       {"role": "user", "content": user_message}
    ]
    response = client.chat.completions.create(
         model="gpt-3.5-turbo",
         messages=messages,
         max_tokens=150,
         temperature=0.7,
         top_p=1
    )
    return response.choices[0].message.content.strip()

# --- New Analysis Function for Mental Health Risk Percentage ---

def get_mental_health_percentage(user_history: str) -> (float, str):
    """
    Use OpenAI's GPT-3.5-turbo to analyze the user's conversation history and return a mental health risk percentage (0-100)
    along with a risk category.
    Expected output format: "NUMBER: CATEGORY" (e.g., "15: Green").
    """
    messages_list = [msg.strip() for msg in user_history.split("\n") if msg.strip()]
    if len(" ".join(messages_list).split()) < 50:
        return (0.0, "Green")
    
    recent_history = "\n".join(messages_list[-10:])
    prompt = (
        "Based on the following user's conversation history, provide a mental health risk percentage from 0 to 100. "
        "0 means the user is completely okay, and 100 means extremely high risk. Then, assign a risk category as follows: "
        "0-20: Green (you are okay), 20-40: Orange (a little problem), 40-60: Yellow (moderate concern), above 60: Red (immediate help needed). "
        "Output your answer in the format: NUMBER: CATEGORY. For example, '15: Green'.\n\n"
        "Conversation history:\n" + recent_history
    )
    
    response = client.chat.completions.create(
         model="gpt-3.5-turbo",
         messages=[
              {"role": "system", "content": "Analyze mental health risk."},
              {"role": "user", "content": prompt}
         ],
         max_tokens=50
    )
    result = response.choices[0].message.content.strip()
    try:
         parts = result.split(":")
         percent = float(parts[0].strip())
         category = parts[1].strip() if len(parts) > 1 else ""
         return (percent, category)
    except Exception as e:
         return (0.0, "Green")

# --- Flask Application Setup ---
app = Flask(__name__)

# Ensure the database is initialized
init_db()

# Dashboard: list all users as cards with pie charts and a risk filter form
@app.route("/")
def dashboard():
    # Get optional filter from query parameter (risk category)
    risk_filter = request.args.get("risk", "All")
    auth_users = get_all_authorizations()
    users = []
    for u in auth_users:
        mental = get_user_mental_health(u[0])
        if mental and mental[0] is not None:
            mental_percent, risk_category, mental_updated = mental
        else:
            mental_percent, risk_category, mental_updated = "N/A", "N/A", ""
        # Apply risk filter if selected (if not "All")
        if risk_filter != "All" and risk_category != risk_filter:
            continue
        users.append({
            "user_id": u[0],
            "age": u[1],
            "gender": u[2],
            "country": u[3],
            "created_at": u[4],
            "mental_percent": mental_percent,
            "risk_category": risk_category,
            "mental_updated": mental_updated
        })
    # Get distribution data for age, gender, country
    age_labels, age_counts = get_distribution("age")
    gender_labels, gender_counts = get_distribution("gender")
    country_labels, country_counts = get_distribution("country")
    
    dashboard_template = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>User Dashboard</title>
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      </head>
      <body>
        <div class="container mt-4">
          <h1>User Dashboard</h1>
          
          <!-- Risk Filter Form -->
          <form method="get" action="{{ url_for('dashboard') }}" class="mb-4">
            <label for="risk_filter">Filter by Mental Health Risk:</label>
            <select name="risk" id="risk_filter" class="form-control" style="max-width: 300px; display:inline-block;">
              <option value="All" {% if request.args.get('risk', 'All') == "All" %}selected{% endif %}>All</option>
              <option value="Green" {% if request.args.get('risk') == "Green" %}selected{% endif %}>Green</option>
              <option value="Orange" {% if request.args.get('risk') == "Orange" %}selected{% endif %}>Orange</option>
              <option value="Yellow" {% if request.args.get('risk') == "Yellow" %}selected{% endif %}>Yellow</option>
              <option value="Red." {% if request.args.get('risk') == "Red." %}selected{% endif %}>Red</option>
            </select>
            <button type="submit" class="btn btn-primary ml-2">Apply Filter</button>
          </form>
          
          <div class="row mb-4">
            <div class="col-md-4">
              <h4>Age Distribution</h4>
              <canvas id="ageChart"></canvas>
            </div>
            <div class="col-md-4">
              <h4>Gender Distribution</h4>
              <canvas id="genderChart"></canvas>
            </div>
            <div class="col-md-4">
              <h4>Country Distribution</h4>
              <canvas id="countryChart"></canvas>
            </div>
          </div>
          
          <div class="row">
            {% for user in users %}
              <div class="col-md-4">
                <div class="card mb-4">
                  <div class="card-body">
                    <h5 class="card-title">User ID: {{ user.user_id }}</h5>
                    <p class="card-text">
                      <strong>Age:</strong> {{ user.age }}<br>
                      <strong>Gender:</strong> {{ user.gender }}<br>
                      <strong>Country:</strong> {{ user.country }}<br>
                      <strong>Mental Health:</strong> {{ user.mental_percent }}% ({{ user.risk_category }})
                    </p>
                    <a href="{{ url_for('user_detail', user_id=user.user_id) }}" class="btn btn-primary">View Details</a>
                  </div>
                </div>
              </div>
            {% endfor %}
          </div>
        </div>
        
        <script>
          // Data for Age Chart
          var ageLabels = {{ age_labels|tojson }};
          var ageCounts = {{ age_counts|tojson }};
          var ctxAge = document.getElementById('ageChart').getContext('2d');
          new Chart(ctxAge, {
              type: 'pie',
              data: {
                  labels: ageLabels,
                  datasets: [{
                      data: ageCounts,
                      backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#66BB6A']
                  }]
              }
          });
          
          // Data for Gender Chart
          var genderLabels = {{ gender_labels|tojson }};
          var genderCounts = {{ gender_counts|tojson }};
          var ctxGender = document.getElementById('genderChart').getContext('2d');
          new Chart(ctxGender, {
              type: 'pie',
              data: {
                  labels: genderLabels,
                  datasets: [{
                      data: genderCounts,
                      backgroundColor: ['#8E24AA', '#3949AB']
                  }]
              }
          });
          
          // Data for Country Chart
          var countryLabels = {{ country_labels|tojson }};
          var countryCounts = {{ country_counts|tojson }};
          var ctxCountry = document.getElementById('countryChart').getContext('2d');
          new Chart(ctxCountry, {
              type: 'pie',
              data: {
                  labels: countryLabels,
                  datasets: [{
                      data: countryCounts,
                      backgroundColor: ['#FF7043', '#26A69A', '#AB47BC', '#EC407A', '#FFCA28']
                  }]
              }
          });
        </script>
      </body>
    </html>
    """
    return render_template_string(dashboard_template, users=users,
                                  age_labels=age_labels, age_counts=age_counts,
                                  gender_labels=gender_labels, gender_counts=gender_counts,
                                  country_labels=country_labels, country_counts=country_counts)

# User detail page: show user's messages, analysis result, and a line chart of message counts per day
from datetime import datetime, timedelta

@app.route("/user/<int:user_id>")
def user_detail(user_id):
    user = get_authorization_by_user(user_id)
    messages = get_user_messages(user_id)
    analysis_result, updated_at = get_user_analysis(user_id)
    stats = get_message_stats(user_id)
    
    # Convert dates to datetime objects and extract counts
    dates = [datetime.strptime(stat[0], '%Y-%m-%d') if isinstance(stat[0], str) else stat[0] for stat in stats]
    counts = [stat[1] for stat in stats]
    
    # Check if dates list is not empty
    if dates:
        # Determine the date range (from the first to the last date in the records)
        min_date = min(dates)
        max_date = max(dates)
        
        # Generate a list of all dates in the range
        all_dates = [min_date + timedelta(days=i) for i in range((max_date - min_date).days + 1)]
        
        # Create a mapping of dates to counts (default to 0 for missing dates)
        date_to_count = {date: 0 for date in all_dates}
        for date, count in zip(dates, counts):
            date_to_count[date] = count
        
        # Prepare the data for rendering
        date_labels = [date.strftime('%Y-%m-%d') for date in all_dates]
        record_counts = [date_to_count[date] for date in all_dates]
    else:
        # Handle the case when no dates are available
        date_labels = []
        record_counts = []

    user_detail_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>User {{ user[0] }} Details</title>
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <!-- Add the date adapter -->
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@latest"></script>
    </head>
    <body>
        <div class="container mt-4">
        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary mb-3">Back to Dashboard</a>
        <h2>User Details</h2>
        <ul class="list-group mb-3">
            <li class="list-group-item"><strong>User ID:</strong> {{ user[0] }}</li>
            <li class="list-group-item"><strong>Age:</strong> {{ user[1] }}</li>
            <li class="list-group-item"><strong>Gender:</strong> {{ user[2] }}</li>
            <li class="list-group-item"><strong>Country:</strong> {{ user[3] }}</li>
            <li class="list-group-item"><strong>Authorized At:</strong> {{ user[4] }}</li>
        </ul>
        <h3>Analysis Result</h3>
        <p><em>{{ analysis_result }}</em> {% if updated_at %}<small>(Last updated: {{ updated_at }})</small>{% endif %}</p>
        <a href="{{ url_for('reanalyze', user_id=user[0]) }}" class="btn btn-warning mb-4">Reanalyze</a>

        <h3>Messages per Day</h3>
        <canvas id="messageLineChart"></canvas>

        <h3 class="mt-4">User Messages</h3>
        {% if messages %}
            <ul class="list-group">
            {% for content, ts in messages %}
                <li class="list-group-item">
                <small class="text-muted">{{ ts }}</small><br>
                {{ content }}
                </li>
            {% endfor %}
            </ul>
        {% else %}
            <p>No messages found for this user.</p>
        {% endif %}
        </div>

        <script>
            var dateLabels = {{ date_labels|safe }};
            var recordCounts = {{ record_counts|safe }};

            var ctx = document.getElementById('messageLineChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dateLabels,
                    datasets: [{
                        label: 'Records per Day',
                        data: recordCounts,
                        borderColor: '#36A2EB',
                        fill: false
                    }]
                },
                options: {
                        scales: {
                            x: {
                                type: 'time',
                                time: {
                                    unit: 'day',
                                    tooltipFormat: 'PPP' // or 'yyyy-MM-dd'
                                },
                                title: {
                                    display: true,
                                    text: 'Date'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Message Count'
                                }
                            }
                        }
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(user_detail_template, user=user, messages=messages,
                                  analysis_result=analysis_result, updated_at=updated_at,
                                  date_labels=date_labels, record_counts=record_counts)
# Endpoint to re-run analysis for a given user
@app.route("/user/<int:user_id>/reanalyze")
def reanalyze(user_id):
    user_history = get_user_history(user_id)
    success, explanation = analyze_user_messages(user_history)
    analysis_text = ("Concern detected: " + explanation) if success else ("No concern detected: " + explanation)
    update_user_analysis(user_id, analysis_text)
    return redirect(url_for('user_detail', user_id=user_id))

if __name__ == '__main__':
    app.run(debug=True)