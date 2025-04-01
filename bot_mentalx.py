import os
import sqlite3
import logging
import json
import re
from datetime import datetime
from telegram import ReplyKeyboardMarkup , ReplyKeyboardRemove
from telegram.ext import (

    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    
)
from openai import OpenAI

# Load configuration
with open('config.json', 'r') as file:
    data = json.load(file)

# --- Global Configuration & Globals ---
with open('config.json', 'r') as file:
    data = json.load(file)
DB_FILE = 'telegram_bot.db'
client = OpenAI(api_key=data['openai_api_key'])
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Initialization and Helper Functions ---

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
    # Authorizations table for storing authorization data
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
    # New table for storing mental health risk percentage and risk category
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
def is_valid_input(user_input):
    # Define the regular expression pattern
    pattern = r'^[A-Za-z\u0400-\u04FF0-9\s\|\]\[\+=\-@#.,!?;:()\'\"—]+$'
    # Match the pattern against the user input
    return bool(re.match(pattern, user_input))
async def validate_input(update, context):
    user_message = update.message.text
    if not is_valid_input(user_message):
        await update.message.reply_text("Invalid input. Please use only permitted characters.")
        return
    else:
        await message_handler(update, context)
def insert_chat(chat):
    """Insert chat info into the Chats table if not already present."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM Chats WHERE chat_id = ?', (chat.id,))
    if cursor.fetchone() is None:
        chat_name = getattr(chat, 'title', None)
        cursor.execute(
            'INSERT INTO Chats (chat_id, chat_name, created_at) VALUES (?, ?, ?)',
            (chat.id, chat_name, datetime.now().isoformat())
        )
        conn.commit()
    conn.close()

def insert_message(chat, user, content):
    """Insert a new message into the Messages table and update daily stats."""
    now = datetime.now()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO Messages (chat_id, user_id, content, timestamp) VALUES (?, ?, ?, ?)',
        (chat.id, user.id, content, now.isoformat())
    )
    current_date = now.date().isoformat()
    cursor.execute('''
        INSERT INTO MessageStats (user_id, date, message_count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET message_count = message_count + 1
    ''', (user.id, current_date))
    conn.commit()
    conn.close()

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

async def message_handler(update, context):
    chat = update.message.chat
    user = update.message.from_user
    message_text = update.message.text

    insert_chat(chat)
    insert_message(chat, user, message_text)
    
    history = get_user_history(user.id)
    needs_analysis, explanation = analyze_user_messages(history)  # This call must find the function
    analysis_text = ("Concern detected: " + explanation) if needs_analysis else ("No concern detected: " + explanation)
    update_user_analysis(user.id, analysis_text)
    logger.info(f"User {user.id} analysis updated: {analysis_text}")
    
    ai_reply = get_ai_response(message_text)
    await update.message.reply_text(ai_reply)

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

def get_user_history(user_id: int) -> str:
    """Retrieve and combine all messages of a given user ordered by time."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT content FROM Messages 
        WHERE user_id = ? 
        ORDER BY timestamp
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return "\n".join(message for (message,) in rows)

def get_all_users() -> list:
    """Retrieve a list of distinct user IDs from the Messages table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM Messages ORDER BY user_id')
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]

def get_user_analysis(user_id: int) -> str:
    """Retrieve the latest analysis result for a given user from the Analyses table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT analysis_result, updated_at FROM Analyses WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return f"Last updated at {row[1]}: {row[0]}"
    else:
        return "No analysis available."

