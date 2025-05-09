# 🤖 AnalyzeBot — Telegram Chat & Data Analytics Tool

**AnalyzeBot** is a Python-based Telegram bot that collects, stores, and analyzes chat data for mental health tracking, user behavior monitoring, and messaging insights. It includes a Flask web interface and Jupyter notebooks for data visualization.

---

## 🧠 Features

- 📥 Collects and stores Telegram messages into a local SQLite database
- 📊 Exports conversations as CSV for manual or notebook-based analysis
- 🧾 Jupyter notebooks to analyze message patterns and trends
- 🌐 Flask web interface served at `http://localhost:5000`
- 💡 AI prompt base for potential OpenAI/GPT summarization
- 📂 Uses config.json for clean token management

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/analyze_bot.git
cd analyze_bot-main
```

### 2. Install dependencies

```bash
pip install flask python-telegram-bot pandas
```

> Optional: for notebook support
```bash
pip install notebook
```

---

### 3. Configure the Bot

In `config.json`, replace `YOUR_TELEGRAM_BOT_TOKEN` with your bot token from @BotFather:

```json
{
  "token": "YOUR_TELEGRAM_BOT_TOKEN"
}
```

---

### 4. Run the Bot and Web Interface

Start the bot:

```bash
python bot_mentalx.py
```

Start the Flask app:

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) to view the dashboard.

---

### 5. Analyze the Data

Launch the notebook interface:

```bash
jupyter notebook data.ipynb
```

This allows you to:

- View chat frequency over time
- Extract message patterns
- Generate charts (bar, line, word cloud, etc.)

---

## 🖼️ Screenshots
<img width="1470" alt="Screenshot 2025-05-09 at 7 13 07 PM" src="https://github.com/user-attachments/assets/f4fc6a13-652b-4077-9268-ce6d77d3bfd1" />
<img width="1470" alt="Screenshot 2025-05-09 at 7 13 17 PM" src="https://github.com/user-attachments/assets/c28379ac-896f-4a6c-8262-67cef796e9a1" />
<img width="1470" alt="Screenshot 2025-05-09 at 7 13 24 PM" src="https://github.com/user-attachments/assets/9497fa6e-f6af-4df4-b453-8c7da61fa91a" />
<img width="1470" alt="Screenshot 2025-05-09 at 7 13 31 PM" src="https://github.com/user-attachments/assets/160b3e3a-1ad3-44d1-893b-4fbdaba1efdb" />

---

## 📝 Project Report

### 📌 Overview

AnalyzeBot is a multifunctional Telegram chatbot that saves user messages for further analysis. It is designed to assist with behavioral analytics, psychological insight gathering, or building LLM training datasets.

### ⚙️ Components

| File              | Description                               |
|-------------------|-------------------------------------------|
| `bot_mentalx.py`  | Telegram bot logic and DB integration     |
| `app.py`          | Flask server that displays dashboard      |
| `chat_data.csv`   | Exported message logs                     |
| `telegram_bot.db` | SQLite DB used to store incoming messages |
| `data.ipynb`      | Notebook for analytics and plotting       |
| `promt.txt`       | Custom prompt format for GPT/AI usage     |

### 🛠 Technologies

- Python 3.11+
- `python-telegram-bot`
- Flask
- SQLite
- Pandas / Matplotlib
- Jupyter Notebooks

---

## 🧪 Potential Use Cases

- Mental health journal via messaging
- Export chat summaries for therapists
- AI-based reflection or journaling
- Behavior analysis by keyword frequency
- Admin dashboard for daily conversation metrics

---

## 📜 License

This project is licensed under the **MIT License** — free to use, modify, and distribute.

---

## 👤 Author

- 🧑 Timur
- 📧 timlim.2006@gmail.com
- 🐙 GitHub: [github.com/yourusername](https://github.com/Ogurchick-fim)