def get_message_stats(user_id: int) -> list:
    """Retrieve daily message statistics for a given user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, message_count FROM MessageStats
        WHERE user_id = ?
        ORDER BY date DESC
    ''', (user_id,))
    stats = cursor.fetchall()
    conn.close()
    return stats

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

# --- New Analysis Function for Mental Health Risk Percentage ---

def get_mental_health_percentage(user_history: str) -> (float, str):
    """
    Use OpenAI's API to get a mental health risk percentage (0-100) based on the user's conversation history.
    Expected output format: "NUMBER: CATEGORY" (e.g., "15: Green").
    """
    messages_list = [msg.strip() for msg in user_history.split("\n") if msg.strip()]
    # If not enough data, default to 0%
    if len(" ".join(messages_list).split()) < 50:
        return (0.0, "Green")
    
    recent_history = "\n".join(messages_list[-10:])
    prompt = (
        "Based on the following user's conversation history, provide a mental health risk percentage from 0 to 100. "
        "0 means the user is completely okay, and 100 means extremely high risk. Then, assign a risk category as follows: "
        "0-20: Green - you are okay, 20-40: Orange - a little problem, 40-60: Yellow - moderate concern, above 60: Red - immediate help needed. "
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
         logger.error(f"Error parsing mental health analysis: {e}. Response was: {result}")
         return (0.0, "Green")

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

# --- Authorization Conversation Handlers ---
# Define conversation states.
AGE, GENDER, COUNTRY = range(3)



# Allowed choices for each step
AGE_RANGES = ['0-6', '7-11', '11-14', '15-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+']
GENDER_OPTIONS = ['Male', 'Female']
COUNTRY_OPTIONS = ['Armenia', 'Azerbaijan', 'Belarus', 'Kazakhstan', 'Kyrgyzstan', 'Moldova', 'Russia', 'Tajikistan', 'Uzbekistan']

async def start_authorization(update, context):
    """
    Introduce the bot and initiate the authorization flow.
    """
    intro_message = (
        "Hello! I'm your friendly assistant. "
        "Let's get started! Please select your age range:"
    )
    age_keyboard = [AGE_RANGES[i:i + 5] for i in range(0, len(AGE_RANGES), 5)]
    markup = ReplyKeyboardMarkup(age_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(intro_message, reply_markup=markup)
    return AGE

async def handle_age(update, context):
    """Store the age and ask for gender."""
    age = update.message.text
    if age not in AGE_RANGES:
        await update.message.reply_text("Please select a valid age range from the keyboard.")
        return AGE
    context.user_data['age'] = age
    gender_keyboard = [GENDER_OPTIONS]
    markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Great! Now, please select your gender:", reply_markup=markup)
    return GENDER

async def handle_gender(update, context):
    """Store the gender and ask for country selection."""
    gender = update.message.text
    if gender not in GENDER_OPTIONS:
        await update.message.reply_text("Please select a valid gender from the keyboard.")
        return GENDER
    context.user_data['gender'] = gender
    country_keyboard = [COUNTRY_OPTIONS[i:i + 2] for i in range(0, len(COUNTRY_OPTIONS), 2)]
    markup = ReplyKeyboardMarkup(country_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Finally, please select your country:", reply_markup=markup)
    return COUNTRY

async def handle_country(update, context):
    """Store the country, save authorization data, and complete the process."""
    country = update.message.text
    if country not in COUNTRY_OPTIONS:
        await update.message.reply_text("Please select a valid country from the keyboard.")
        return COUNTRY
    user_id = update.message.from_user.id
    context.user_data['country'] = country
    # Insert authorization data into your database or storage here
    await update.message.reply_text("Authorization completed. Thank you!", reply_markup=ReplyKeyboardRemove())
    insert_authorization(user_id, **context.user_data)
    return ConversationHandler.END


async def cancel(update, context):
    """Handle the cancellation of the conversation."""
    await update.message.reply_text("Authorization process has been cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- Handler for General Messages ---
async def message_handler(update, context):
    """Process incoming text messages: store, analyze, update analysis, update mental health risk, and respond using AI."""
    chat = update.message.chat
    user = update.message.from_user
    message_text = update.message.text

    insert_chat(chat)
    insert_message(chat, user, message_text)
    
    history = get_user_history(user.id)
    needs_analysis, explanation = analyze_user_messages(history)
    analysis_text = ("Concern detected: " + explanation) if needs_analysis else ("No concern detected: " + explanation)
    update_user_analysis(user.id, analysis_text)
    logger.info(f"User {user.id} analysis updated: {analysis_text}")
    
    # Compute mental health percentage and update in the new table.
    mental_percent, risk_category = get_mental_health_percentage(history)
    update_user_mental_health(user.id, mental_percent, risk_category)
    logger.info(f"User {user.id} mental health risk: {mental_percent}% ({risk_category})")
    
    ai_reply = get_ai_response(message_text)
    await update.message.reply_text(ai_reply)

# --- Main Application Setup ---
def main():
    # Initialize the database.
    init_db()
    
    # Create the Application and add handlers.
    application = Application.builder().token(data['telegram_bot_token']).build()
    # validation_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, validate_input)
    # application.add_handler(validation_handler, group=0)

    # Authorization conversation handler using /start as the entry point.
    auth_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_authorization)],
        states={
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gender)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add the conversation handler and the general message handler.
    application.add_handler(auth_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Start the bot.
    application.run_polling()

if __name__ == '__main__':
    main()